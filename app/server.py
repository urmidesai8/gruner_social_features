from pathlib import Path
from typing import Optional

from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles

from app.ai import MODELS, generate_image_base64
from app.text import generate_quote_card_base64
from app.video import VIDEO_MODELS, generate_video_base64
from app.schemas import (
    ChatRequest, ChatResponse, 
    GenerateImageRequest, GenerateImageResponse,
    GenerateVideoRequest, GenerateVideoResponse,
    GenerateQuoteCardRequest, GenerateQuoteCardResponse,
)

BASE_DIR = Path(__file__).resolve().parent
STATIC_DIR = BASE_DIR / "static"

app = FastAPI(title="Gruner Social AI Features")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=False,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.mount("/static", StaticFiles(directory=str(STATIC_DIR)), name="static")


@app.get("/api/ping")
async def ping() -> dict:
    return {"status": "ok"}


@app.get("/api/models")
async def list_models() -> dict:
    return {"models": MODELS}


@app.get("/api/video-models")
async def list_video_models() -> dict:
    return {"models": VIDEO_MODELS}


@app.post("/api/generate-image", response_model=GenerateImageResponse)
async def generate_image(req: GenerateImageRequest) -> GenerateImageResponse:
    try:
        mime_type, image_base64 = await generate_image_base64(req.model, req.prompt)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e)) from e
    except RuntimeError as e:
        raise HTTPException(status_code=500, detail=str(e)) from e
    return GenerateImageResponse(
        model=req.model,
        prompt=req.prompt,
        mime_type=mime_type,
        image_base64=image_base64,
    )


@app.post("/api/generate-video", response_model=GenerateVideoResponse)
async def generate_video(req: GenerateVideoRequest) -> GenerateVideoResponse:
    try:
        mime_type, video_base64 = await generate_video_base64(req.model, req.prompt)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e)) from e
    except RuntimeError as e:
        raise HTTPException(status_code=500, detail=str(e)) from e
    return GenerateVideoResponse(
        model=req.model,
        prompt=req.prompt,
        mime_type=mime_type,
        video_base64=video_base64,
    )


@app.post("/api/generate-quote-card", response_model=GenerateQuoteCardResponse)
async def generate_quote_card(req: GenerateQuoteCardRequest) -> GenerateQuoteCardResponse:
    prompt = (req.prompt or "").strip()
    if not prompt:
        raise HTTPException(status_code=400, detail="Missing prompt.")
    try:
        quote_text, mime_type, image_base64 = await generate_quote_card_base64(prompt)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e)) from e
    except RuntimeError as e:
        raise HTTPException(status_code=500, detail=str(e)) from e

    return GenerateQuoteCardResponse(
        prompt=prompt,
        quote_text=quote_text,
        mime_type=mime_type,
        image_base64=image_base64,
    )

def _extract_prompt(req: ChatRequest) -> Optional[str]:
    if req.prompt:
        return req.prompt
    for msg in reversed(req.messages):
        if msg.role == "user":
            return msg.content
    return None


@app.post("/api/chat", response_model=ChatResponse)
async def chat(req: ChatRequest) -> ChatResponse:
    prompt = _extract_prompt(req)
    if not prompt or not prompt.strip():
        raise HTTPException(status_code=400, detail="Missing prompt/messages.")

    try:
        mime_type, image_base64 = await generate_image_base64(req.model, prompt)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e)) from e
    except RuntimeError as e:
        raise HTTPException(status_code=500, detail=str(e)) from e

    reply = f"Generated an image using {req.model}."
    return ChatResponse(
        model=req.model,
        reply=reply,
        mime_type=mime_type,
        image_base64=image_base64,
    )


@app.get("/")
def ui_home():
    return FileResponse(str(STATIC_DIR / "index.html"))

