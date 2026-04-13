from typing import Dict

from fastapi import APIRouter, HTTPException

from app.models.schemas import (
    GenerateVideoRequest,
    GenerateVideoResponse,
    VideoAudioTranslateRequest,
    VideoAudioTranslateResponse,
)
from app.services.video_audio_translation import translate_video_audio_base64
from app.services.video_generation import VIDEO_MODELS, generate_video_base64


router = APIRouter(prefix="/api", tags=["Video Related Features"])


@router.get("/video-models")
async def list_video_models() -> Dict[str, list[str]]:
    return {"models": VIDEO_MODELS}


@router.post("/generate-video", response_model=GenerateVideoResponse)
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


@router.post("/translate-video-audio", response_model=VideoAudioTranslateResponse)
async def translate_video_audio(req: VideoAudioTranslateRequest) -> VideoAudioTranslateResponse:
    if not (req.video_base64 or "").strip():
        raise HTTPException(status_code=400, detail="Missing video_base64.")
    if not (req.mime_type or "").strip():
        raise HTTPException(status_code=400, detail="Missing mime_type.")
    if not (req.target_language or "").strip():
        raise HTTPException(status_code=400, detail="Missing target_language.")

    try:
        mime_type, video_base64, translated_text = await translate_video_audio_base64(
            req.video_base64,
            req.mime_type,
            req.target_language,
            keep_original_audio=req.keep_original_audio,
        )
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e)) from e
    except RuntimeError as e:
        raise HTTPException(status_code=500, detail=str(e)) from e

    return VideoAudioTranslateResponse(
        mime_type=mime_type,
        video_base64=video_base64,
        translated_text=translated_text,
    )

