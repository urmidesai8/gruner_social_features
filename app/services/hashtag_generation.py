from __future__ import annotations

import asyncio
import base64
import json
import os
import subprocess
import tempfile
import time
import uuid

import botocore.exceptions

from app.core.config import settings
from app.services.aws_clients import (
    bedrock_guardrail_precheck_text,
    bedrock_invoke_model,
    bedrock_runtime_client,
    s3_client,
    transcribe_client,
)
from app.services.image_captioning import generate_blip_caption


def _normalize_base64_payload(data: str, field_name: str) -> bytes:
    raw = (data or "").strip()
    if not raw:
        raise ValueError(f"{field_name} is required.")
    if raw.startswith("data:"):
        _, _, raw = raw.partition(",")
    try:
        return base64.b64decode(raw)
    except Exception as e:  # noqa: BLE001
        raise ValueError(f"Invalid {field_name} payload.") from e


def _run(cmd: list[str]) -> None:
    try:
        proc = subprocess.run(cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE, check=False)
    except FileNotFoundError as e:
        raise RuntimeError(f"Missing executable: {cmd[0]!r}. Install it and ensure it is on PATH.") from e
    if proc.returncode != 0:
        stderr = (proc.stderr or b"").decode("utf-8", "ignore")
        raise RuntimeError(f"{cmd[0]} failed: {stderr}")


def _video_has_audio_stream(video_path: str) -> bool:
    try:
        proc = subprocess.run(
            [
                "ffprobe",
                "-v",
                "error",
                "-select_streams",
                "a",
                "-show_entries",
                "stream=index",
                "-of",
                "csv=p=0",
                video_path,
            ],
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            check=False,
        )
    except FileNotFoundError as e:
        raise RuntimeError("Missing executable: 'ffprobe'. Install FFmpeg and ensure it is on PATH.") from e

    if proc.returncode != 0:
        stderr = (proc.stderr or b"").decode("utf-8", "ignore")
        raise RuntimeError(f"ffprobe failed: {stderr}")

    out = (proc.stdout or b"").decode("utf-8", "ignore").strip()
    return bool(out)


def _extract_audio_wav_sync(video_bytes: bytes) -> str:
    with tempfile.TemporaryDirectory() as tmp:
        video_path = os.path.join(tmp, "input.mp4")
        audio_wav = os.path.join(tmp, "audio.wav")
        with open(video_path, "wb") as f:
            f.write(video_bytes)
        if not _video_has_audio_stream(video_path):
            raise ValueError(
                "Uploaded video has no audio stream. Please upload a video with speech/audio for transcription."
            )
        _run(["ffmpeg", "-y", "-i", video_path, "-vn", "-acodec", "pcm_s16le", "-ar", "16000", "-ac", "1", audio_wav])
        with open(audio_wav, "rb") as f:
            return base64.b64encode(f.read()).decode("ascii")


def _upload_audio_and_transcribe_sync(
    audio_bytes: bytes,
    precheck_text: str | None = None,
) -> str:
    bucket = (settings.transcribe_bucket or "").strip()
    if not bucket:
        raise RuntimeError("Missing TRANSCRIBE_BUCKET environment variable.")

    job_name = f"hashtag-generation-{uuid.uuid4().hex}"
    audio_key = f"hashtag-generation/{job_name}/audio.wav"
    transcript_key = f"hashtag-generation/{job_name}/transcript.json"

    s3 = s3_client(region_name=settings.aws_region)
    transcribe = transcribe_client(region_name=settings.aws_region)

    try:
        s3.put_object(Bucket=bucket, Key=audio_key, Body=audio_bytes, ContentType="audio/wav")
    except botocore.exceptions.ClientError as e:
        msg = e.response.get("Error", {}).get("Message", str(e))
        raise RuntimeError(f"Failed to upload audio to S3: {msg}") from e

    bedrock_guardrail_precheck_text(
        (precheck_text or "").strip(),
        context_label="hashtag transcribe request context",
    )

    try:
        start_kwargs = {
            "TranscriptionJobName": job_name,
            "Media": {"MediaFileUri": f"s3://{bucket}/{audio_key}"},
            "OutputBucketName": bucket,
            "OutputKey": transcript_key,
            "Settings": {"ShowSpeakerLabels": False, "ShowAlternatives": False},
        }
        configured_lang = (settings.transcribe_language_code or "").strip()
        if configured_lang:
            start_kwargs["LanguageCode"] = configured_lang
        else:
            start_kwargs["IdentifyLanguage"] = True
        transcribe.start_transcription_job(**start_kwargs)
    except botocore.exceptions.ClientError as e:
        msg = e.response.get("Error", {}).get("Message", str(e))
        raise RuntimeError(f"AWS Transcribe error: {msg}") from e

    deadline = time.time() + float(settings.transcribe_timeout_seconds)
    while True:
        if time.time() > deadline:
            raise RuntimeError("AWS Transcribe timed out waiting for transcription job completion.")
        status_resp = transcribe.get_transcription_job(TranscriptionJobName=job_name)
        status = status_resp["TranscriptionJob"]["TranscriptionJobStatus"]
        if status in ("COMPLETED", "FAILED"):
            if status == "FAILED":
                reason = status_resp["TranscriptionJob"].get("FailureReason", "unknown")
                raise RuntimeError(f"AWS Transcribe failed: {reason}")
            break
        time.sleep(2.0)

    try:
        obj = s3.get_object(Bucket=bucket, Key=transcript_key)
        payload = json.loads(obj["Body"].read().decode("utf-8"))
    except botocore.exceptions.ClientError as e:
        msg = e.response.get("Error", {}).get("Message", str(e))
        raise RuntimeError(f"Failed to fetch transcript from S3: {msg}") from e

    transcript = (((payload.get("results") or {}).get("transcripts") or [{}])[0].get("transcript") or "").strip()
    if not transcript:
        raise RuntimeError("AWS Transcribe returned empty transcript.")
    return transcript


def _hashtags_with_sonnet_sync(combined_caption: str) -> list[str]:
    model_id = (settings.bedrock_claude_sonnet_id or "").strip()
    if not model_id:
        raise RuntimeError("Missing BEDROCK_CLAUDE_SONNET_ID in environment.")

    bedrock = bedrock_runtime_client(region_name=settings.aws_region)
    system_prompt = (
        "You generate social media hashtags.\n"
        "Return ONLY valid JSON in this exact shape:\n"
        '{"hashtags": ["#one", "#two"]}\n'
        "Rules:\n"
        "- Generate 10-18 relevant hashtags.\n"
        "- Every hashtag must start with # and use only letters/numbers/underscore.\n"
        "- No spaces, punctuation, duplicates, or explanation text.\n"
        "- Prefer broad + niche tags mix."
    )
    body = {
        "anthropic_version": "bedrock-2023-05-31",
        "max_tokens": 350,
        "temperature": 0.4,
        "system": system_prompt,
        "messages": [
            {
                "role": "user",
                "content": [{"type": "text", "text": f"Content context:\n{combined_caption}"}],
            }
        ],
    }

    try:
        response = bedrock_invoke_model(
            bedrock,
            modelId=model_id,
            body=json.dumps(body),
            accept="application/json",
            contentType="application/json",
        )
    except botocore.exceptions.ClientError as e:
        msg = e.response.get("Error", {}).get("Message", str(e))
        raise RuntimeError(f"Bedrock Claude Sonnet error: {msg}") from e

    payload = json.loads(response["body"].read())
    content = payload.get("content", [])
    raw_text = "\n".join(part.get("text", "").strip() for part in content if isinstance(part, dict)).strip()
    if not raw_text:
        raise RuntimeError("Claude Sonnet returned empty hashtag content.")

    try:
        parsed = json.loads(raw_text)
    except json.JSONDecodeError:
        lower_raw = raw_text.lower()
        guardrail_markers = (
            "guardrail",
            "safety",
            "policy",
            "cannot help",
            "can't help",
            "cannot assist",
            "can't assist",
            "not able to comply",
            "not able to provide",
            "blocked",
        )
        if any(marker in lower_raw for marker in guardrail_markers):
            raise ValueError("Content was blocked by safety guardrails.")
        start = raw_text.find("{")
        end = raw_text.rfind("}")
        if start == -1 or end == -1 or end <= start:
            raise RuntimeError("Claude Sonnet returned non-JSON hashtag output.")
        parsed = json.loads(raw_text[start : end + 1])

    values = parsed.get("hashtags") if isinstance(parsed, dict) else None
    if not isinstance(values, list):
        raise RuntimeError("Claude Sonnet hashtag output format is invalid.")

    cleaned: list[str] = []
    seen: set[str] = set()
    for value in values:
        tag = str(value or "").strip()
        if not tag:
            continue
        if not tag.startswith("#"):
            tag = f"#{tag}"
        normalized = "".join(ch for ch in tag if ch.isalnum() or ch in {"#", "_"})
        if not normalized.startswith("#") or len(normalized) <= 1:
            continue
        key = normalized.lower()
        if key in seen:
            continue
        seen.add(key)
        cleaned.append(normalized)
    if not cleaned:
        raise RuntimeError("Claude Sonnet returned no valid hashtags.")
    return cleaned


async def generate_hashtags(
    text_caption: str | None = None,
    media_image: str | None = None,
    media_video: str | None = None,
) -> dict[str, object]:
    text = (text_caption or "").strip()
    has_image = bool((media_image or "").strip())
    has_video = bool((media_video or "").strip())
    if not (text or has_image or has_video):
        raise ValueError(
            "Missing input. Provide at least one of text_caption, media_image, or media_video."
        )

    captions: list[str] = []
    used_sources: list[str] = []
    if text:
        bedrock_guardrail_precheck_text(text, context_label="hashtag text_caption")
        captions.append(text)
        used_sources.append("text_caption")
    image_caption = ""
    video_caption = ""

    if has_image:
        image_caption = await generate_blip_caption(media_image or "")
        if image_caption:
            captions.append(image_caption)
            used_sources.append("media_image")

    if has_video:
        video_bytes = _normalize_base64_payload(media_video or "", "media_video")
        audio_wav_base64 = await asyncio.to_thread(_extract_audio_wav_sync, video_bytes)
        audio_bytes = base64.b64decode(audio_wav_base64)
        video_caption = await asyncio.to_thread(
            _upload_audio_and_transcribe_sync,
            audio_bytes,
            f"Hashtag generation request context. text_caption={text}",
        )
        if video_caption:
            captions.append(video_caption)
            used_sources.append("media_video")

    combined_caption = "\n".join(f"- {part}" for part in captions if (part or "").strip()).strip()
    if not combined_caption:
        raise RuntimeError("No caption content available for hashtag generation.")
    bedrock_guardrail_precheck_text(
        combined_caption,
        context_label="hashtag combined caption",
    )

    hashtags = await asyncio.to_thread(_hashtags_with_sonnet_sync, combined_caption)
    return {
        "hashtags": hashtags,
        "combined_caption": combined_caption,
        "used_sources": used_sources,
        "text_caption": text,
        "image_caption": image_caption,
        "video_caption": video_caption,
    }


__all__ = ["generate_hashtags"]
