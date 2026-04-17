import time
from typing import Dict

from fastapi import APIRouter, BackgroundTasks, Depends, HTTPException, Request

from app.api.deps import get_audit_user_id
from app.models.schemas import (
    GenerateVideoRequest,
    GenerateVideoResponse,
    VideoAudioTranslateRequest,
    VideoAudioTranslateResponse,
)
from app.services import ai_audit
from app.services.aws_clients import redact_text_if_guardrail_blocked
from app.services.video_audio_translation import translate_video_audio_base64
from app.services.video_generation import VIDEO_MODELS, generate_video_base64


router = APIRouter(prefix="/api", tags=["Video Related Features"])


@router.get("/video-models")
async def list_video_models() -> Dict[str, list[str]]:
    return {"models": VIDEO_MODELS}


@router.post("/generate-video", response_model=GenerateVideoResponse)
async def generate_video(
    req: GenerateVideoRequest,
    request: Request,
    background_tasks: BackgroundTasks,
    user_id: str = Depends(get_audit_user_id),
) -> GenerateVideoResponse:
    t0 = time.perf_counter()
    resp: GenerateVideoResponse | None = None
    err_detail: str | None = None
    status = 200
    success = True
    guardrail_blocked = False
    try:
        mime_type, video_base64 = await generate_video_base64(req.model, req.prompt)
        resp = GenerateVideoResponse(
            model=req.model,
            prompt=redact_text_if_guardrail_blocked(
                req.prompt,
                context_label="video generation prompt echo",
                run_guardrail_precheck=False,
            ),
            mime_type=mime_type,
            video_base64=video_base64,
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
            feature_name="generate_video",
            endpoint="/api/generate-video",
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


@router.post("/translate-video-audio", response_model=VideoAudioTranslateResponse)
async def translate_video_audio(
    req: VideoAudioTranslateRequest,
    request: Request,
    background_tasks: BackgroundTasks,
    user_id: str = Depends(get_audit_user_id),
) -> VideoAudioTranslateResponse:
    if not (req.video_base64 or "").strip():
        ai_audit.schedule_ai_audit(
            background_tasks,
            request=request,
            user_id=user_id,
            feature_name="translate_video_audio",
            endpoint="/api/translate-video-audio",
            http_method="POST",
            model_name=None,
            request_payload=ai_audit.request_payload_full(req),
            response_payload=None,
            status_code=400,
            success=False,
            guardrail_blocked=False,
            error_message="Missing video_base64.",
            latency_ms=0,
        )
        raise HTTPException(status_code=400, detail="Missing video_base64.")
    if not (req.mime_type or "").strip():
        ai_audit.schedule_ai_audit(
            background_tasks,
            request=request,
            user_id=user_id,
            feature_name="translate_video_audio",
            endpoint="/api/translate-video-audio",
            http_method="POST",
            model_name=None,
            request_payload=ai_audit.request_payload_full(req),
            response_payload=None,
            status_code=400,
            success=False,
            guardrail_blocked=False,
            error_message="Missing mime_type.",
            latency_ms=0,
        )
        raise HTTPException(status_code=400, detail="Missing mime_type.")
    if not (req.target_language or "").strip():
        ai_audit.schedule_ai_audit(
            background_tasks,
            request=request,
            user_id=user_id,
            feature_name="translate_video_audio",
            endpoint="/api/translate-video-audio",
            http_method="POST",
            model_name=None,
            request_payload=ai_audit.request_payload_full(req),
            response_payload=None,
            status_code=400,
            success=False,
            guardrail_blocked=False,
            error_message="Missing target_language.",
            latency_ms=0,
        )
        raise HTTPException(status_code=400, detail="Missing target_language.")

    t0 = time.perf_counter()
    resp: VideoAudioTranslateResponse | None = None
    err_detail: str | None = None
    status = 200
    success = True
    guardrail_blocked = False
    try:
        mime_type, video_base64, translated_text = await translate_video_audio_base64(
            req.video_base64,
            req.mime_type,
            req.target_language,
            keep_original_audio=req.keep_original_audio,
        )
        resp = VideoAudioTranslateResponse(
            mime_type=mime_type,
            video_base64=video_base64,
            translated_text=translated_text,
        )
        return resp
    except HTTPException as e:
        status = e.status_code
        success = False
        err_detail = e.detail if isinstance(e.detail, str) else str(e.detail)
        raise
    except ValueError as e:
        status = 400
        success = False
        err_detail = str(e)
        guardrail_blocked = "guardrail" in err_detail.lower() or "blocked" in err_detail.lower()
        raise HTTPException(status_code=400, detail=str(e)) from e
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
            feature_name="translate_video_audio",
            endpoint="/api/translate-video-audio",
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
