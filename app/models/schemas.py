from enum import Enum
from typing import List, Literal, Optional

from pydantic import BaseModel, Field


class ChatMessage(BaseModel):
    role: Literal["user", "assistant", "system"] = "user"
    content: str


class ChatRequest(BaseModel):
    model: str
    messages: List[ChatMessage] = Field(default_factory=list)
    prompt: Optional[str] = None


class GenerateImageRequest(BaseModel):
    model: str
    prompt: str


class GenerateImageResponse(BaseModel):
    model: str
    prompt: str
    mime_type: str
    image_base64: str


class EnhanceImageRequest(BaseModel):
    image_base64: str
    mime_type: Optional[str] = None
    prompt: Optional[str] = Field(
        default=None,
        description="Optional edits (e.g. color grade, crop, object changes) in addition to default enhancement.",
    )


class EnhanceImageResponse(BaseModel):
    model: str
    prompt: str
    mime_type: str
    image_base64: str


class GenerateVideoRequest(BaseModel):
    model: str
    prompt: str


class GenerateVideoResponse(BaseModel):
    model: str
    prompt: str
    mime_type: str
    video_base64: str


class GenerateQuoteCardRequest(BaseModel):
    prompt: str


class GenerateQuoteCardResponse(BaseModel):
    prompt: str
    quote_text: str
    mime_type: str
    image_base64: str


class CopilotMode(str, Enum):
    GENERATE = "generate"
    REWRITE = "rewrite"
    IDEAS = "ideas"


class ContentCopilotRequest(BaseModel):
    mode: CopilotMode = CopilotMode.GENERATE
    text: str


class ContentCopilotResponse(BaseModel):
    mode: CopilotMode
    original_text: str
    result: str


class SummarizePostRequest(BaseModel):
    text: str = Field(..., description="Long post or article excerpt to summarise in plain language.")


class SummarizePostResponse(BaseModel):
    original_text: str
    result: str


class ImageCaptioningRequest(BaseModel):
    image_base64: str
    mime_type: Optional[str] = None


class ImageCaptioningResponse(BaseModel):
    blip_caption: str
    captions: dict[str, str]


class ChatResponse(BaseModel):
    model: str
    reply: str
    mime_type: Optional[str] = None
    image_base64: Optional[str] = None

