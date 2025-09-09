"""EXIF data extraction utilities."""
import asyncio
import io
from datetime import datetime
from typing import Optional

from PIL import Image
from PIL.ExifTags import TAGS

from ..models.types import ExifData
from ..storage.base import StorageBackend


async def extract_exif(storage: StorageBackend, image_path: str) -> Optional[ExifData]:
    """Extract basic EXIF data from an image."""
    try:
        # Read image data
        image_data = await storage.read_bytes(image_path)
        
        # Process in thread pool to avoid blocking
        loop = asyncio.get_event_loop()
        return await loop.run_in_executor(None, _extract_exif_sync, image_data)
        
    except Exception as e:
        print(f"Failed to extract EXIF from {image_path}: {e}")
        return None


def _extract_exif_sync(image_data: bytes) -> Optional[ExifData]:
    """Synchronous EXIF extraction."""
    try:
        with Image.open(io.BytesIO(image_data)) as image:
            # Get basic dimensions
            width, height = image.size
            created_at = None
            
            # Extract EXIF data if available
            exif_dict = image.getexif()
            if exif_dict:
                # Look for DateTime tags
                for tag_id, value in exif_dict.items():
                    tag = TAGS.get(tag_id, tag_id)
                    
                    if tag in ("DateTime", "DateTimeOriginal", "DateTimeDigitized"):
                        try:
                            # Parse datetime string
                            created_at = datetime.strptime(value, "%Y:%m:%d %H:%M:%S")
                            break
                        except (ValueError, TypeError):
                            continue
            
            return ExifData(
                width=width,
                height=height,
                createdAt=created_at
            )
            
    except Exception:
        return None
