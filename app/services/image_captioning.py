import asyncio
import base64
import io
import json
import logging
import os
from typing import Dict, Tuple
import time

import torch
from dotenv import load_dotenv
from PIL import Image
from app.services.aws_clients import bedrock_runtime_client

load_dotenv()

logger = logging.getLogger("uvicorn.error")

_BLIP_MODEL_ID = "Salesforce/blip-image-captioning-large"
# ImageTextToTextPipeline requires non-None `text` when `images` is set; BLIP is trained with a short prefix.
_BLIP_CONDITIONING_TEXT = "A photo of"

_blip_pipe = None
_blip_load_lock = asyncio.Lock()


def _decode_base64_image(image_base64: str) -> Image.Image:
    raw = (image_base64 or "").strip()
    if raw.startswith("data:"):
        _, _, raw = raw.partition(",")

    try:
        image_bytes = base64.b64decode(raw)
    except Exception as e:  # noqa: BLE001
        raise ValueError("Invalid image_base64 payload.") from e

    try:
        return Image.open(io.BytesIO(image_bytes)).convert("RGB")
    except Exception as e:  # noqa: BLE001
        raise ValueError("Unable to decode uploaded image.") from e


async def _get_blip_pipeline():
    """
    Lazy-load BLIP captioning pipeline to avoid heavy startup costs.
    """
    global _blip_pipe
    async with _blip_load_lock:
        if _blip_pipe is not None:
            return _blip_pipe

        from transformers import pipeline

        if torch.cuda.is_available():
            device = 0
        else:
            # MPS support varies by transformers build; default to CPU.
            device = -1

        hf_token = os.getenv("HF_TOKEN")
        # Transformers 5.x removes the "image-to-text" task; use "image-text-to-text" for BLIP captioning.
        _blip_pipe = pipeline(
            "image-text-to-text",
            model=_BLIP_MODEL_ID,
            device=device,
            token=hf_token or None,
        )
        return _blip_pipe


def _generate_blip_caption_sync(image: Image.Image) -> str:
    pipe = _blip_pipe
    if pipe is None:
        raise RuntimeError("BLIP pipeline not loaded.")

    out = pipe(images=image, text=_BLIP_CONDITIONING_TEXT)
    if isinstance(out, list) and out:
        first = out[0]
        if isinstance(first, list) and first:
            first = first[0]
        if isinstance(first, dict):
            return (
                first.get("generated_text")
                or first.get("caption")
                or first.get("text")
                or str(first)
            )
        if isinstance(first, str):
            return first.strip()
    # Fallback
    return str(out).strip()


def _parse_caption_json(raw_text: str) -> Dict[str, str]:
    """
    Best-effort JSON parsing:
    - Try full JSON first.
    - If Claude wraps JSON with text, slice to the first {...} block.
    - Fallback to "key: value" line parsing.
    """
    keys = ["poetic", "funny", "aesthetic", "short", "deep"]
    text = (raw_text or "").strip()

    try:
        data = json.loads(text)
        if isinstance(data, dict):
            return {k: str(data.get(k, "")).strip() for k in keys}
    except Exception:  # noqa: BLE001
        pass

    start = text.find("{")
    end = text.rfind("}")
    if start != -1 and end != -1 and end > start:
        try:
            data = json.loads(text[start : end + 1])
            if isinstance(data, dict):
                return {k: str(data.get(k, "")).strip() for k in keys}
        except Exception:  # noqa: BLE001
            pass

    parsed: Dict[str, str] = {}
    lower_lines = text.splitlines()
    for line in lower_lines:
        if ":" not in line:
            continue
        k, v = line.split(":", 1)
        k = k.strip().lower()
        if k in keys:
            parsed[k] = v.strip()

    return {k: parsed.get(k, "").strip() for k in keys}


def _generate_caption_variants_sync(blip_caption: str) -> Dict[str, str]:
    """
    Use Bedrock Claude Haiku to rewrite the BLIP caption into 5 styles.
    """
    import botocore.exceptions

    model_id = os.getenv("BEDROCK_CLAUDE_HAIKU_ID")
    if not model_id:
        raise RuntimeError("Missing BEDROCK_CLAUDE_HAIKU_ID in environment.")

    bedrock = bedrock_runtime_client(region_name=os.getenv("AWS_REGION"))

    system_prompt = (
        "You are an AI social media editor. "
        "You will be given a raw image caption (from an image model). "
        "Rewrite it into five different caption variants with these exact styles: "
        "poetic, funny, aesthetic, short, deep.\n\n"
        "Return ONLY valid JSON (no markdown, no extra keys, no surrounding commentary) "
        "with exactly these keys:\n"
        "poetic, funny, aesthetic, short, deep.\n\n"
        "Constraints:\n"
        "- poetic: lyrical and reflective (1-2 sentences)\n"
        "- funny: playful and humorous (1-2 sentences)\n"
        "- aesthetic: vibe-focused, sensory, style-forward (1-2 sentences)\n"
        "- short: a single concise line\n"
        "- deep: insightful and meaningful (1-2 sentences)\n"
        "- Avoid emojis and hashtags.\n"
    )

    user_text = f"BLIP caption: {blip_caption}"
    body = {
        "anthropic_version": "bedrock-2023-05-31",
        "max_tokens": 500,
        "temperature": 0.7,
        "system": system_prompt,
        "messages": [{"role": "user", "content": [{"type": "text", "text": user_text}]}],
    }

    t0 = time.perf_counter()
    logger.info(
        "image-captioning: step=llm start blip_len=%d", len(blip_caption or "")
    )
    try:
        response = bedrock.invoke_model(
            modelId=model_id,
            body=json.dumps(body),
            accept="application/json",
            contentType="application/json",
        )
    except botocore.exceptions.ClientError as e:
        error_message = e.response.get("Error", {}).get("Message", str(e))
        logger.exception(
            "image-captioning: step=llm error elapsed_s=%d",
            int(time.perf_counter() - t0),
        )
        raise RuntimeError(f"Bedrock Claude Haiku error: {error_message}") from e

    payload = json.loads(response["body"].read())
    content = payload.get("content", [])
    parts = [part.get("text", "") for part in content if isinstance(part, dict)]
    raw_text = "\n".join(p.strip() for p in parts if p.strip()).strip()
    if not raw_text:
        raise RuntimeError("Claude Haiku returned an empty caption JSON.")

    variants = _parse_caption_json(raw_text)
    # Ensure all keys exist
    for key in ["poetic", "funny", "aesthetic", "short", "deep"]:
        variants[key] = variants.get(key, "").strip()
    return variants


async def generate_image_caption_options(
    image_base64: str,
) -> Tuple[str, Dict[str, str]]:
    image = _decode_base64_image(image_base64)

    pipe = await _get_blip_pipeline()
    # Ensure the sync BLIP generator sees the same pipe in the module global.
    global _blip_pipe
    _blip_pipe = pipe

    blip_caption = await asyncio.to_thread(_generate_blip_caption_sync, image)
    blip_caption = (blip_caption or "").strip()
    if not blip_caption:
        raise RuntimeError("BLIP returned an empty caption.")

    # LLM call is sync (Bedrock client); run in a worker thread.
    variants = await asyncio.to_thread(_generate_caption_variants_sync, blip_caption)
    return blip_caption, variants


__all__ = [
    "generate_image_caption_options",
]

