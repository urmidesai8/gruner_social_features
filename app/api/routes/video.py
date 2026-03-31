from typing import Dict

from fastapi import APIRouter, HTTPException

from app.models.schemas import GenerateVideoRequest, GenerateVideoResponse
from app.services.video import VIDEO_MODELS, generate_video_base64


router = APIRouter(prefix="/api", tags=["video"])


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

