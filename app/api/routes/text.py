import time

from fastapi import APIRouter, BackgroundTasks, Depends, HTTPException, Request

from app.api.deps import get_audit_user_id
from app.models.schemas import (
    ContentCopilotRequest,
    ContentCopilotResponse,
    GenerateQuoteCardRequest,
    GenerateQuoteCardResponse,
    HashtagGenerationRequest,
    HashtagGenerationResponse,
    SummarizePostRequest,
    SummarizePostResponse,
    VoiceToPostCommentRequest,
    VoiceToPostCommentResponse,
    TranslateLanguagesResponse,
    TranslateLanguageItem,
    TranslateTextRequest,
    TranslateTextResponse,
)
from app.services import ai_audit
from app.services.aws_clients import redact_text_if_guardrail_blocked
from app.services.content_copilot import generate_copilot_text
from app.services.hashtag_generation import generate_hashtags
from app.services.quote_card_generation import generate_quote_card_base64
from app.services.summarize_post import summarize_post_text
from app.services.text_translation import list_translate_languages, translate_post_text
from app.services.voice_to_post_comment import voice_to_post_comment
from app.core.config import settings


router = APIRouter(prefix="/api", tags=["Text Related Features"])


def _guardrail_hint_from_message(msg: str) -> bool:
    m = msg.lower()
    return "guardrail" in m or "blocked by safety" in m or "safety guardrails" in m


@router.post("/generate-quote-card", response_model=GenerateQuoteCardResponse)
async def generate_quote_card(
    req: GenerateQuoteCardRequest,
    request: Request,
    background_tasks: BackgroundTasks,
    user_id: str = Depends(get_audit_user_id),
) -> GenerateQuoteCardResponse:
    prompt = (req.prompt or "").strip()
    if not prompt:
        ai_audit.schedule_ai_audit(
            background_tasks,
            request=request,
            user_id=user_id,
            feature_name="generate_quote_card",
            endpoint="/api/generate-quote-card",
            http_method="POST",
            model_name=settings.bedrock_claude_haiku_id,
            request_payload=ai_audit.request_payload_full(req),
            response_payload=None,
            status_code=400,
            success=False,
            guardrail_blocked=False,
            error_message="Missing prompt.",
            latency_ms=0,
        )
        raise HTTPException(status_code=400, detail="Missing prompt.")

    t0 = time.perf_counter()
    resp: GenerateQuoteCardResponse | None = None
    err_detail: str | None = None
    status = 200
    success = True
    guardrail_blocked = False
    try:
        quote_text, mime_type, image_base64, guardrail_blocked = await generate_quote_card_base64(prompt)
        resp = GenerateQuoteCardResponse(
            prompt=redact_text_if_guardrail_blocked(
                prompt,
                context_label="quote card prompt echo",
                run_guardrail_precheck=False,
                blocked_by_guardrail=guardrail_blocked,
            ),
            quote_text=quote_text,
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
            feature_name="generate_quote_card",
            endpoint="/api/generate-quote-card",
            http_method="POST",
            model_name=settings.bedrock_claude_haiku_id,
            request_payload=ai_audit.request_payload_full(req),
            response_payload=res_pl,
            status_code=status,
            success=success,
            guardrail_blocked=guardrail_blocked,
            error_message=err_detail,
            latency_ms=latency_ms,
        )


@router.post("/content-copilot", response_model=ContentCopilotResponse)
async def content_copilot(
    req: ContentCopilotRequest,
    request: Request,
    background_tasks: BackgroundTasks,
    user_id: str = Depends(get_audit_user_id),
) -> ContentCopilotResponse:
    text = (req.text or "").strip()
    if not text:
        ai_audit.schedule_ai_audit(
            background_tasks,
            request=request,
            user_id=user_id,
            feature_name="content_copilot",
            endpoint="/api/content-copilot",
            http_method="POST",
            model_name=settings.bedrock_claude_haiku_id,
            request_payload=ai_audit.request_payload_full(req),
            response_payload=None,
            status_code=400,
            success=False,
            guardrail_blocked=False,
            error_message="Missing text.",
            latency_ms=0,
        )
        raise HTTPException(status_code=400, detail="Missing text.")

    t0 = time.perf_counter()
    resp: ContentCopilotResponse | None = None
    err_detail: str | None = None
    status = 200
    success = True
    guardrail_blocked = False
    try:
        result, guardrail_blocked = await generate_copilot_text(req.mode.value, text)
        resp = ContentCopilotResponse(
            mode=req.mode,
            original_text=redact_text_if_guardrail_blocked(
                text,
                context_label="content copilot text echo",
                run_guardrail_precheck=False,
                blocked_by_guardrail=guardrail_blocked,
            ),
            result=result,
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
            feature_name="content_copilot",
            endpoint="/api/content-copilot",
            http_method="POST",
            model_name=settings.bedrock_claude_haiku_id,
            request_payload=ai_audit.request_payload_full(req),
            response_payload=res_pl,
            status_code=status,
            success=success,
            guardrail_blocked=guardrail_blocked,
            error_message=err_detail,
            latency_ms=latency_ms,
        )


@router.post("/summarize-post", response_model=SummarizePostResponse)
async def summarize_post(
    req: SummarizePostRequest,
    request: Request,
    background_tasks: BackgroundTasks,
    user_id: str = Depends(get_audit_user_id),
) -> SummarizePostResponse:
    text = (req.text or "").strip()
    if not text:
        ai_audit.schedule_ai_audit(
            background_tasks,
            request=request,
            user_id=user_id,
            feature_name="summarize_post",
            endpoint="/api/summarize-post",
            http_method="POST",
            model_name=settings.bedrock_claude_haiku_id,
            request_payload=ai_audit.request_payload_full(req),
            response_payload=None,
            status_code=400,
            success=False,
            guardrail_blocked=False,
            error_message="Missing text.",
            latency_ms=0,
        )
        raise HTTPException(status_code=400, detail="Missing text.")

    t0 = time.perf_counter()
    resp: SummarizePostResponse | None = None
    err_detail: str | None = None
    status = 200
    success = True
    guardrail_blocked = False
    try:
        result, guardrail_blocked = await summarize_post_text(text)
        resp = SummarizePostResponse(
            original_text=redact_text_if_guardrail_blocked(
                text,
                context_label="summarize post text echo",
                run_guardrail_precheck=False,
                blocked_by_guardrail=guardrail_blocked,
            ),
            result=result,
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
            feature_name="summarize_post",
            endpoint="/api/summarize-post",
            http_method="POST",
            model_name=settings.bedrock_claude_haiku_id,
            request_payload=ai_audit.request_payload_full(req),
            response_payload=res_pl,
            status_code=status,
            success=success,
            guardrail_blocked=guardrail_blocked,
            error_message=err_detail,
            latency_ms=latency_ms,
        )


@router.post("/hashtag-generation", response_model=HashtagGenerationResponse)
async def hashtag_generation(
    req: HashtagGenerationRequest,
    request: Request,
    background_tasks: BackgroundTasks,
    user_id: str = Depends(get_audit_user_id),
) -> HashtagGenerationResponse:
    text_caption = (req.text_caption or "").strip()
    media_image = (req.media_image or "").strip()
    media_video = (req.media_video or "").strip()
    if not (text_caption or media_image or media_video):
        ai_audit.schedule_ai_audit(
            background_tasks,
            request=request,
            user_id=user_id,
            feature_name="hashtag_generation",
            endpoint="/api/hashtag-generation",
            http_method="POST",
            model_name=None,
            request_payload=ai_audit.request_payload_full(req),
            response_payload=None,
            status_code=400,
            success=False,
            guardrail_blocked=False,
            error_message="Missing input.",
            latency_ms=0,
        )
        raise HTTPException(
            status_code=400,
            detail="Missing input. Provide at least one of text_caption, media_image, or media_video.",
        )

    t0 = time.perf_counter()
    resp: HashtagGenerationResponse | None = None
    err_detail: str | None = None
    status = 200
    success = True
    guardrail_blocked = False
    try:
        out = await generate_hashtags(
            text_caption=text_caption or None,
            media_image=media_image or None,
            media_video=media_video or None,
        )
        resp = HashtagGenerationResponse(
            hashtags=out["hashtags"],  # type: ignore[arg-type]
            combined_caption=out["combined_caption"],  # type: ignore[arg-type]
            used_sources=out["used_sources"],  # type: ignore[arg-type]
            text_caption=redact_text_if_guardrail_blocked(
                out["text_caption"],  # type: ignore[arg-type]
                context_label="hashtag text_caption echo",
                run_guardrail_precheck=False,
            ),
            image_caption=out["image_caption"],  # type: ignore[arg-type]
            video_caption=out["video_caption"],  # type: ignore[arg-type]
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
            feature_name="hashtag_generation",
            endpoint="/api/hashtag-generation",
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


@router.post("/voice-to-post-comment", response_model=VoiceToPostCommentResponse)
async def voice_post_comment(
    req: VoiceToPostCommentRequest,
    request: Request,
    background_tasks: BackgroundTasks,
    user_id: str = Depends(get_audit_user_id),
) -> VoiceToPostCommentResponse:
    if not (req.audio_base64 or "").strip():
        ai_audit.schedule_ai_audit(
            background_tasks,
            request=request,
            user_id=user_id,
            feature_name="voice_to_post_comment",
            endpoint="/api/voice-to-post-comment",
            http_method="POST",
            model_name=None,
            request_payload=ai_audit.request_payload_full(req),
            response_payload=None,
            status_code=400,
            success=False,
            guardrail_blocked=False,
            error_message="Missing audio_base64.",
            latency_ms=0,
        )
        raise HTTPException(status_code=400, detail="Missing audio_base64.")
    if not (req.mime_type or "").strip():
        ai_audit.schedule_ai_audit(
            background_tasks,
            request=request,
            user_id=user_id,
            feature_name="voice_to_post_comment",
            endpoint="/api/voice-to-post-comment",
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

    t0 = time.perf_counter()
    resp: VoiceToPostCommentResponse | None = None
    err_detail: str | None = None
    status = 200
    success = True
    guardrail_blocked = False
    try:
        out = await voice_to_post_comment(
            audio_base64=req.audio_base64,
            mime_type=req.mime_type,
            output_kind=req.output_kind,
        )
        resp = VoiceToPostCommentResponse(
            raw_transcript=out["raw_transcript"],
            final_text=out["final_text"],
            output_kind=out["output_kind"],  # type: ignore[arg-type]
            language_code=out["language_code"],
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
            feature_name="voice_to_post_comment",
            endpoint="/api/voice-to-post-comment",
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


@router.get("/translate-languages", response_model=TranslateLanguagesResponse)
async def translate_languages() -> TranslateLanguagesResponse:
    try:
        rows = await list_translate_languages()
    except RuntimeError as e:
        raise HTTPException(status_code=500, detail=str(e)) from e
    return TranslateLanguagesResponse(
        languages=[TranslateLanguageItem(**r) for r in rows]
    )


@router.post("/translate-text", response_model=TranslateTextResponse)
async def translate_text(
    req: TranslateTextRequest,
    request: Request,
    background_tasks: BackgroundTasks,
    user_id: str = Depends(get_audit_user_id),
) -> TranslateTextResponse:
    text = (req.text or "").strip()
    if not text:
        ai_audit.schedule_ai_audit(
            background_tasks,
            request=request,
            user_id=user_id,
            feature_name="translate_text",
            endpoint="/api/translate-text",
            http_method="POST",
            model_name="amazon-translate",
            request_payload=ai_audit.request_payload_full(req),
            response_payload=None,
            status_code=400,
            success=False,
            guardrail_blocked=False,
            error_message="Missing text.",
            latency_ms=0,
        )
        raise HTTPException(status_code=400, detail="Missing text.")
    src = (req.source_language_code or "auto").strip().lower()
    tgt = (req.target_language or "").strip()
    if not tgt:
        ai_audit.schedule_ai_audit(
            background_tasks,
            request=request,
            user_id=user_id,
            feature_name="translate_text",
            endpoint="/api/translate-text",
            http_method="POST",
            model_name="amazon-translate",
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
    resp: TranslateTextResponse | None = None
    err_detail: str | None = None
    status = 200
    success = True
    guardrail_blocked = False
    try:
        out = await translate_post_text(text, src, tgt)
        resp = TranslateTextResponse(
            translated_text=out["translated_text"],
            source_language_code=out["source_language_code"],
            target_language_code=out["target_language_code"],
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
        guardrail_blocked = _guardrail_hint_from_message(err_detail)
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
            feature_name="translate_text",
            endpoint="/api/translate-text",
            http_method="POST",
            model_name="amazon-translate",
            request_payload=ai_audit.request_payload_full(req),
            response_payload=res_pl,
            status_code=status,
            success=success,
            guardrail_blocked=guardrail_blocked,
            error_message=err_detail,
            latency_ms=latency_ms,
        )
