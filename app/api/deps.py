from typing import Annotated, Optional

from fastapi import Header, HTTPException

from app.models.schemas import ChatRequest


def get_audit_user_id(
    x_user_id: Annotated[str | None, Header(alias="X-User-Id")] = None,
) -> str:
    """Explicit user identifier for AI audit logging (required on audited endpoints)."""
    uid = (x_user_id or "").strip()
    if not uid:
        raise HTTPException(
            status_code=400,
            detail="Missing X-User-Id header (required for AI audit logging).",
        )
    return uid


def extract_prompt(req: ChatRequest) -> Optional[str]:
    """
    Extract the effective user prompt from a ChatRequest.
    Mirrors the legacy _extract_prompt helper from app.server.
    """
    if req.prompt:
        return req.prompt
    for msg in reversed(req.messages):
        if msg.role == "user":
            return msg.content
    return None

