from __future__ import annotations
import os
from dataclasses import dataclass

@dataclass(frozen=True)
class Settings:
    # Restrict ROOT_PATH to an absolute path; default stays within repo's data dir
    root_path: str = os.path.abspath(os.getenv("ROOT_PATH", "./data"))
    s3_bucket: str | None = os.getenv("S3_BUCKET")
    s3_prefix: str = os.getenv("S3_PREFIX", "")
    aws_region: str | None = os.getenv("AWS_REGION")
    s3_endpoint: str | None = os.getenv("S3_ENDPOINT")
    thumb_long_edge: int = int(os.getenv("THUMB_LONG_EDGE", "256"))
    thumb_quality: int = int(os.getenv("THUMB_QUALITY", "70"))
    frontend_dist: str = os.getenv("FRONTEND_DIST", os.path.abspath(os.path.join(os.path.dirname(__file__), "../../../../lenscat-lite/dist")))
    # Worker concurrency controls
    index_concurrency: int = int(os.getenv("INDEX_CONCURRENCY", str(os.cpu_count() or 4)))
    progress_interval_s: float = float(os.getenv("PROGRESS_INTERVAL_S", "2.0"))

settings = Settings()
