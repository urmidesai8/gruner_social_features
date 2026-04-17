from fastapi import APIRouter, HTTPException

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
from app.services.content_copilot import generate_copilot_text
from app.services.quote_card_generation import generate_quote_card_base64
from app.services.summarize_post import summarize_post_text
from app.services.hashtag_generation import generate_hashtags
from app.services.text_translation import list_translate_languages, translate_post_text
from app.services.voice_to_post_comment import voice_to_post_comment
from app.services.aws_clients import redact_text_if_guardrail_blocked


router = APIRouter(prefix="/api", tags=["Text Related Features"])


@router.post("/generate-quote-card", response_model=GenerateQuoteCardResponse)
async def generate_quote_card(req: GenerateQuoteCardRequest) -> GenerateQuoteCardResponse:
    prompt = (req.prompt or "").strip()
    if not prompt:
        raise HTTPException(status_code=400, detail="Missing prompt.")
    try:
        quote_text, mime_type, image_base64, guardrail_blocked = await generate_quote_card_base64(prompt)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e)) from e
    except RuntimeError as e:
        raise HTTPException(status_code=500, detail=str(e)) from e

    return GenerateQuoteCardResponse(
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


@router.post("/content-copilot", response_model=ContentCopilotResponse)
async def content_copilot(req: ContentCopilotRequest) -> ContentCopilotResponse:
    text = (req.text or "").strip()
    if not text:
        raise HTTPException(status_code=400, detail="Missing text.")
    try:
        result, guardrail_blocked = await generate_copilot_text(req.mode.value, text)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e)) from e
    except RuntimeError as e:
        raise HTTPException(status_code=500, detail=str(e)) from e

    return ContentCopilotResponse(
        mode=req.mode,
        original_text=redact_text_if_guardrail_blocked(
            text,
            context_label="content copilot text echo",
            run_guardrail_precheck=False,
            blocked_by_guardrail=guardrail_blocked,
        ),
        result=result,
    )


@router.post("/summarize-post", response_model=SummarizePostResponse)
async def summarize_post(req: SummarizePostRequest) -> SummarizePostResponse:
    text = (req.text or "").strip()
    if not text:
        raise HTTPException(status_code=400, detail="Missing text.")
    try:
        result, guardrail_blocked = await summarize_post_text(text)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e)) from e
    except RuntimeError as e:
        raise HTTPException(status_code=500, detail=str(e)) from e

    return SummarizePostResponse(
        original_text=redact_text_if_guardrail_blocked(
            text,
            context_label="summarize post text echo",
            run_guardrail_precheck=False,
            blocked_by_guardrail=guardrail_blocked,
        ),
        result=result,
    )


@router.post("/hashtag-generation", response_model=HashtagGenerationResponse)
async def hashtag_generation(req: HashtagGenerationRequest) -> HashtagGenerationResponse:
    text_caption = (req.text_caption or "").strip()
    media_image = (req.media_image or "").strip()
    media_video = (req.media_video or "").strip()
    if not (text_caption or media_image or media_video):
        raise HTTPException(
            status_code=400,
            detail="Missing input. Provide at least one of text_caption, media_image, or media_video.",
        )

    try:
        out = await generate_hashtags(
            text_caption=text_caption or None,
            media_image=media_image or None,
            media_video=media_video or None,
        )
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e)) from e
    except RuntimeError as e:
        raise HTTPException(status_code=500, detail=str(e)) from e

    return HashtagGenerationResponse(
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


@router.post("/voice-to-post-comment", response_model=VoiceToPostCommentResponse)
async def voice_post_comment(
    req: VoiceToPostCommentRequest,
) -> VoiceToPostCommentResponse:
    if not (req.audio_base64 or "").strip():
        raise HTTPException(status_code=400, detail="Missing audio_base64.")
    if not (req.mime_type or "").strip():
        raise HTTPException(status_code=400, detail="Missing mime_type.")
    try:
        out = await voice_to_post_comment(
            audio_base64=req.audio_base64,
            mime_type=req.mime_type,
            output_kind=req.output_kind,
        )
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e)) from e
    except RuntimeError as e:
        raise HTTPException(status_code=500, detail=str(e)) from e

    return VoiceToPostCommentResponse(
        raw_transcript=out["raw_transcript"],
        final_text=out["final_text"],
        output_kind=out["output_kind"],  # type: ignore[arg-type]
        language_code=out["language_code"],
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
async def translate_text(req: TranslateTextRequest) -> TranslateTextResponse:
    text = (req.text or "").strip()
    if not text:
        raise HTTPException(status_code=400, detail="Missing text.")
    src = (req.source_language_code or "auto").strip().lower()
    tgt = (req.target_language or "").strip()
    if not tgt:
        raise HTTPException(status_code=400, detail="Missing target_language.")
    try:
        out = await translate_post_text(text, src, tgt)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e)) from e
    except RuntimeError as e:
        raise HTTPException(status_code=500, detail=str(e)) from e

    return TranslateTextResponse(
        translated_text=out["translated_text"],
        source_language_code=out["source_language_code"],
        target_language_code=out["target_language_code"],
    )

