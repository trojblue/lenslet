from __future__ import annotations
import os, asyncio
from ..config import settings
from ..storage.local import LocalStorage
from ..storage.s3 import S3Storage
from .indexer import walk_and_index, build_rollup

async def main():
    if settings.s3_bucket:
        storage = S3Storage(settings.s3_bucket, settings.s3_prefix, settings.aws_region, settings.s3_endpoint)
    else:
        storage = LocalStorage(settings.root_path)
    root = ""  # logical root inside storage
    await walk_and_index(storage, root)
    await build_rollup(storage, root)

if __name__ == '__main__':
    asyncio.run(main())
