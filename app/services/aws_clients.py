from __future__ import annotations

import boto3
import json

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


def bedrock_response_guardrail_intervened(
    response: dict,
    payload: dict | None = None,
) -> bool:
    """
    Detect whether Bedrock Guardrails intervened for an invoke_model response.
    Checks both response headers and known payload fields.
    """
    headers = (
        response.get("ResponseMetadata", {})
        .get("HTTPHeaders", {})
    )
    for key, value in headers.items():
        key_l = str(key).lower()
        val_l = str(value).lower()
        if "guardrail" in key_l and val_l in {"intervened", "blocked"}:
            return True

    body = payload or {}
    action = (
        body.get("amazon-bedrock-guardrailAction")
        or body.get("guardrailAction")
        or ""
    )
    action_l = str(action).lower()
    return action_l in {"intervened", "blocked"}


def bedrock_guardrail_precheck_text(text: str, context_label: str = "input") -> None:
    """
    Run a lightweight Bedrock Guardrail gate over text before downstream services.
    Raises ValueError when content is blocked by Guardrails.
    """
    content = (text or "").strip()
    if not content:
        return

    guardrail_id = (settings.bedrock_guardrail_id or "").strip()
    if not guardrail_id:
        return

    model_id = (
        (settings.bedrock_claude_haiku_id or "").strip()
        or (settings.bedrock_claude_sonnet_id or "").strip()
    )
    if not model_id:
        raise RuntimeError(
            "Guardrail precheck requested but no Bedrock text model is configured "
            "(BEDROCK_CLAUDE_HAIKU_ID or BEDROCK_CLAUDE_SONNET_ID)."
        )

    bedrock = bedrock_runtime_client(region_name=settings.aws_region)
    body = {
        "anthropic_version": "bedrock-2023-05-31",
        "max_tokens": 16,
        "temperature": 0.0,
        "system": (
            "You are a safety gate checker. "
            "If the user input is allowed, respond with exactly: ALLOW. "
            "Do not include any extra words."
        ),
        "messages": [{"role": "user", "content": [{"type": "text", "text": content}]}],
    }

    try:
        response = bedrock_invoke_model(
            bedrock,
            modelId=model_id,
            body=json.dumps(body),
            accept="application/json",
            contentType="application/json",
        )
    except Exception as e:  # noqa: BLE001
        raise RuntimeError(f"Guardrail precheck failed for {context_label}: {e}") from e

    try:
        payload = json.loads(response["body"].read())
    except Exception as e:  # noqa: BLE001
        raise RuntimeError(f"Guardrail precheck returned invalid payload for {context_label}.") from e
    parts = payload.get("content", [])
    text_out = "\n".join(
        part.get("text", "").strip() for part in parts if isinstance(part, dict)
    ).strip()
    if text_out.upper() != "ALLOW":
        raise ValueError(f"{context_label} was blocked by safety guardrails.")


def redact_text_if_guardrail_blocked(
    text: str,
    context_label: str = "input",
    redacted_value: str = "[REDACTED]",
    run_guardrail_precheck: bool = False,
    blocked_by_guardrail: bool | None = None,
) -> str:
    """
    Return a guardrail-safe text for response echoes.
    Redacts only when a block is known:
    - blocked_by_guardrail=True, or
    - run_guardrail_precheck=True and precheck blocks.
    """
    content = (text or "").strip()
    if not content:
        return content
    if blocked_by_guardrail is True:
        return redacted_value
    if blocked_by_guardrail is False:
        return content
    if not run_guardrail_precheck:
        return content
    try:
        bedrock_guardrail_precheck_text(content, context_label=context_label)
    except ValueError:
        return redacted_value
    return content

