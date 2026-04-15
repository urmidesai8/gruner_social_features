from typing import Tuple

import asyncio
import base64

from dotenv import load_dotenv
from huggingface_hub import InferenceClient
from app.core.config import settings
from app.services.aws_clients import bedrock_runtime_client, s3_client

load_dotenv()

VIDEO_MODELS = [
    "amazon.nova-reel-v1:1",
]

_NOVA_REEL_MODEL = "amazon.nova-reel-v1:1"


def _generate_nova_reel_video_sync(prompt: str) -> Tuple[str, str]:
    import random
    import time

    import botocore.exceptions

    AWS_REGION = settings.aws_region_bedrock_nova_reel
    SLEEP_SECONDS = 30

    bucket_uri = settings.nova_reel_bucket
    if not bucket_uri:
        raise RuntimeError("Missing NOVA_REEL_BUCKET environment variable for Nova Reel output.")
    if not bucket_uri.startswith("s3://"):
        bucket_uri = f"s3://{bucket_uri}"

    bedrock_runtime = bedrock_runtime_client(region_name=AWS_REGION)

    model_input = {
        "taskType": "MULTI_SHOT_AUTOMATED",
        "multiShotAutomatedParams": {"text": prompt},
        "videoGenerationConfig": {
            "durationSeconds": 12,
            "fps": 24,
            "dimension": "1280x720",
            "seed": random.randint(0, 2147483648),
        },
    }

    invocation = bedrock_runtime.start_async_invoke(
        modelId=_NOVA_REEL_MODEL,
        modelInput=model_input,
        outputDataConfig={"s3OutputDataConfig": {"s3Uri": bucket_uri}},
    )

    invocation_arn = invocation["invocationArn"]

    while True:
        response = bedrock_runtime.get_async_invoke(invocationArn=invocation_arn)
        status = response["status"]
        if status != "InProgress":
            break
        time.sleep(SLEEP_SECONDS)

    if status != "Completed":
        raise RuntimeError(f"Video generation status: {status}")

    job_id = invocation_arn.split("/")[-1]

    without_scheme = bucket_uri[len("s3://") :]
    if "/" in without_scheme:
        bucket_name, base_prefix = without_scheme.split("/", 1)
        base_prefix = base_prefix.rstrip("/")
        key_prefix = f"{base_prefix}/{job_id}"
    else:
        bucket_name = without_scheme
        key_prefix = job_id

    video_key = f"{key_prefix}/output.mp4"

    s3 = s3_client(region_name=settings.aws_region_nova_reel_s3 or AWS_REGION)
    try:
        obj = s3.get_object(Bucket=bucket_name, Key=video_key)
    except botocore.exceptions.ClientError as e:
        error_message = e.response.get("Error", {}).get("Message", str(e))
        raise RuntimeError(f"Failed to fetch generated video from S3: {error_message}") from e

    video_bytes = obj["Body"].read()
    mime_type = "video/mp4"
    video_base64 = base64.b64encode(video_bytes).decode("ascii")
    return mime_type, video_base64


async def generate_video_base64(model: str, prompt: str) -> Tuple[str, str]:
    if model not in VIDEO_MODELS:
        raise ValueError(f"Unknown video model: {model}")

    if model == _NOVA_REEL_MODEL:
        return await asyncio.to_thread(_generate_nova_reel_video_sync, prompt)

    client = InferenceClient(
        api_key=settings.hf_token,
    )

    video_bytes = client.text_to_video(
        prompt,
        model=model,
    )

    mime_type = "video/mp4"
    video_base64 = base64.b64encode(video_bytes).decode("ascii")
    return mime_type, video_base64


__all__ = [
    "VIDEO_MODELS",
    "generate_video_base64",
]

