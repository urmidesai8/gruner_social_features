from typing import Dict

from fastapi import APIRouter, HTTPException

from app.models.schemas import (
    ChatRequest,
    ChatResponse,
    ImageCaptioningRequest,
    ImageCaptioningResponse,
    EnhanceImageRequest,
    EnhanceImageResponse,
    GenerateImageRequest,
    GenerateImageResponse,
)
from app.services.image_enhancement import enhance_image_base64
from app.services.image_generation import MODELS, generate_image_base64
from app.services.image_captioning import generate_image_caption_options
from app.api.deps import extract_prompt


router = APIRouter(prefix="/api", tags=["image"])


@router.get("/models")
async def list_models() -> Dict[str, list[str]]:
    return {"models": MODELS}


@router.post("/generate-image", response_model=GenerateImageResponse)
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


@router.post("/enhance-image", response_model=EnhanceImageResponse)
async def enhance_image(req: EnhanceImageRequest) -> EnhanceImageResponse:
    if not req.image_base64 or not req.image_base64.strip():
        raise HTTPException(status_code=400, detail="Missing image_base64.")
    try:
        prompt, mime_type, image_base64 = await enhance_image_base64(
            req.image_base64, req.prompt
        )
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e)) from e
    except RuntimeError as e:
        raise HTTPException(status_code=500, detail=str(e)) from e
    return EnhanceImageResponse(
        model="black-forest-labs/FLUX.2-klein-9b-kv",
        prompt=prompt,
        mime_type=mime_type,
        image_base64=image_base64,
    )


@router.post("/image-captioning", response_model=ImageCaptioningResponse)
async def image_captioning(req: ImageCaptioningRequest) -> ImageCaptioningResponse:
    if not req.image_base64 or not req.image_base64.strip():
        raise HTTPException(status_code=400, detail="Missing image_base64.")
    try:
        blip_caption, captions = await generate_image_caption_options(req.image_base64)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e)) from e
    except RuntimeError as e:
        raise HTTPException(status_code=500, detail=str(e)) from e

    return ImageCaptioningResponse(blip_caption=blip_caption, captions=captions)


@router.post("/chat", response_model=ChatResponse)
async def chat(req: ChatRequest) -> ChatResponse:
    prompt = extract_prompt(req)
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

