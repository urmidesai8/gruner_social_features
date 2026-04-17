import time
from typing import Dict

from fastapi import APIRouter, BackgroundTasks, Depends, HTTPException, Request

from app.api.deps import extract_prompt, get_audit_user_id
from app.models.schemas import (
    ChatRequest,
    ChatResponse,
    EnhanceImageRequest,
    EnhanceImageResponse,
    GenerateImageRequest,
    GenerateImageResponse,
    ImageCaptioningRequest,
    ImageCaptioningResponse,
)
from app.services import ai_audit
from app.services.aws_clients import redact_text_if_guardrail_blocked
from app.services.image_captioning import generate_image_caption_options
from app.services.image_enhancement import enhance_image_base64
from app.services.image_generation import MODELS, generate_image_base64


router = APIRouter(prefix="/api", tags=["Image Related Features"])


@router.get("/models")
async def list_models() -> Dict[str, list[str]]:
    return {"models": MODELS}


@router.post("/generate-image", response_model=GenerateImageResponse)
async def generate_image(
    req: GenerateImageRequest,
    request: Request,
    background_tasks: BackgroundTasks,
    user_id: str = Depends(get_audit_user_id),
) -> GenerateImageResponse:
    t0 = time.perf_counter()
    resp: GenerateImageResponse | None = None
    err_detail: str | None = None
    status = 200
    success = True
    guardrail_blocked = False
    try:
        mime_type, image_base64, guardrail_blocked = await generate_image_base64(req.model, req.prompt)
        resp = GenerateImageResponse(
            model=req.model,
            prompt=redact_text_if_guardrail_blocked(
                req.prompt,
                context_label="image generation prompt echo",
                run_guardrail_precheck=not req.model.startswith("amazon."),
                blocked_by_guardrail=guardrail_blocked,
            ),
            mime_type=mime_type,
            image_base64=image_base64,
        )
        return resp
    except HTTPException as e:
        status = e.status_code
        success = False
        err_detail = e.detail if isinstance(e.detail, str) else str(e.detail)
        raise
    except Exception as e:
        status = 500
        success = False
        err_detail = str(e)
        raise
    finally:
        latency_ms = int((time.perf_counter() - t0) * 1000)
        res_pl = ai_audit.summarize_response_dict(resp.model_dump()) if resp else None
        ai_audit.schedule_ai_audit(
            background_tasks,
            request=request,
            user_id=user_id,
            feature_name="generate_image",
            endpoint="/api/generate-image",
            http_method="POST",
            model_name=req.model,
            request_payload=ai_audit.request_payload_full(req),
            response_payload=res_pl,
            status_code=status,
            success=success,
            guardrail_blocked=guardrail_blocked,
            error_message=err_detail,
            latency_ms=latency_ms,
        )


@router.post("/enhance-image", response_model=EnhanceImageResponse)
async def enhance_image(
    req: EnhanceImageRequest,
    request: Request,
    background_tasks: BackgroundTasks,
    user_id: str = Depends(get_audit_user_id),
) -> EnhanceImageResponse:
    if not req.image_base64 or not req.image_base64.strip():
        ai_audit.schedule_ai_audit(
            background_tasks,
            request=request,
            user_id=user_id,
            feature_name="enhance_image",
            endpoint="/api/enhance-image",
            http_method="POST",
            model_name="black-forest-labs/FLUX.2-klein-9b-kv",
            request_payload=ai_audit.request_payload_full(req),
            response_payload=None,
            status_code=400,
            success=False,
            guardrail_blocked=False,
            error_message="Missing image_base64.",
            latency_ms=0,
        )
        raise HTTPException(status_code=400, detail="Missing image_base64.")

    t0 = time.perf_counter()
    resp: EnhanceImageResponse | None = None
    err_detail: str | None = None
    status = 200
    success = True
    guardrail_blocked = False
    try:
        prompt, mime_type, image_base64 = await enhance_image_base64(
            req.image_base64, req.prompt
        )
        resp = EnhanceImageResponse(
            model="black-forest-labs/FLUX.2-klein-9b-kv",
            prompt=redact_text_if_guardrail_blocked(
                prompt,
                context_label="image enhancement prompt echo",
                run_guardrail_precheck=True,
            ),
            mime_type=mime_type,
            image_base64=image_base64,
        )
        return resp
    except HTTPException as e:
        status = e.status_code
        success = False
        err_detail = e.detail if isinstance(e.detail, str) else str(e.detail)
        raise
    except Exception as e:
        status = 500
        success = False
        err_detail = str(e)
        raise
    finally:
        latency_ms = int((time.perf_counter() - t0) * 1000)
        res_pl = ai_audit.summarize_response_dict(resp.model_dump()) if resp else None
        ai_audit.schedule_ai_audit(
            background_tasks,
            request=request,
            user_id=user_id,
            feature_name="enhance_image",
            endpoint="/api/enhance-image",
            http_method="POST",
            model_name="black-forest-labs/FLUX.2-klein-9b-kv",
            request_payload=ai_audit.request_payload_full(req),
            response_payload=res_pl,
            status_code=status,
            success=success,
            guardrail_blocked=guardrail_blocked,
            error_message=err_detail,
            latency_ms=latency_ms,
        )


@router.post("/image-captioning", response_model=ImageCaptioningResponse)
async def image_captioning(
    req: ImageCaptioningRequest,
    request: Request,
    background_tasks: BackgroundTasks,
    user_id: str = Depends(get_audit_user_id),
) -> ImageCaptioningResponse:
    if not req.image_base64 or not req.image_base64.strip():
        ai_audit.schedule_ai_audit(
            background_tasks,
            request=request,
            user_id=user_id,
            feature_name="image_captioning",
            endpoint="/api/image-captioning",
            http_method="POST",
            model_name=None,
            request_payload=ai_audit.request_payload_full(req),
            response_payload=None,
            status_code=400,
            success=False,
            guardrail_blocked=False,
            error_message="Missing image_base64.",
            latency_ms=0,
        )
        raise HTTPException(status_code=400, detail="Missing image_base64.")

    t0 = time.perf_counter()
    resp: ImageCaptioningResponse | None = None
    err_detail: str | None = None
    status = 200
    success = True
    guardrail_blocked = False
    try:
        blip_caption, captions = await generate_image_caption_options(req.image_base64)
        resp = ImageCaptioningResponse(blip_caption=blip_caption, captions=captions)
        return resp
    except HTTPException as e:
        status = e.status_code
        success = False
        err_detail = e.detail if isinstance(e.detail, str) else str(e.detail)
        raise
    except Exception as e:
        status = 500
        success = False
        err_detail = str(e)
        raise
    finally:
        latency_ms = int((time.perf_counter() - t0) * 1000)
        res_pl = ai_audit.summarize_response_dict(resp.model_dump()) if resp else None
        ai_audit.schedule_ai_audit(
            background_tasks,
            request=request,
            user_id=user_id,
            feature_name="image_captioning",
            endpoint="/api/image-captioning",
            http_method="POST",
            model_name=None,
            request_payload=ai_audit.request_payload_full(req),
            response_payload=res_pl,
            status_code=status,
            success=success,
            guardrail_blocked=guardrail_blocked,
            error_message=err_detail,
            latency_ms=latency_ms,
        )


@router.post("/chat", response_model=ChatResponse)
async def chat(
    req: ChatRequest,
    request: Request,
    background_tasks: BackgroundTasks,
    user_id: str = Depends(get_audit_user_id),
) -> ChatResponse:
    prompt = extract_prompt(req)
    if not prompt or not prompt.strip():
        ai_audit.schedule_ai_audit(
            background_tasks,
            request=request,
            user_id=user_id,
            feature_name="chat_image",
            endpoint="/api/chat",
            http_method="POST",
            model_name=req.model,
            request_payload=ai_audit.request_payload_full(req),
            response_payload=None,
            status_code=400,
            success=False,
            guardrail_blocked=False,
            error_message="Missing prompt/messages.",
            latency_ms=0,
        )
        raise HTTPException(status_code=400, detail="Missing prompt/messages.")

    t0 = time.perf_counter()
    resp: ChatResponse | None = None
    err_detail: str | None = None
    status = 200
    success = True
    guardrail_blocked = False
    try:
        mime_type, image_base64, guardrail_blocked = await generate_image_base64(req.model, prompt)
        reply = f"Generated an image using {req.model}."
        resp = ChatResponse(
            model=req.model,
            reply=reply,
            mime_type=mime_type,
            image_base64=image_base64,
        )
        return resp
    except HTTPException as e:
        status = e.status_code
        success = False
        err_detail = e.detail if isinstance(e.detail, str) else str(e.detail)
        raise
    except Exception as e:
        status = 500
        success = False
        err_detail = str(e)
        raise
    finally:
        latency_ms = int((time.perf_counter() - t0) * 1000)
        res_pl = ai_audit.summarize_response_dict(resp.model_dump()) if resp else None
        ai_audit.schedule_ai_audit(
            background_tasks,
            request=request,
            user_id=user_id,
            feature_name="chat_image",
            endpoint="/api/chat",
            http_method="POST",
            model_name=req.model,
            request_payload=ai_audit.request_payload_full(req),
            response_payload=res_pl,
            status_code=status,
            success=success,
            guardrail_blocked=guardrail_blocked,
            error_message=err_detail,
            latency_ms=latency_ms,
        )
