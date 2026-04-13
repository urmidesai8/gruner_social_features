from typing import List, Tuple

import asyncio
import base64
import io
import os

from diffusers import DiffusionPipeline, Kandinsky5T2IPipeline
from huggingface_hub import InferenceClient
from huggingface_hub.errors import HfHubHTTPError, RemoteEntryNotFoundError
from PIL import Image
import torch
from dotenv import load_dotenv
from app.services.aws_clients import bedrock_runtime_client

load_dotenv()

MODELS: List[str] = [
    "black-forest-labs/FLUX.1-schnell",
    "stabilityai/stable-diffusion-xl-base-1.0",
    "kandinskylab/Kandinsky-5.0-T2I-Lite",
    "amazon.titan-image-generator-v2:0",
    "amazon.nova-canvas-v1:0",
    "gpt-image-1.5",
]

_KANDINSKY_MODEL = "kandinskylab/Kandinsky-5.0-T2I-Lite"
_STABILITY_MODEL = "stabilityai/stable-diffusion-xl-base-1.0"
_TITAN_MODEL = "amazon.titan-image-generator-v2:0"
_NOVA_CANVAS_MODEL = "amazon.nova-canvas-v1:0"
_OPENAI_MODEL = "gpt-image-1.5"
_KANDINSKY_PIPELINE_MODEL_CANDIDATES: List[str] = [
    "kandinskylab/Kandinsky-5.0-T2I-Lite-sft-Diffusers",
    "kandinskylab/Kandinsky-5.0-T2I-Lite-pretrain-Diffusers",
]

_inference_clients_by_provider: dict[str, InferenceClient] = {}
_stability_inference_client_hf_inference: InferenceClient | None = None
_kandinsky_pipe: DiffusionPipeline | None = None
_kandinsky_load_lock = asyncio.Lock()
_kandinsky_generate_lock = asyncio.Lock()


def _require_hf_token() -> str:
    token = os.getenv("HF_TOKEN")
    if not token:
        raise RuntimeError(
            "Missing HF_TOKEN environment variable. Set HF_TOKEN to your Hugging Face token."
        )
    return token


def _get_inference_client(provider: str) -> InferenceClient:
    global _inference_clients_by_provider
    token = _require_hf_token()
    if provider not in _inference_clients_by_provider:
        kwargs = {"api_key": token}
        if provider != "default":
            kwargs["provider"] = provider
        _inference_clients_by_provider[provider] = InferenceClient(**kwargs)
    return _inference_clients_by_provider[provider]


def _provider_candidates(model: str) -> List[str]:
    return ["default", "hf-inference", "fal-ai"]


def _get_stability_inference_client_hf_inference() -> InferenceClient:
    global _stability_inference_client_hf_inference
    if _stability_inference_client_hf_inference is None:
        token = _require_hf_token()
        _stability_inference_client_hf_inference = InferenceClient(
            provider="hf-inference",
            api_key=token,
        )
    return _stability_inference_client_hf_inference


async def _get_kandinsky_pipeline() -> DiffusionPipeline:
    global _kandinsky_pipe
    async with _kandinsky_load_lock:
        if _kandinsky_pipe is not None:
            return _kandinsky_pipe

        token = _require_hf_token()
        torch_dtype = torch.bfloat16 if torch.cuda.is_available() else torch.float32
        device_map = "cuda" if torch.cuda.is_available() else None

        kwargs = {
            "torch_dtype": torch_dtype,
            "token": token,
        }
        if device_map is not None:
            kwargs["device_map"] = device_map

        try:
            pipe: DiffusionPipeline = DiffusionPipeline.from_pretrained(_KANDINSKY_MODEL, **kwargs)
        except RemoteEntryNotFoundError:
            last_error: Exception | None = None
            for candidate in _KANDINSKY_PIPELINE_MODEL_CANDIDATES:
                try:
                    pipe = Kandinsky5T2IPipeline.from_pretrained(candidate, **kwargs)
                    break
                except Exception as e:  # noqa: BLE001
                    last_error = e
                    continue
            else:
                raise last_error or RuntimeError(
                    "Failed to load Kandinsky pipeline from all candidates."
                )

        if device_map is None:
            pipe = pipe.to("cpu")

        _kandinsky_pipe = pipe
        return _kandinsky_pipe


def _encode_pil_image_to_base64(image: Image.Image) -> Tuple[str, str]:
    buf = io.BytesIO()
    image.save(buf, format="PNG")
    mime_type = "image/png"
    image_base64 = base64.b64encode(buf.getvalue()).decode("ascii")
    return mime_type, image_base64


def _generate_via_inference_client(model: str, prompt: str) -> Image.Image:
    errors: List[str] = []
    for provider in _provider_candidates(model):
        client = _get_inference_client(provider)
        try:
            return client.text_to_image(prompt, model=model)
        except HfHubHTTPError as e:
            status_code = getattr(getattr(e, "response", None), "status_code", "unknown")
            errors.append(f"{provider}: HTTP {status_code}")
            continue

    raise RuntimeError(
        f"Model call failed for '{model}' with all providers ({', '.join(_provider_candidates(model))}). "
        f"Attempts: {', '.join(errors)}. "
        "Most likely causes: model unavailable for your account/provider, or provider billing required."
    )


def _generate_kandinsky_sync(pipe: DiffusionPipeline, prompt: str) -> Image.Image:
    return pipe(prompt).images[0]


def _generate_aws_bedrock_image_sync(model_id: str, prompt: str) -> Tuple[str, str]:
    import botocore.exceptions
    import json

    max_len = 512
    if model_id == _TITAN_MODEL and len(prompt) > max_len:
        raise ValueError(
            f"{model_id} only supports prompts up to {max_len} characters. Your prompt was {len(prompt)} characters."
        )

    region_name = (
        os.getenv("AWS_REGION_BEDROCK_NOVA_CANVAS", "us-east-1")
        if model_id == _NOVA_CANVAS_MODEL
        else os.getenv("AWS_REGION_BEDROCK_IMAGE", "us-west-2")
    )

    bedrock = bedrock_runtime_client(region_name=region_name)

    body = {
        "taskType": "TEXT_IMAGE",
        "textToImageParams": {"text": prompt},
        "imageGenerationConfig": {
            "numberOfImages": 1,
            "height": 1024,
            "width": 1024,
            "cfgScale": 8.0,
            "seed": 0,
        },
    }

    try:
        response = bedrock.invoke_model(
            modelId=model_id,
            body=json.dumps(body),
            accept="application/json",
            contentType="application/json",
        )
    except botocore.exceptions.ClientError as e:
        error_message = e.response.get("Error", {}).get("Message", str(e))
        raise RuntimeError(f"AWS Bedrock error: {error_message}") from e

    response_body = json.loads(response.get("body").read())
    if "images" not in response_body or response_body["images"] is None:
        raise RuntimeError(
            f"Bedrock ({model_id}) response did not contain 'images'. Raw response: {json.dumps(response_body)}"
        )

    base64_image = response_body.get("images")[0]
    return "image/png", base64_image


def _generate_openai_image_sync(model_id: str, prompt: str) -> Tuple[str, str]:
    from openai import OpenAI

    api_key = os.getenv("OPENAI_KEY")
    if not api_key:
        raise RuntimeError("Missing OPENAI_KEY in environment.")

    client = OpenAI(api_key=api_key)

    try:
        response = client.images.generate(
            model=model_id,
            prompt=prompt,
            n=1,
            size="1024x1024",
        )
    except Exception as e:  # noqa: BLE001
        raise RuntimeError(f"OpenAI error: {e}") from e

    import httpx

    data = response.data[0]
    if data.b64_json:
        base64_image = data.b64_json
    elif data.url:
        img_response = httpx.get(data.url)
        img_response.raise_for_status()
        base64_image = base64.b64encode(img_response.content).decode("ascii")
    else:
        raise RuntimeError(f"OpenAI response missing image data: {response}")

    return "image/png", base64_image


async def generate_image_base64(model: str, prompt: str) -> Tuple[str, str]:
    if model not in MODELS:
        raise ValueError(f"Unknown model: {model}")

    if model == _KANDINSKY_MODEL:
        async with _kandinsky_generate_lock:
            pipe = await _get_kandinsky_pipeline()
            image: Image.Image = await asyncio.to_thread(_generate_kandinsky_sync, pipe, prompt)
            return _encode_pil_image_to_base64(image)

    if model == _STABILITY_MODEL:
        client = _get_stability_inference_client_hf_inference()
        try:
            image = await asyncio.to_thread(client.text_to_image, prompt, model=model)
        except HfHubHTTPError as e:
            raise RuntimeError(f"Model call failed for '{model}': {e}.") from e
        return _encode_pil_image_to_base64(image)

    if model in (_TITAN_MODEL, _NOVA_CANVAS_MODEL):
        return await asyncio.to_thread(_generate_aws_bedrock_image_sync, model, prompt)

    if model == _OPENAI_MODEL:
        return await asyncio.to_thread(_generate_openai_image_sync, model, prompt)

    image = await asyncio.to_thread(_generate_via_inference_client, model, prompt)
    return _encode_pil_image_to_base64(image)


__all__ = [
    "MODELS",
    "generate_image_base64",
]

