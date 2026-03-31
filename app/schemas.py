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


class ChatResponse(BaseModel):
    model: str
    reply: str
    mime_type: Optional[str] = None
    image_base64: Optional[str] = None

