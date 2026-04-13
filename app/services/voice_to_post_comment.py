from __future__ import annotations

import asyncio
import json
import os
import time
import uuid
from typing import Literal

import boto3
import botocore.exceptions


_OutputKind = Literal["post", "comment"]


def _aws_creds() -> tuple[str, str, str]:
    access_key = os.getenv("AWS_ACCESS_KEY")
    secret_key = os.getenv("AWS_SECRET_KEY")
    region = os.getenv("AWS_REGION", "us-east-1")
    if not (access_key and secret_key):
        raise RuntimeError(
            "Missing AWS credentials in environment (AWS_ACCESS_KEY/AWS_SECRET_KEY)."
        )
    return access_key, secret_key, region


def _s3_client():
    access_key, secret_key, region = _aws_creds()
    return boto3.client(
        "s3",
        aws_access_key_id=access_key,
        aws_secret_access_key=secret_key,
        region_name=region,
    )


def _transcribe_client():
    access_key, secret_key, region = _aws_creds()
    return boto3.client(
        "transcribe",
        aws_access_key_id=access_key,
        aws_secret_access_key=secret_key,
        region_name=region,
    )


def _bedrock_client():
    access_key, secret_key, region = _aws_creds()
    return boto3.client(
        "bedrock-runtime",
        aws_access_key_id=access_key,
        aws_secret_access_key=secret_key,
        region_name=region,
    )


def _normalize_audio_base64(audio_base64: str) -> bytes:
    import base64

    raw = (audio_base64 or "").strip()
    if not raw:
        raise ValueError("audio_base64 is required.")
    if raw.startswith("data:"):
        _, _, raw = raw.partition(",")
    try:
        return base64.b64decode(raw)
    except Exception as e:  # noqa: BLE001
        raise ValueError("Invalid audio_base64 payload.") from e


def _extension_for_mime(mime_type: str) -> str:
    mt = (mime_type or "").strip().lower()
    if not mt:
        raise ValueError("mime_type is required.")
    mapping = {
        "audio/mpeg": "mp3",
        "audio/mp3": "mp3",
        "audio/mp4": "m4a",
        "audio/x-m4a": "m4a",
        "audio/wav": "wav",
        "audio/x-wav": "wav",
        "audio/webm": "webm",
        "audio/ogg": "ogg",
    }
    if mt in mapping:
        return mapping[mt]
    # fall back to best-effort extension from mime subtype
    if "/" in mt:
        subtype = mt.split("/", 1)[1].strip()
        if subtype:
            return subtype.replace("x-", "")
    return "bin"


def _upload_audio_and_transcribe_sync(
    audio_bytes: bytes,
    mime_type: str,
    language_code: str | None,
) -> str:
    bucket = (os.getenv("TRANSCRIBE_BUCKET") or "").strip()
    if not bucket:
        raise RuntimeError("Missing TRANSCRIBE_BUCKET environment variable.")

    file_ext = _extension_for_mime(mime_type)
    job_name = f"voice-to-post-comment-{uuid.uuid4().hex}"
    audio_key = f"voice-to-post-comment/{job_name}/input.{file_ext}"
    transcript_key = f"voice-to-post-comment/{job_name}/transcript.json"

    s3 = _s3_client()
    transcribe = _transcribe_client()

    try:
        s3.put_object(Bucket=bucket, Key=audio_key, Body=audio_bytes, ContentType=mime_type)
    except botocore.exceptions.ClientError as e:
        msg = e.response.get("Error", {}).get("Message", str(e))
        raise RuntimeError(f"Failed to upload audio to S3: {msg}") from e

    media_uri = f"s3://{bucket}/{audio_key}"
    try:
        start_kwargs = {
            "TranscriptionJobName": job_name,
            "Media": {"MediaFileUri": media_uri},
            "OutputBucketName": bucket,
            "OutputKey": transcript_key,
            "Settings": {"ShowSpeakerLabels": False, "ShowAlternatives": False},
        }
        if (language_code or "").strip():
            start_kwargs["LanguageCode"] = language_code
        else:
            # Auto-detect language when the caller does not provide one.
            start_kwargs["IdentifyLanguage"] = True
        transcribe.start_transcription_job(
            **start_kwargs
        )
    except botocore.exceptions.ClientError as e:
        msg = e.response.get("Error", {}).get("Message", str(e))
        raise RuntimeError(f"AWS Transcribe error: {msg}") from e

    timeout_seconds = float(os.getenv("TRANSCRIBE_TIMEOUT_SECONDS", "300"))
    deadline = time.time() + timeout_seconds
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

    transcript = (
        ((payload.get("results") or {}).get("transcripts") or [{}])[0].get("transcript") or ""
    )
    transcript = str(transcript).strip()
    if not transcript:
        raise RuntimeError("AWS Transcribe returned empty transcript.")
    return transcript


def _cleanup_with_claude_sync(raw_transcript: str, output_kind: _OutputKind) -> str:
    model_id = (os.getenv("BEDROCK_CLAUDE_SONNET_ID") or "").strip()
    if not model_id:
        raise RuntimeError("Missing BEDROCK_CLAUDE_SONNET_ID in environment.")

    if output_kind == "comment":
        format_instruction = (
            "Rewrite the raw speech into a polished social media comment. "
            "Keep it concise (1-3 sentences), natural, and conversational."
        )
    else:
        format_instruction = (
            "Rewrite the raw speech into a clean social media post. "
            "Keep the intent and voice, but improve grammar, clarity, and flow. "
            "Output should read like a direct post caption, not an assistant reply."
        )

    system_prompt = (
        "You are an editor that converts voice transcripts into polished social text.\n"
        f"{format_instruction}\n"
        "Rules:\n"
        "- Return only the final text.\n"
        "- Always rewrite the transcript into a cleaner version; do not copy it verbatim.\n"
        "- If the transcript is already grammatically correct, lightly rephrase and improve tone.\n"
        "- Remove filler words, repeated fragments, and transcription artifacts.\n"
        "- Preserve meaning and key facts.\n"
        "- For comments, sound warm and human, like a real reaction to a post.\n"
        "- Do NOT add preambles like 'Here's', 'Here is', 'I would say', or any quotation wrappers.\n"
        "- Start directly with the post/comment content.\n"
        "- Do not add hashtags or emojis unless clearly spoken by user intent."
    )

    body = {
        "anthropic_version": "bedrock-2023-05-31",
        "max_tokens": 500,
        "temperature": 0.4,
        "system": system_prompt,
        "messages": [
            {
                "role": "user",
                "content": [{"type": "text", "text": f"Raw transcript:\n{raw_transcript}"}],
            }
        ],
    }

    bedrock = _bedrock_client()
    try:
        response = bedrock.invoke_model(
            modelId=model_id,
            body=json.dumps(body),
            accept="application/json",
            contentType="application/json",
        )
    except botocore.exceptions.ClientError as e:
        msg = e.response.get("Error", {}).get("Message", str(e))
        raise RuntimeError(f"Bedrock Claude error: {msg}") from e

    payload = json.loads(response["body"].read())
    content = payload.get("content", [])
    parts = [part.get("text", "") for part in content if isinstance(part, dict)]
    cleaned = "\n".join(p.strip() for p in parts if p.strip()).strip()
    if not cleaned:
        raise RuntimeError("Claude returned empty cleaned text.")
    return cleaned


def _voice_to_post_comment_sync(
    audio_base64: str,
    mime_type: str,
    output_kind: _OutputKind,
    language_code: str | None,
) -> dict[str, str]:
    normalized_kind = (output_kind or "").strip().lower()
    if normalized_kind not in ("post", "comment"):
        raise ValueError("output_kind must be either 'post' or 'comment'.")

    normalized_lang = (language_code or "").strip()

    audio_bytes = _normalize_audio_base64(audio_base64)
    raw_transcript = _upload_audio_and_transcribe_sync(audio_bytes, mime_type, normalized_lang)
    final_text = _cleanup_with_claude_sync(raw_transcript, normalized_kind)  # type: ignore[arg-type]
    return {
        "raw_transcript": raw_transcript,
        "final_text": final_text,
        "output_kind": normalized_kind,
        "language_code": normalized_lang or "auto",
    }


async def voice_to_post_comment(
    audio_base64: str,
    mime_type: str,
    output_kind: _OutputKind = "post",
    language_code: str | None = None,
) -> dict[str, str]:
    return await asyncio.to_thread(
        _voice_to_post_comment_sync,
        audio_base64,
        mime_type,
        output_kind,
        language_code,
    )


__all__ = ["voice_to_post_comment"]

