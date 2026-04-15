"""
AWS Translate: list supported languages and translate text.
Uses AWS_ACCESS_KEY, AWS_SECRET_KEY, AWS_REGION from the environment.
"""

from __future__ import annotations

import asyncio
from typing import Any, Dict, List

from dotenv import load_dotenv
from app.core.config import settings
from app.services.aws_clients import translate_client

load_dotenv()

# AWS Translate synchronous limit for TranslateText (UTF-8 bytes for standard).
_MAX_TEXT_BYTES = 10_000


def _translate_client():
    return translate_client(region_name=settings.aws_region)


def _list_languages_sync() -> List[Dict[str, str]]:
    import botocore.exceptions

    client = _translate_client()
    languages: List[Dict[str, str]] = []
    token: str | None = None
    try:
        while True:
            kwargs: Dict[str, Any] = {
                "DisplayLanguageCode": "en",
                "MaxResults": 500,
            }
            if token:
                kwargs["NextToken"] = token
            resp = client.list_languages(**kwargs)
            for row in resp.get("Languages", []) or []:
                code = (row.get("LanguageCode") or "").strip()
                name = (row.get("LanguageName") or code or "").strip()
                if code:
                    languages.append({"code": code, "name": name})
            token = resp.get("NextToken")
            if not token:
                break
    except botocore.exceptions.ClientError as e:
        msg = e.response.get("Error", {}).get("Message", str(e))
        raise RuntimeError(f"AWS Translate list_languages error: {msg}") from e

    # De-duplicate by code (stable order: sort by name)
    seen: set[str] = set()
    unique: List[Dict[str, str]] = []
    for item in sorted(languages, key=lambda x: (x["name"].lower(), x["code"])):
        if item["code"] in seen:
            continue
        seen.add(item["code"])
        unique.append(item)
    return unique


def _resolve_target_language_code(raw: str, languages: List[Dict[str, str]]) -> str:
    """
    Map user-facing target (code, display name, or "Name (code)" from UI) to AWS LanguageCode.
    Uses the same catalog as list_translate_languages().
    """
    s = (raw or "").strip()
    if not s:
        raise ValueError("target_language is required.")
    s_lower = s.lower()

    for item in languages:
        if item["code"].lower() == s_lower:
            return item["code"]

    for item in languages:
        if item["name"].lower() == s_lower:
            return item["code"]

    if "(" in s and s.rstrip().endswith(")"):
        inner = s[s.rfind("(") + 1 : -1].strip().lower()
        for item in languages:
            if item["code"].lower() == inner:
                return item["code"]

    for item in languages:
        name_l = item["name"].lower()
        if name_l in s_lower or s_lower in name_l:
            return item["code"]

    raise ValueError(
        f"Unknown target language {raw!r}. Use a supported language code or name from Amazon Translate."
    )


def _translate_text_sync(
    text: str,
    source_language_code: str,
    target_language: str,
) -> Dict[str, str]:
    import botocore.exceptions

    src = (source_language_code or "auto").strip().lower()
    languages = _list_languages_sync()
    tgt = _resolve_target_language_code(target_language, languages)
    tgt_lower = tgt.lower()

    if src != "auto" and src == tgt_lower:
        raise ValueError("Source and target language must differ.")
    raw = text.encode("utf-8")
    if len(raw) > _MAX_TEXT_BYTES:
        raise ValueError(
            f"Text exceeds Amazon Translate limit of {_MAX_TEXT_BYTES} UTF-8 bytes "
            f"(got {len(raw)}). Shorten the input or split into chunks."
        )

    client = _translate_client()
    try:
        resp = client.translate_text(
            Text=text,
            SourceLanguageCode=src,
            TargetLanguageCode=tgt,
        )
    except botocore.exceptions.ClientError as e:
        msg = e.response.get("Error", {}).get("Message", str(e))
        raise RuntimeError(f"AWS Translate error: {msg}") from e

    out = (resp.get("TranslatedText") or "").strip()
    detected = (resp.get("SourceLanguageCode") or src).strip()
    if not out:
        raise RuntimeError("Amazon Translate returned empty translated text.")

    detected_l = detected.lower()
    if detected_l == tgt_lower:
        raise ValueError("Source and target language must differ.")

    return {
        "translated_text": out,
        "source_language_code": detected,
        "target_language_code": tgt,
    }


async def list_translate_languages() -> List[Dict[str, str]]:
    return await asyncio.to_thread(_list_languages_sync)


async def translate_post_text(
    text: str,
    source_language_code: str,
    target_language: str,
) -> Dict[str, str]:
    return await asyncio.to_thread(
        _translate_text_sync,
        text,
        source_language_code,
        target_language,
    )


__all__ = [
    "list_translate_languages",
    "translate_post_text",
]
