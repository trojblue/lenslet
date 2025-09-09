from __future__ import annotations
import os
from dataclasses import dataclass

@dataclass(frozen=True)
class Settings:
    root_path: str = os.getenv("ROOT_PATH", "./data")
    s3_bucket: str | None = os.getenv("S3_BUCKET")
    s3_prefix: str = os.getenv("S3_PREFIX", "")
    aws_region: str | None = os.getenv("AWS_REGION")
    s3_endpoint: str | None = os.getenv("S3_ENDPOINT")
    thumb_long_edge: int = int(os.getenv("THUMB_LONG_EDGE", "256"))
    thumb_quality: int = int(os.getenv("THUMB_QUALITY", "70"))

settings = Settings()
