import json
import logging
import os
import time

from app.services.aws_clients import bedrock_runtime_client


logger = logging.getLogger("uvicorn.error")


async def summarize_post_text(text: str) -> str:
    """
    Turn a long post into a short, easy-to-read summary (bullets) using Claude Haiku.
    """
    import botocore.exceptions

    model_id = os.getenv("BEDROCK_CLAUDE_HAIKU_ID")
    if not model_id:
        raise RuntimeError("Missing BEDROCK_CLAUDE_HAIKU_ID in environment.")

    bedrock = bedrock_runtime_client(region_name=os.getenv("AWS_REGION"))

    system_prompt = (
        "You help busy readers understand long social posts and articles. "
        "Read the user's text and respond with exactly 3–5 bullet points. "
        "Each bullet must be one short, plain-language sentence (easy for a general audience). "
        "Capture the main ideas and implications; avoid jargon unless you briefly explain it. "
        "Do not use a title line, preamble, or closing ('Here is a summary', etc.). "
        "Start directly with the first bullet (use • or - for bullets). "
        "If the text is already short, still distil it into at most 3 bullets."
    )

    body = {
        "anthropic_version": "bedrock-2023-05-31",
        "max_tokens": 900,
        "temperature": 0.4,
        "system": system_prompt,
        "messages": [{"role": "user", "content": [{"type": "text", "text": text}]}],
    }

    t0 = time.perf_counter()
    logger.info("summarize-post: step=llm start text_len=%d", len(text or ""))

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
            "summarize-post: step=llm error elapsed_ms=%d",
            int((time.perf_counter() - t0) * 1000),
        )
        raise RuntimeError(f"Bedrock Claude Haiku error: {error_message}") from e

    payload = json.loads(response["body"].read())
    content = payload.get("content", [])
    parts = [part.get("text", "") for part in content if isinstance(part, dict)]
    result = "\n".join(p.strip() for p in parts if p.strip()).strip()
    if not result:
        logger.error(
            "summarize-post: step=llm empty_result elapsed_ms=%d",
            int((time.perf_counter() - t0) * 1000),
        )
        raise RuntimeError("Claude Haiku returned empty text for summarise.")

    lower_result = result.lower()
    leadins = (
        "here is a summary:",
        "here's a summary:",
        "summary:",
        "here are the key points:",
        "key points:",
        "bullet points:",
        "here are 3 key points:",
    )
    for lead in leadins:
        if lower_result.startswith(lead):
            result = result[len(lead) :].lstrip()
            break

    logger.info(
        "summarize-post: step=llm done elapsed_ms=%d result_len=%d",
        int((time.perf_counter() - t0) * 1000),
        len(result),
    )
    return result


__all__ = [
    "summarize_post_text",
]

