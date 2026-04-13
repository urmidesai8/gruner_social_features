from __future__ import annotations

import os

import boto3


def aws_creds() -> tuple[str, str, str]:
    access_key = os.getenv("AWS_ACCESS_KEY")
    secret_key = os.getenv("AWS_SECRET_KEY")
    region = os.getenv("AWS_REGION", "us-east-1")
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

