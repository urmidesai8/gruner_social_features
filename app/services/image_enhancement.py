from typing import Optional, Tuple

import asyncio
import base64
import io
import os

import torch
from diffusers import DiffusionPipeline
from dotenv import load_dotenv
from PIL import Image

load_dotenv()

_flux2_klein_pipe = None
_flux2_klein_load_lock = asyncio.Lock()
_flux2_klein_generate_lock = asyncio.Lock()

_FLUX2_KLEIN_ENHANCER_MODEL = "black-forest-labs/FLUX.2-klein-9b-kv"
_ENHANCE_BASE_PROMPT = (
    "Enhance and edit this image: improve lighting and exposure, lift shadows and balance highlights; "
    "increase clarity, sharpness, and fine detail while reducing noise and haze; "
    "strengthen composition and framing. Preserve the subject and main scene content; "
    "keep the result photorealistic, natural, and high quality."
)


def _compose_enhance_prompt(user_prompt: Optional[str]) -> str:
    extra = (user_prompt or "").strip()
    if not extra:
        return _ENHANCE_BASE_PROMPT
    return f"{_ENHANCE_BASE_PROMPT} Additional instructions from the user: {extra}"


def _require_hf_token() -> str:
    token = os.getenv("HF_TOKEN")
    if not token:
        raise RuntimeError(
            "Missing HF_TOKEN environment variable. Set HF_TOKEN to your Hugging Face token."
        )
    return token


def _encode_pil_image_to_base64(image: Image.Image) -> Tuple[str, str]:
    buf = io.BytesIO()
    image.save(buf, format="PNG")
    mime_type = "image/png"
    image_base64 = base64.b64encode(buf.getvalue()).decode("ascii")
    return mime_type, image_base64


def _decode_base64_image(image_base64: str) -> Image.Image:
    raw = image_base64.strip()
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


def _load_flux2_klein_pipeline(model_id: str, **kwargs):
    # FLUX.2 klein is not a generic DiffusionPipeline model; use its dedicated class.
    try:
        from diffusers import Flux2KleinKVPipeline

        return Flux2KleinKVPipeline.from_pretrained(model_id, **kwargs)
    except (ImportError, AttributeError):
        try:
            from diffusers import Flux2KleinPipeline

            return Flux2KleinPipeline.from_pretrained(model_id, **kwargs)
        except (ImportError, AttributeError) as e:
            import diffusers as _diffusers

            available = [n for n in dir(_diffusers) if "Flux2Klein" in n]
            raise RuntimeError(
                "Your installed diffusers version does not expose a compatible FLUX.2 klein pipeline class. "
                f"Available symbols: {available}. "
                "Upgrade diffusers to a version that supports FLUX.2 klein."
            ) from e


async def _get_flux2_klein_enhancer_pipeline():
    global _flux2_klein_pipe
    async with _flux2_klein_load_lock:
        if _flux2_klein_pipe is not None:
            return _flux2_klein_pipe

        token = _require_hf_token()
        common = {
            "token": token,
            "trust_remote_code": True,
        }

        if torch.cuda.is_available():
            torch_dtype = torch.bfloat16
            load_kwargs = {**common, "torch_dtype": torch_dtype, "device_map": "cuda"}
            move_to = None
        elif getattr(torch.backends, "mps", None) and torch.backends.mps.is_available():
            torch_dtype = torch.bfloat16
            load_kwargs = {**common, "torch_dtype": torch_dtype}
            move_to = "mps"
        else:
            load_kwargs = {**common, "torch_dtype": torch.float32}
            move_to = "cpu"

        try:
            pipe = await asyncio.to_thread(
                _load_flux2_klein_pipeline,
                _FLUX2_KLEIN_ENHANCER_MODEL,
                **load_kwargs,
            )
        except Exception as e:  # noqa: BLE001
            raise RuntimeError(
                f"Failed to load {_FLUX2_KLEIN_ENHANCER_MODEL} pipeline. {e}"
            ) from e

        if move_to is not None:
            pipe = pipe.to(move_to)

        _flux2_klein_pipe = pipe
        return _flux2_klein_pipe


def _enhance_image_sync(pipe, input_image: Image.Image, prompt: str) -> Image.Image:
    result = pipe(image=input_image, prompt=prompt).images[0]
    return result


async def enhance_image_base64(
    image_base64: str, user_prompt: Optional[str] = None
) -> Tuple[str, str, str]:
    control_image = _decode_base64_image(image_base64)
    full_prompt = _compose_enhance_prompt(user_prompt)
    async with _flux2_klein_generate_lock:
        pipe = await _get_flux2_klein_enhancer_pipeline()
        enhanced = await asyncio.to_thread(
            _enhance_image_sync, pipe, control_image, full_prompt
        )
    mime_type, encoded = _encode_pil_image_to_base64(enhanced)
    return full_prompt, mime_type, encoded


__all__ = [
    "enhance_image_base64",
]

