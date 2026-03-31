from typing import Optional

from app.models.schemas import ChatRequest


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

