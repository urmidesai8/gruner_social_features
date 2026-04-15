from __future__ import annotations

import boto3

from app.core.config import settings


def aws_creds() -> tuple[str, str, str]:
    access_key = settings.aws_access_key
    secret_key = settings.aws_secret_key
    region = settings.aws_region or settings.aws_default_region or "ap-south-1"
    if not (access_key and secret_key):
        raise RuntimeError(
            "Missing AWS credentials in environment (AWS_ACCESS_KEY/AWS_SECRET_KEY)."
        )
    return access_key, secret_key, region


def aws_client(service_name: str, region_name: str | None = None):
    access_key, secret_key, default_region = aws_creds()
    return boto3.client(
        service_name,
        aws_access_key_id=access_key,
        aws_secret_access_key=secret_key,
        region_name=region_name or default_region,
    )


def s3_client(region_name: str | None = None):
    return aws_client("s3", region_name=region_name)


def transcribe_client(region_name: str | None = None):
    return aws_client("transcribe", region_name=region_name)


def polly_client(region_name: str | None = None):
    return aws_client("polly", region_name=region_name)


def translate_client(region_name: str | None = None):
    return aws_client("translate", region_name=region_name)


def bedrock_runtime_client(region_name: str | None = None):
    return aws_client("bedrock-runtime", region_name=region_name)


def bedrock_invoke_model(client, **kwargs):
    """
    Invoke Bedrock model with optional Guardrail configuration from settings.
    """
    guardrail_id = (settings.bedrock_guardrail_id or "").strip()
    guardrail_version = (settings.bedrock_guardrail_version or "").strip()
    guardrail_trace = (settings.bedrock_guardrail_trace or "").strip()

    if guardrail_id:
        kwargs["guardrailIdentifier"] = guardrail_id
        kwargs["guardrailVersion"] = guardrail_version or "DRAFT"
        if guardrail_trace:
            kwargs["trace"] = guardrail_trace

    return client.invoke_model(**kwargs)

