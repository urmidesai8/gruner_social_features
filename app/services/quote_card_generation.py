from typing import List, Tuple

import asyncio
import base64
import io
import json
import logging
import os
import textwrap
import time
from pathlib import Path

from PIL import Image, ImageDraw, ImageFont

from app.core.config import settings
from app.services.aws_clients import (
    bedrock_invoke_model,
    bedrock_response_guardrail_intervened,
    bedrock_runtime_client,
)
from app.services.image_generation import generate_image_base64

_QUOTE_CARD_MODEL = "stabilityai/stable-diffusion-xl-base-1.0"
_QUOTE_BG_ONLY_PROMPT = (
    "Soft full-bleed pastel gradient background only, smooth color blend, instagram aesthetic, "
    "subtle light vignette, dreamy abstract atmosphere. "
    "No text, letters, or words. "
    "No squares, rectangles, frames, panels, cards, blocks, layers, or overlapping geometric shapes. "
    "No circles or diagrams. No objects in the center. Uniform simple gradient fill."
)

logger = logging.getLogger("uvicorn.error")

_APP_DIR = Path(__file__).resolve().parent


def _quote_font_candidates() -> List[str]:
    env = (settings.quote_card_font_path or "").strip()
    paths = [
        env,
        "Poppins-Bold.ttf",
        str(_APP_DIR.parent / "static" / "fonts" / "Poppins-Bold.ttf"),
        str(_APP_DIR.parent / "Poppins-Bold.ttf"),
        "DejaVuSans-Bold.ttf",
        "/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf",
        "/System/Library/Fonts/Supplemental/Arial Bold.ttf",
    ]
    return [p for p in paths if p]


def _load_poppins_font(size: int) -> ImageFont.FreeTypeFont | ImageFont.ImageFont:
    for path in _quote_font_candidates():
        try:
            return ImageFont.truetype(path, size=size)
        except OSError:
            continue
    return ImageFont.load_default()


def _wrap_text(text: str, width: int = 25) -> str:
    return "\n".join(textwrap.wrap(text, width=width))


def _overlay_quote_on_image_sync(image_b64: str, quote: str) -> Tuple[str, str]:
    t0 = time.perf_counter()
    logger.info("quote-cards: step=overlay start quote_len=%d", len(quote))

    image_bytes = base64.b64decode(image_b64)
    image = Image.open(io.BytesIO(image_bytes)).convert("RGBA")
    draw = ImageDraw.Draw(image)

    W, H = image.size
    margin = max(32, W // 28)
    max_text_w = max(64, W - 2 * margin)

    font_size = max(28, min(52, int(44 * (W / 1024))))
    font = _load_poppins_font(font_size)
    wrap_cols = max(14, min(42, int(28 * (W / 1024))))
    bbox_spacing = 10
    line_spacing = 12

    def _measure_block() -> tuple[tuple[int, int, int, int], int, int]:
        sw = max(1, font_size // 22)
        bb = draw.multiline_textbbox(
            (0, 0),
            wrapped_text,
            font=font,
            spacing=bbox_spacing,
            stroke_width=sw,
        )
        left, top, right, bottom = bb
        return bb, right - left, bottom - top

    wrapped_text = _wrap_text(quote, width=wrap_cols)
    bbox, text_width, text_height = _measure_block()

    for _ in range(40):
        if text_width <= max_text_w:
            break
        if wrap_cols > 8:
            wrap_cols -= 1
        else:
            font_size = max(18, font_size - 2)
            font = _load_poppins_font(font_size)
        wrapped_text = _wrap_text(quote, width=wrap_cols)
        bbox, text_width, text_height = _measure_block()

    stroke_w = max(1, font_size // 22)
    left, top, right, bottom = bbox
    text_width = right - left
    text_height = bottom - top
    x = (W - text_width) // 2 - left
    y = max(margin // 2, (H - text_height) // 2 - top)

    draw.multiline_text(
        (x, y),
        wrapped_text,
        font=font,
        fill=(255, 255, 255, 255),
        align="left",
        spacing=line_spacing,
        stroke_width=stroke_w,
        stroke_fill=(30, 30, 40, 220),
    )

    composed = image.convert("RGB")
    out = io.BytesIO()
    composed.save(out, format="PNG")
    final_b64 = base64.b64encode(out.getvalue()).decode("ascii")
    logger.info(
        "quote-cards: step=overlay done elapsed_ms=%d size=%dx%d",
        int((time.perf_counter() - t0) * 1000),
        W,
        H,
    )
    return "image/png", final_b64


def _generate_quote_text_sync(user_prompt: str) -> tuple[str, bool]:
    import botocore.exceptions

    model_id = settings.bedrock_claude_haiku_id
    if not model_id:
        raise RuntimeError("Missing BEDROCK_CLAUDE_HAIKU_ID in environment.")

    t0 = time.perf_counter()
    logger.info(
        "quote-cards: step=llm_quote start model=%s prompt_len=%d",
        model_id,
        len(user_prompt or ""),
    )

    bedrock = bedrock_runtime_client(region_name=settings.aws_region)

    system_prompt = (
        "You write short inspirational quotes for visual quote cards. "
        "Return only a single quote, plain text, no attribution, no markdown, max 180 characters."
    )
    user_content = f"Create a quote for this theme: {user_prompt}"
    body = {
        "anthropic_version": "bedrock-2023-05-31",
        "max_tokens": 120,
        "temperature": 0.8,
        "system": system_prompt,
        "messages": [{"role": "user", "content": [{"type": "text", "text": user_content}]}],
    }

    try:
        response = bedrock_invoke_model(
            bedrock,
            modelId=model_id,
            body=json.dumps(body),
            accept="application/json",
            contentType="application/json",
        )
    except botocore.exceptions.ClientError as e:
        error_message = e.response.get("Error", {}).get("Message", str(e))
        logger.exception(
            "quote-cards: step=llm_quote error model=%s elapsed_ms=%d",
            model_id,
            int((time.perf_counter() - t0) * 1000),
        )
        raise RuntimeError(f"Bedrock Claude Haiku error: {error_message}") from e

    payload = json.loads(response["body"].read())
    guardrail_blocked = bedrock_response_guardrail_intervened(
        response=response,
        payload=payload,
    )
    content = payload.get("content", [])
    text_parts = [part.get("text", "") for part in content if isinstance(part, dict)]
    quote = " ".join(part.strip() for part in text_parts if part.strip()).strip()
    if not quote:
        logger.error(
            "quote-cards: step=llm_quote empty_result model=%s elapsed_ms=%d",
            model_id,
            int((time.perf_counter() - t0) * 1000),
        )
        raise RuntimeError("Claude Haiku returned an empty quote.")

    quote = quote.strip().strip('"')
    logger.info(
        "quote-cards: step=llm_quote done model=%s elapsed_ms=%d quote_len=%d",
        model_id,
        int((time.perf_counter() - t0) * 1000),
        len(quote),
    )
    return quote, guardrail_blocked


async def generate_quote_card_base64(user_prompt: str) -> Tuple[str, str, str, bool]:
    req_t0 = time.perf_counter()
    logger.info("quote-cards: start prompt_len=%d", len(user_prompt or ""))

    quote_text, guardrail_blocked = await asyncio.to_thread(_generate_quote_text_sync, user_prompt)

    bg_t0 = time.perf_counter()
    logger.info("quote-cards: step=flux_background start model=%s", _QUOTE_CARD_MODEL)
    _, bg_base64, _ = await generate_image_base64(_QUOTE_CARD_MODEL, _QUOTE_BG_ONLY_PROMPT)
    logger.info(
        "quote-cards: step=flux_background done elapsed_ms=%d",
        int((time.perf_counter() - bg_t0) * 1000),
    )

    mime_type, final_image_base64 = await asyncio.to_thread(
        _overlay_quote_on_image_sync, bg_base64, quote_text
    )

    logger.info(
        "quote-cards: done elapsed_ms=%d",
        int((time.perf_counter() - req_t0) * 1000),
    )
    return quote_text, mime_type, final_image_base64, guardrail_blocked


__all__ = [
    "generate_quote_card_base64",
]

