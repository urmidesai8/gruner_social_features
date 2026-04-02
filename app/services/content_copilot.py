import json
import logging
import os
import time


logger = logging.getLogger("uvicorn.error")


async def generate_copilot_text(mode: str, text: str) -> str:
    """
    AI Content Co-Pilot using Claude Haiku.

    - mode == "generate": turn a short idea into a full caption.
    - mode == "rewrite": improve/clarify an existing caption.
    - mode == "ideas": brainstorm several post ideas.
    """
    import boto3
    import botocore.exceptions

    model_id = os.getenv("BEDROCK_CLAUDE_HAIKU_ID")
    if not model_id:
        raise RuntimeError("Missing BEDROCK_CLAUDE_HAIKU_ID in environment.")

    aws_access_key_id = os.getenv("AWS_ACCESS_KEY")
    aws_secret_access_key = os.getenv("AWS_SECRET_KEY")
    if not (aws_access_key_id and aws_secret_access_key):
        raise RuntimeError("Missing AWS credentials in environment for Bedrock Claude Haiku.")

    bedrock = boto3.client(
        "bedrock-runtime",
        region_name=os.getenv("AWS_REGION"),
        aws_access_key_id=aws_access_key_id,
        aws_secret_access_key=aws_secret_access_key,
    )

    base_system = (
        "You are an AI content co-pilot helping users write short, engaging social media posts. "
        "Your tone should be confident, friendly, and authentic. Avoid emojis and hashtags unless explicitly requested."
    )
    if mode == "rewrite":
        task_instruction = (
            "Rewrite the following caption to be clearer, more confident, and engaging. "
            "Keep the meaning, keep it under 3-4 lines, and return only the rewritten caption text. "
            "Do not add any prefix like 'Here is a rewritten version' or any explanatory sentence."
        )
    elif mode == "ideas":
        task_instruction = (
            "Brainstorm 3–5 specific post ideas or caption angles based on the topic. "
            "Return them as a short numbered list; keep each item to 1–2 sentences."
        )
    else:
        task_instruction = (
            "Turn the following idea or fragment into a complete, polished caption suitable for a social media post. "
            "Keep it concise (2–5 sentences) and focused on a single clear message. Return only the caption text."
        )

    system_prompt = f"{base_system} {task_instruction}"
    body = {
        "anthropic_version": "bedrock-2023-05-31",
        "max_tokens": 260,
        "temperature": 0.7,
        "system": system_prompt,
        "messages": [{"role": "user", "content": [{"type": "text", "text": text}]}],
    }

    t0 = time.perf_counter()
    logger.info("copilot: step=llm start mode=%s text_len=%d", mode, len(text or ""))

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
            "copilot: step=llm error mode=%s elapsed_ms=%d",
            mode,
            int((time.perf_counter() - t0) * 1000),
        )
        raise RuntimeError(f"Bedrock Claude Haiku error: {error_message}") from e

    payload = json.loads(response["body"].read())
    content = payload.get("content", [])
    parts = [part.get("text", "") for part in content if isinstance(part, dict)]
    result = "\n".join(p.strip() for p in parts if p.strip()).strip()
    if not result:
        logger.error(
            "copilot: step=llm empty_result mode=%s elapsed_ms=%d",
            mode,
            int((time.perf_counter() - t0) * 1000),
        )
        raise RuntimeError("Claude Haiku returned empty text for Content Co-Pilot.")

    # Guardrail cleanup: strip occasional boilerplate lead-ins from LLM output.
    lower_result = result.lower()
    leadins = [
        "here is a rewritten version of the caption:",
        "here's a rewritten version of the caption:",
        "rewritten caption:",
        "here is your rewritten caption:",
        "here's your rewritten caption:",
    ]
    for lead in leadins:
        if lower_result.startswith(lead):
            result = result[len(lead) :].lstrip()
            break

    logger.info(
        "copilot: step=llm done mode=%s elapsed_ms=%d result_len=%d",
        mode,
        int((time.perf_counter() - t0) * 1000),
        len(result),
    )
    return result


__all__ = [
    "generate_copilot_text",
]

