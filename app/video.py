import os
import base64
from typing import Tuple
from huggingface_hub import InferenceClient
from dotenv import load_dotenv

load_dotenv()

VIDEO_MODELS = [
    "Wan-AI/Wan2.2-T2V-A14B-Diffusers"
]

async def generate_video_base64(model: str, prompt: str) -> Tuple[str, str]:
    if model not in VIDEO_MODELS:
        raise ValueError(f"Unknown video model: {model}")

    client = InferenceClient(
        # provider="hf-inference",
        api_key=os.getenv("HF_TOKEN"),
    )

    # Note: text_to_video from InferenceClient typically returns bytes
    video_bytes = client.text_to_video(
        prompt,
        model=model,
    )

    mime_type = "video/mp4"
    video_base64 = base64.b64encode(video_bytes).decode("ascii")

    return mime_type, video_base64
