from __future__ import annotations

import asyncio
import base64
import json
import os
import subprocess
import tempfile
import time
import uuid
from dataclasses import dataclass
from typing import List, Tuple

import boto3
import botocore.exceptions

from app.services.text_translation import _list_languages_sync, _resolve_target_language_code, _translate_client

_INDIAN_LANGUAGE_CODES = {"as", "bn", "gu", "hi", "kn", "ml", "mr", "or", "pa", "ta", "te"}

_INDIAN_POLLY_VOICES_BY_LANGUAGE_CODE = {
    # In current Polly setup, Hindi is reliably supported with Indian voices.
    "hi": "Aditi",
}


@dataclass(frozen=True)
class _Segment:
    start_s: float
    end_s: float
    text: str


def _require_env(name: str) -> str:
    v = os.getenv(name)
    if not v:
        raise RuntimeError(f"Missing required environment variable: {name}")
    return v


def _aws_creds() -> tuple[str, str, str]:
    ak = os.getenv("AWS_ACCESS_KEY")
    sk = os.getenv("AWS_SECRET_KEY")
    region = os.getenv("AWS_REGION", "us-east-1")
    if not (ak and sk):
        raise RuntimeError("Missing AWS credentials in environment (AWS_ACCESS_KEY/AWS_SECRET_KEY).")
    return ak, sk, region


def _s3_client():
    ak, sk, region = _aws_creds()
    return boto3.client("s3", aws_access_key_id=ak, aws_secret_access_key=sk, region_name=region)


def _transcribe_client():
    ak, sk, region = _aws_creds()
    return boto3.client("transcribe", aws_access_key_id=ak, aws_secret_access_key=sk, region_name=region)


def _polly_client():
    ak, sk, region = _aws_creds()
    return boto3.client("polly", aws_access_key_id=ak, aws_secret_access_key=sk, region_name=region)


def _run(cmd: List[str]) -> None:
    try:
        proc = subprocess.run(cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE, check=False)
    except FileNotFoundError as e:
        raise RuntimeError(f"Missing executable: {cmd[0]!r}. Install it and ensure it's on PATH.") from e
    if proc.returncode != 0:
        raise RuntimeError(f"{cmd[0]} failed: {proc.stderr.decode('utf-8', 'ignore')}")


def _ffmpeg(*args: str) -> None:
    _run(["ffmpeg", "-y", *args])


def _ffprobe_duration_seconds(path: str) -> float:
    cmd = [
        "ffprobe",
        "-v",
        "error",
        "-show_entries",
        "format=duration",
        "-of",
        "default=nokey=1:noprint_wrappers=1",
        path,
    ]
    try:
        proc = subprocess.run(cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE, check=False)
    except FileNotFoundError as e:
        raise RuntimeError("Missing executable: 'ffprobe'. Install FFmpeg (includes ffprobe) and ensure it's on PATH.") from e
    if proc.returncode != 0:
        raise RuntimeError(f"ffprobe failed: {proc.stderr.decode('utf-8', 'ignore')}")
    out = (proc.stdout or b"").decode("utf-8", "ignore").strip()
    try:
        return float(out)
    except ValueError as e:
        raise RuntimeError(f"Could not parse ffprobe duration output: {out!r}") from e


def _resolve_target_code(target_language: str) -> str:
    languages = _list_languages_sync()
    return _resolve_target_language_code(target_language, languages).lower()


def _translate_text_sync_auto(text: str, target_language_code: str) -> str:
    client = _translate_client()
    resp = client.translate_text(Text=text, SourceLanguageCode="auto", TargetLanguageCode=target_language_code)
    out = (resp.get("TranslatedText") or "").strip()
    if not out:
        raise RuntimeError("Amazon Translate returned empty translated text.")
    return out


def _transcribe_audio_s3(audio_wav_path: str) -> List[_Segment]:
    bucket = _require_env("TRANSCRIBE_BUCKET")
    job_name = f"video-audio-translate-{uuid.uuid4().hex}"
    audio_key = f"video-audio-translate/{job_name}/audio.wav"
    out_key = f"video-audio-translate/{job_name}/transcript.json"

    s3 = _s3_client()
    s3.upload_file(audio_wav_path, bucket, audio_key)

    media_uri = f"s3://{bucket}/{audio_key}"

    transcribe = _transcribe_client()
    try:
        transcribe.start_transcription_job(
            TranscriptionJobName=job_name,
            LanguageCode=os.getenv("TRANSCRIBE_LANGUAGE_CODE", "en-US"),
            Media={"MediaFileUri": media_uri},
            OutputBucketName=bucket,
            OutputKey=out_key,
            Settings={
                "ShowSpeakerLabels": False,
                "ShowAlternatives": False,
            },
        )
    except botocore.exceptions.ClientError as e:
        msg = e.response.get("Error", {}).get("Message", str(e))
        raise RuntimeError(f"AWS Transcribe error: {msg}") from e

    deadline = time.time() + float(os.getenv("TRANSCRIBE_TIMEOUT_SECONDS", "300"))
    while True:
        if time.time() > deadline:
            raise RuntimeError("AWS Transcribe timed out waiting for transcription job completion.")
        resp = transcribe.get_transcription_job(TranscriptionJobName=job_name)
        status = resp["TranscriptionJob"]["TranscriptionJobStatus"]
        if status in ("COMPLETED", "FAILED"):
            if status == "FAILED":
                reason = resp["TranscriptionJob"].get("FailureReason", "unknown")
                raise RuntimeError(f"AWS Transcribe failed: {reason}")
            break
        time.sleep(2.0)

    try:
        obj = s3.get_object(Bucket=bucket, Key=out_key)
        transcript_json = json.loads(obj["Body"].read().decode("utf-8"))
    except botocore.exceptions.ClientError as e:
        msg = e.response.get("Error", {}).get("Message", str(e))
        raise RuntimeError(f"Failed to fetch transcript from S3: {msg}") from e

    items = (transcript_json.get("results") or {}).get("items") or []
    if not items:
        raise RuntimeError("AWS Transcribe returned no items.")

    segments: List[_Segment] = []
    cur_words: List[str] = []
    cur_start: float | None = None
    cur_end: float | None = None

    def flush() -> None:
        nonlocal cur_words, cur_start, cur_end
        text = " ".join(w for w in cur_words if w).strip()
        if text and cur_start is not None and cur_end is not None and cur_end >= cur_start:
            segments.append(_Segment(start_s=cur_start, end_s=cur_end, text=text))
        cur_words = []
        cur_start = None
        cur_end = None

    for it in items:
        t = it.get("type")
        alts = it.get("alternatives") or []
        content = (alts[0].get("content") if alts else "") or ""
        if t == "pronunciation":
            try:
                st = float(it.get("start_time"))
                en = float(it.get("end_time"))
            except (TypeError, ValueError):
                continue
            if cur_start is None:
                cur_start = st
            cur_end = en
            cur_words.append(content)
        elif t == "punctuation":
            if content in (".", "!", "?"):
                flush()
            else:
                if cur_words:
                    cur_words[-1] = f"{cur_words[-1]}{content}"

    flush()
    if not segments:
        # Fallback: use full transcript text without timestamps (still useful)
        full = ((transcript_json.get("results") or {}).get("transcripts") or [{}])[0].get("transcript") or ""
        full = str(full).strip()
        if not full:
            raise RuntimeError("AWS Transcribe returned empty transcript.")
        # place at start; will produce unsynced overlay, but at least generates audio
        segments = [_Segment(start_s=0.0, end_s=0.0, text=full)]

    return segments


def _pick_polly_voice(target_language_code: str) -> str:
    explicit = (os.getenv("POLLY_VOICE_ID") or "").strip()
    if explicit:
        return explicit
    code = (target_language_code or "").strip().lower()
    if code in _INDIAN_LANGUAGE_CODES and code != "hi":
        return "Joanna"
    return _INDIAN_POLLY_VOICES_BY_LANGUAGE_CODE.get(code, "Joanna")


def _polly_synthesize_segment_mp3(text: str, out_path: str, target_language_code: str) -> None:
    polly = _polly_client()
    voice = _pick_polly_voice(target_language_code)
    engine = os.getenv("POLLY_ENGINE", "neural")
    try:
        resp = polly.synthesize_speech(
            Text=text,
            OutputFormat="mp3",
            VoiceId=voice,
            Engine=engine,
            TextType="text",
        )
    except botocore.exceptions.ClientError as e:
        msg = e.response.get("Error", {}).get("Message", str(e))
        # Some voices (for example Aditi) do not support neural engine.
        # Fallback to standard automatically so translation flow does not fail.
        if engine.lower() == "neural" and "does not support the selected engine" in msg.lower():
            try:
                resp = polly.synthesize_speech(
                    Text=text,
                    OutputFormat="mp3",
                    VoiceId=voice,
                    Engine="standard",
                    TextType="text",
                )
            except botocore.exceptions.ClientError as inner:
                inner_msg = inner.response.get("Error", {}).get("Message", str(inner))
                raise RuntimeError(f"AWS Polly error: {inner_msg}") from inner
        else:
            raise RuntimeError(f"AWS Polly error: {msg}") from e

    stream = resp.get("AudioStream")
    if not stream:
        raise RuntimeError("AWS Polly returned no AudioStream.")
    data = stream.read()
    if not data:
        raise RuntimeError("AWS Polly returned empty audio.")
    with open(out_path, "wb") as f:
        f.write(data)


def _mix_segments_to_track(
    video_duration_s: float,
    segment_mp3_paths: List[str],
    segment_start_ms: List[int],
    out_aac_path: str,
) -> None:
    if len(segment_mp3_paths) != len(segment_start_ms):
        raise ValueError("segment_mp3_paths and segment_start_ms must have the same length.")

    args: List[str] = []
    # Base silent input sized to the video duration.
    args += ["-f", "lavfi", "-i", f"anullsrc=r=48000:cl=stereo:d={max(video_duration_s, 0.1)}"]
    for p in segment_mp3_paths:
        args += ["-i", p]

    # Build filter: delay each segment, then mix all together with silent base.
    filters: List[str] = []
    labels: List[str] = ["[0:a]"]
    for i, ms in enumerate(segment_start_ms, start=1):
        # adelay expects ms per channel. Use same for both channels.
        filters.append(f"[{i}:a]adelay={ms}|{ms},aformat=sample_fmts=fltp:sample_rates=48000:channel_layouts=stereo[s{i}]")
        labels.append(f"[s{i}]")
    amix_inputs = len(labels)
    gain = os.getenv("POLLY_TRACK_VOLUME_GAIN", "2.4").strip() or "2.4"
    filters.append(
        "".join(labels)
        + f"amix=inputs={amix_inputs}:duration=longest:dropout_transition=0,volume={gain}[m]"
    )

    _ffmpeg(
        *args,
        "-filter_complex",
        ";".join(filters),
        "-map",
        "[m]",
        "-c:a",
        "aac",
        "-b:a",
        "160k",
        out_aac_path,
    )


def _translate_video_audio_sync(
    video_base64: str,
    mime_type: str,
    target_language: str,
    keep_original_audio: bool,
) -> Tuple[str, str]:
    if not (video_base64 or "").strip():
        raise ValueError("video_base64 is required.")
    if not (mime_type or "").strip():
        raise ValueError("mime_type is required.")
    if not (target_language or "").strip():
        raise ValueError("target_language is required.")
    if not mime_type.startswith("video/"):
        raise ValueError("mime_type must start with 'video/'.")

    video_bytes = base64.b64decode(video_base64)

    with tempfile.TemporaryDirectory() as tmp:
        src_path = os.path.join(tmp, "input.mp4")
        audio_wav = os.path.join(tmp, "audio.wav")
        translated_aac = os.path.join(tmp, "translated.aac")
        out_path = os.path.join(tmp, "output.mp4")

        with open(src_path, "wb") as f:
            f.write(video_bytes)

        # Extract mono 16k WAV for Transcribe.
        _ffmpeg("-i", src_path, "-vn", "-acodec", "pcm_s16le", "-ar", "16000", "-ac", "1", audio_wav)

        # ASR + timestamps.
        segments = _transcribe_audio_s3(audio_wav)
        target_language_code = _resolve_target_code(target_language)

        # Translate + TTS per segment, then delay/mix according to timestamps.
        segment_paths: List[str] = []
        segment_delays_ms: List[int] = []
        for idx, seg in enumerate(segments):
            # Keep Polly requests reasonably sized.
            src_text = (seg.text or "").strip()
            if not src_text:
                continue
            if len(src_text) > 1500:
                src_text = src_text[:1500]
            translated = _translate_text_sync_auto(src_text, target_language_code)
            mp3_path = os.path.join(tmp, f"seg_{idx}.mp3")
            _polly_synthesize_segment_mp3(translated, mp3_path, target_language_code)
            segment_paths.append(mp3_path)
            segment_delays_ms.append(max(0, int(seg.start_s * 1000)))

        duration_s = _ffprobe_duration_seconds(src_path)
        if not segment_paths:
            raise RuntimeError("No transcribed segments were synthesized into audio.")

        _mix_segments_to_track(duration_s, segment_paths, segment_delays_ms, translated_aac)

        # Mux: keep original audio as extra track if requested.
        if keep_original_audio:
            _ffmpeg(
                "-i",
                src_path,
                "-i",
                translated_aac,
                "-map",
                "0:v:0",
                "-map",
                "0:a:0?",
                "-map",
                "1:a:0",
                "-c:v",
                "copy",
                "-c:a",
                "aac",
                "-shortest",
                out_path,
            )
        else:
            _ffmpeg(
                "-i",
                src_path,
                "-i",
                translated_aac,
                "-map",
                "0:v:0",
                "-map",
                "1:a:0",
                "-c:v",
                "copy",
                "-c:a",
                "aac",
                "-shortest",
                out_path,
            )

        with open(out_path, "rb") as f:
            out_b = f.read()

    return "video/mp4", base64.b64encode(out_b).decode("ascii")


async def translate_video_audio_base64(
    video_base64: str,
    mime_type: str,
    target_language: str,
    keep_original_audio: bool = True,
) -> Tuple[str, str]:
    return await asyncio.to_thread(
        _translate_video_audio_sync,
        video_base64,
        mime_type,
        target_language,
        keep_original_audio,
    )


__all__ = ["translate_video_audio_base64"]

