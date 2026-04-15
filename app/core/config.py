from functools import lru_cache
from typing import Optional

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    hf_token: Optional[str] = None
    aws_access_key: Optional[str] = None
    aws_secret_key: Optional[str] = None
    aws_region: str = "ap-south-1"
    aws_default_region: str = "ap-south-1"

    aws_region_bedrock_image: str = "us-west-2"
    aws_region_bedrock_nova_canvas: str = "us-east-1"
    aws_region_bedrock_nova_reel: str = "us-east-1"
    aws_region_nova_reel_s3: Optional[str] = None

    openai_key: Optional[str] = None
    nova_reel_bucket: Optional[str] = None
    transcribe_bucket: Optional[str] = None
    transcribe_language_code: Optional[str] = None
    transcribe_timeout_seconds: float = 300

    bedrock_claude_haiku_id: Optional[str] = None
    bedrock_claude_sonnet_id: Optional[str] = None
    bedrock_guardrail_id: Optional[str] = None
    bedrock_guardrail_version: Optional[str] = None
    bedrock_guardrail_trace: Optional[str] = None

    blip_model_id: str = "Salesforce/blip-image-captioning-large"
    blip_conditioning_text: str = "A photo of"

    quote_card_font_path: Optional[str] = None
    polly_voice_id: Optional[str] = None
    polly_engine: str = "neural"
    polly_track_volume_gain: str = ""

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        case_sensitive=False,
        extra="ignore",
    )


@lru_cache(maxsize=1)
def get_settings() -> Settings:
    """Return a cached settings instance."""

    return Settings()


settings = get_settings()

