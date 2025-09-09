"""S3 storage backend."""
import asyncio
from typing import List, Optional, Tuple
from urllib.parse import quote

import aioboto3
from botocore.exceptions import ClientError, NoCredentialsError
from PIL import Image
import io

from ..models.types import DirEntry, DirKind, Item, MimeType
from .base import StorageBackend


class S3Storage(StorageBackend):
    """S3 storage implementation."""

    def __init__(self, bucket: str, prefix: str = "", region: str = "us-east-1"):
        """Initialize S3 storage."""
        self.bucket = bucket
        self.prefix = prefix.rstrip("/")
        self.region = region
        self.session = aioboto3.Session()

    def _full_path(self, path: str) -> str:
        """Get full S3 key with prefix."""
        clean_path = path.lstrip("/")
        if self.prefix:
            return f"{self.prefix}/{clean_path}"
        return clean_path

    async def exists(self, path: str) -> bool:
        """Check if S3 object exists."""
        try:
            async with self.session.client("s3", region_name=self.region) as s3:
                await s3.head_object(Bucket=self.bucket, Key=self._full_path(path))
                return True
        except ClientError as e:
            if e.response["Error"]["Code"] == "404":
                return False
            raise

    async def read_bytes(self, path: str) -> bytes:
        """Read S3 object as bytes."""
        async with self.session.client("s3", region_name=self.region) as s3:
            response = await s3.get_object(Bucket=self.bucket, Key=self._full_path(path))
            return await response["Body"].read()

    async def read_text(self, path: str) -> str:
        """Read S3 object as text."""
        data = await self.read_bytes(path)
        return data.decode("utf-8")

    async def write_bytes(self, path: str, data: bytes) -> None:
        """Write bytes to S3."""
        async with self.session.client("s3", region_name=self.region) as s3:
            await s3.put_object(
                Bucket=self.bucket,
                Key=self._full_path(path),
                Body=data
            )

    async def write_text(self, path: str, content: str) -> None:
        """Write text to S3."""
        await self.write_bytes(path, content.encode("utf-8"))

    async def list_directory(self, path: str) -> Tuple[List[DirEntry], List[Item]]:
        """List S3 directory contents."""
        prefix = self._full_path(path)
        if prefix and not prefix.endswith("/"):
            prefix += "/"

        dirs = []
        items = []
        seen_dirs = set()

        async with self.session.client("s3", region_name=self.region) as s3:
            paginator = s3.get_paginator("list_objects_v2")
            
            async for page in paginator.paginate(
                Bucket=self.bucket, 
                Prefix=prefix,
                Delimiter="/"
            ):
                # Handle directories (common prefixes)
                for common_prefix in page.get("CommonPrefixes", []):
                    dir_name = common_prefix["Prefix"][len(prefix):].rstrip("/")
                    if dir_name and dir_name not in seen_dirs:
                        seen_dirs.add(dir_name)
                        # TODO: Determine if branch/leaf-real/leaf-pointer
                        dirs.append(DirEntry(name=dir_name, kind=DirKind.BRANCH))

                # Handle files
                for obj in page.get("Contents", []):
                    key = obj["Key"]
                    if key == prefix:  # Skip the directory itself
                        continue
                    
                    rel_key = key[len(prefix):]
                    if "/" in rel_key:  # Skip nested files
                        continue
                    
                    if self._is_image_file(rel_key):
                        # Get image info
                        try:
                            info = await self.get_file_info(key[len(self.prefix)+1:] if self.prefix else key)
                            if info:
                                w, h, size = info
                                
                                # Check for sidecar and thumbnail
                                has_meta = await self.exists(f"{key}.json")
                                has_thumb = await self.exists(f"{key}.thumbnail")
                                
                                items.append(Item(
                                    path=key[len(self.prefix)+1:] if self.prefix else key,
                                    name=rel_key,
                                    type=self._get_mime_type(rel_key),
                                    w=w,
                                    h=h,
                                    size=size,
                                    hasThumb=has_thumb,
                                    hasMeta=has_meta
                                ))
                        except Exception:
                            continue

        return dirs, items

    async def get_file_info(self, path: str) -> Optional[Tuple[int, int, int]]:
        """Get S3 object info: (width, height, size)."""
        try:
            if not self._is_image_file(path):
                return None
            
            # Get object metadata first for size
            async with self.session.client("s3", region_name=self.region) as s3:
                response = await s3.head_object(
                    Bucket=self.bucket,
                    Key=self._full_path(path)
                )
                size = response["ContentLength"]
                
                # Download image to get dimensions
                obj_response = await s3.get_object(
                    Bucket=self.bucket,
                    Key=self._full_path(path)
                )
                data = await obj_response["Body"].read()
                
                with Image.open(io.BytesIO(data)) as img:
                    w, h = img.size
                
                return w, h, size
        except Exception:
            return None

    async def delete(self, path: str) -> None:
        """Delete S3 object."""
        async with self.session.client("s3", region_name=self.region) as s3:
            await s3.delete_object(Bucket=self.bucket, Key=self._full_path(path))

    def get_public_url(self, path: str) -> str:
        """Get public S3 URL."""
        key = self._full_path(path)
        return f"https://{self.bucket}.s3.{self.region}.amazonaws.com/{quote(key)}"

    async def health_check(self) -> dict:
        """Return S3 health status."""
        try:
            async with self.session.client("s3", region_name=self.region) as s3:
                # Test basic access
                await s3.head_bucket(Bucket=self.bucket)
                return {
                    "type": "s3",
                    "bucket": self.bucket,
                    "prefix": self.prefix,
                    "region": self.region,
                    "accessible": True,
                }
        except NoCredentialsError:
            return {
                "type": "s3",
                "bucket": self.bucket,
                "accessible": False,
                "error": "No AWS credentials found",
            }
        except ClientError as e:
            return {
                "type": "s3",
                "bucket": self.bucket,
                "accessible": False,
                "error": str(e),
            }

    def _is_image_file(self, path: str) -> bool:
        """Check if file is a supported image."""
        return path.lower().endswith((".jpg", ".jpeg", ".png", ".webp"))

    def _get_mime_type(self, path: str) -> MimeType:
        """Get MIME type from file extension."""
        ext = path.lower().split(".")[-1]
        if ext in {"jpg", "jpeg"}:
            return MimeType.JPEG
        elif ext == "png":
            return MimeType.PNG
        elif ext == "webp":
            return MimeType.WEBP
        else:
            return MimeType.JPEG  # fallback
