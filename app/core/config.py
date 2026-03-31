"""
Central application configuration.

For now this is a thin wrapper around environment variables so that configuration
access is centralized and easy to evolve later (e.g. with pydantic-settings).
"""

from functools import lru_cache
import os
from typing import Optional


class Settings:
    hf_token: Optional[str]
    aws_access_key: Optional[str]
    aws_secret_key: Optional[str]
    aws_region: Optional[str]

    def __init__(self) -> None:
        self.hf_token = os.getenv("HF_TOKEN")
        self.aws_access_key = os.getenv("AWS_ACCESS_KEY")
        self.aws_secret_key = os.getenv("AWS_SECRET_KEY")
        self.aws_region = os.getenv("AWS_REGION", "us-east-1")


@lru_cache(maxsize=1)
def get_settings() -> Settings:
    return Settings()

