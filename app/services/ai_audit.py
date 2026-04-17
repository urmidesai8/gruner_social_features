"""
Append-only audit logging for AI feature requests into PostgreSQL table
`gruner_social_dev_ai_audit`.

`request_payload` stores the full request body as JSON (no truncation).
`response_payload` remains a summarized form (base64 replaced by fingerprints; large text truncated for DB practicality).
"""

from __future__ import annotations

import base64
import hashlib
import json
import logging
from typing import Any, Mapping

from fastapi import BackgroundTasks, Request

from app.core.config import settings

logger = logging.getLogger("uvicorn.error")

AUDIT_TABLE = "gruner_social_dev_ai_audit"


def request_payload_full(req: Any) -> dict[str, Any]:
    """Full request body for audit JSONB (Pydantic models or plain dicts)."""
    if hasattr(req, "model_dump"):
        return req.model_dump(mode="json")
    if isinstance(req, dict):
        return dict(req)
    return {}


def media_field_summary(
    b64: str | None,
    field_name: str,
    mime_type: str | None = None,
) -> dict[str, Any] | None:
    if not b64 or not str(b64).strip():
        return None
    raw = str(b64).strip()
    if raw.startswith("data:"):
        _, _, raw = raw.partition(",")
    try:
        decoded = base64.b64decode(raw, validate=False)
    except Exception:
        return {
            "field_name": field_name,
            "present": True,
            "decode_error": True,
            "base64_char_length": len(raw),
            "mime_type": mime_type,
        }
    digest = hashlib.sha256(decoded).hexdigest()
    return {
        "field_name": field_name,
        "present": True,
        "mime_type": mime_type,
        "decoded_byte_length": len(decoded),
        "base64_char_length": len(raw),
        "content_sha256_hex": digest,
    }


def _strip_large_b64_from_mapping(data: Mapping[str, Any]) -> dict[str, Any]:
    out: dict[str, Any] = {}
    for k, v in data.items():
        if isinstance(v, str) and (
            k.endswith("_base64") or k == "image_base64" or k == "video_base64" or k == "audio_base64"
        ):
            summary = media_field_summary(v, field_name=k)
            if summary:
                out[k] = summary
            else:
                out[k] = None
        elif isinstance(v, dict):
            out[k] = _strip_large_b64_from_mapping(v)
        elif isinstance(v, list):
            out[k] = [
                _strip_large_b64_from_mapping(x) if isinstance(x, dict) else x for x in v[:500]
            ]
        else:
            out[k] = v
    return out


def summarize_response_dict(data: Mapping[str, Any]) -> dict[str, Any]:
    """Response summary for JSONB: replace base64 with fingerprints; truncate very long text."""
    cleaned = _strip_large_b64_from_mapping(dict(data))
    for text_key in (
        "result",
        "translated_text",
        "combined_caption",
        "quote_text",
        "reply",
        "raw_transcript",
        "final_text",
        "original_text",
        "blip_caption",
        "text_caption",
        "image_caption",
        "video_caption",
        "prompt",
    ):
        if text_key in cleaned and isinstance(cleaned[text_key], str):
            s = cleaned[text_key]
            if len(s) > 500:
                cleaned[text_key] = s[:497] + "..."
    if "captions" in cleaned and isinstance(cleaned["captions"], dict):
        cap = cleaned["captions"]
        if len(json.dumps(cap)) > 2000:
            cleaned["captions"] = {"_truncated": True, "keys": list(cap.keys())[:20]}
    if "hashtags" in cleaned and isinstance(cleaned["hashtags"], list):
        tags = cleaned["hashtags"]
        cleaned["hashtags"] = tags[:30]
        cleaned["hashtags_count"] = len(tags)
    return cleaned


def insert_audit_row_sync(
    *,
    user_id: str,
    endpoint: str,
    http_method: str,
    feature_name: str,
    model_name: str | None,
    request_payload: dict[str, Any] | None,
    response_payload: dict[str, Any] | None,
    status_code: int,
    success: bool,
    guardrail_blocked: bool,
    guardrail_action: str | None,
    error_message: str | None,
    latency_ms: int | None,
    client_ip: str | None,
    user_agent: str | None,
) -> None:
    dsn = (settings.database_url or "").strip()
    if not dsn:
        return
    try:
        import psycopg
        from psycopg.types.json import Json
    except ImportError:
        logger.warning("ai_audit: psycopg not installed, skipping audit insert")
        return

    try:
        with psycopg.connect(dsn, connect_timeout=10) as conn:
            with conn.cursor() as cur:
                cur.execute(
                    f"""
                    INSERT INTO {AUDIT_TABLE} (
                        user_id, endpoint, http_method, feature_name, model_name,
                        request_payload, response_payload,
                        status_code, success, guardrail_blocked, guardrail_action,
                        error_message, latency_ms, client_ip, user_agent
                    ) VALUES (
                        %(user_id)s, %(endpoint)s, %(http_method)s, %(feature_name)s, %(model_name)s,
                        %(request_payload)s, %(response_payload)s,
                        %(status_code)s, %(success)s, %(guardrail_blocked)s, %(guardrail_action)s,
                        %(error_message)s, %(latency_ms)s, %(client_ip)s, %(user_agent)s
                    )
                    """,
                    {
                        "user_id": user_id,
                        "endpoint": endpoint,
                        "http_method": http_method,
                        "feature_name": feature_name,
                        "model_name": model_name,
                        "request_payload": Json(request_payload or {}),
                        "response_payload": (
                            Json(response_payload) if response_payload is not None else None
                        ),
                        "status_code": status_code,
                        "success": success,
                        "guardrail_blocked": guardrail_blocked,
                        "guardrail_action": guardrail_action,
                        "error_message": error_message,
                        "latency_ms": latency_ms,
                        "client_ip": client_ip,
                        "user_agent": (user_agent or "")[:2048] or None,
                    },
                )
            conn.commit()
    except Exception:
        logger.exception("ai_audit: failed to insert row for feature=%s endpoint=%s", feature_name, endpoint)


def schedule_ai_audit(
    background_tasks: BackgroundTasks,
    *,
    request: Request,
    user_id: str,
    feature_name: str,
    endpoint: str,
    http_method: str,
    model_name: str | None,
    request_payload: dict[str, Any] | None,
    response_payload: dict[str, Any] | None,
    status_code: int,
    success: bool,
    guardrail_blocked: bool,
    error_message: str | None,
    latency_ms: int | None,
) -> None:
    if not (settings.database_url or "").strip():
        return
    guardrail_action = "intervened" if guardrail_blocked else None
    client_ip = request.client.host if request.client else None
    ua = request.headers.get("user-agent")
    background_tasks.add_task(
        insert_audit_row_sync,
        user_id=user_id,
        endpoint=endpoint,
        http_method=http_method,
        feature_name=feature_name,
        model_name=model_name,
        request_payload=request_payload,
        response_payload=response_payload,
        status_code=status_code,
        success=success,
        guardrail_blocked=guardrail_blocked,
        guardrail_action=guardrail_action,
        error_message=error_message,
        latency_ms=latency_ms,
        client_ip=client_ip,
        user_agent=ua,
    )
