"""Thumbnail generation utilities."""
import asyncio
import io
from typing import Optional

try:
    import pyvips
    PYVIPS_AVAILABLE = True
except ImportError:
    PYVIPS_AVAILABLE = False
    pyvips = None

from PIL import Image

from ..storage.base import StorageBackend


class ThumbnailGenerator:
    """Handles thumbnail generation with pyvips fallback to PIL."""

    def __init__(self, max_size: int = 256, quality: int = 70):
        """Initialize thumbnail generator."""
        self.max_size = max_size
        self.quality = quality

    async def generate_thumbnail(
        self, 
        storage: StorageBackend, 
        image_path: str
    ) -> Optional[bytes]:
        """Generate thumbnail for an image."""
        try:
            # Read source image
            image_data = await storage.read_bytes(image_path)
            
            # Generate thumbnail using pyvips if available, otherwise PIL
            if PYVIPS_AVAILABLE:
                thumbnail_data = await self._generate_with_pyvips(image_data)
            else:
                thumbnail_data = await self._generate_with_pil(image_data)
            
            return thumbnail_data
            
        except Exception as e:
            print(f"Failed to generate thumbnail for {image_path}: {e}")
            return None

    async def _generate_with_pyvips(self, image_data: bytes) -> bytes:
        """Generate thumbnail using pyvips (faster)."""
        def _process():
            # Load image from memory
            image = pyvips.Image.new_from_buffer(image_data, "")
            
            # Calculate resize dimensions
            width, height = image.width, image.height
            if width > height:
                new_width = self.max_size
                new_height = int((height * self.max_size) / width)
            else:
                new_height = self.max_size
                new_width = int((width * self.max_size) / height)
            
            # Resize image
            resized = image.resize(new_width / width)
            
            # Convert to WebP
            return resized.webpsave_buffer(Q=self.quality)
        
        # Run in thread pool to avoid blocking
        loop = asyncio.get_event_loop()
        return await loop.run_in_executor(None, _process)

    async def _generate_with_pil(self, image_data: bytes) -> bytes:
        """Generate thumbnail using PIL (fallback)."""
        def _process():
            # Load image
            with Image.open(io.BytesIO(image_data)) as image:
                # Convert to RGB if necessary
                if image.mode in ("RGBA", "LA", "P"):
                    rgb_image = Image.new("RGB", image.size, (255, 255, 255))
                    if image.mode == "P":
                        image = image.convert("RGBA")
                    rgb_image.paste(image, mask=image.split()[-1] if image.mode in ("RGBA", "LA") else None)
                    image = rgb_image
                
                # Calculate resize dimensions
                width, height = image.size
                if width > height:
                    new_width = self.max_size
                    new_height = int((height * self.max_size) / width)
                else:
                    new_height = self.max_size
                    new_width = int((width * self.max_size) / height)
                
                # Resize with high quality
                thumbnail = image.resize((new_width, new_height), Image.Resampling.LANCZOS)
                
                # Save as WebP
                output = io.BytesIO()
                thumbnail.save(output, format="WEBP", quality=self.quality, optimize=True)
                return output.getvalue()
        
        # Run in thread pool
        loop = asyncio.get_event_loop()
        return await loop.run_in_executor(None, _process)

    async def ensure_thumbnail(
        self, 
        storage: StorageBackend, 
        image_path: str
    ) -> bool:
        """Ensure thumbnail exists, generate if missing."""
        thumb_path = f"{image_path}.thumbnail"
        
        # Check if thumbnail already exists
        if await storage.exists(thumb_path):
            return True
        
        # Generate thumbnail
        thumbnail_data = await self.generate_thumbnail(storage, image_path)
        if thumbnail_data is None:
            return False
        
        # Save thumbnail
        try:
            await storage.write_bytes(thumb_path, thumbnail_data)
            return True
        except Exception as e:
            print(f"Failed to save thumbnail for {image_path}: {e}")
            return False
