"""Thumbnail generation worker."""
import asyncio
from typing import List

from ..storage.base import StorageBackend
from ..utils.thumbnails import ThumbnailGenerator


class ThumbnailWorker:
    """Worker for generating missing thumbnails."""

    def __init__(self, storage: StorageBackend, max_concurrent: int = 4):
        """Initialize thumbnail worker."""
        self.storage = storage
        self.generator = ThumbnailGenerator()
        self.max_concurrent = max_concurrent
        self._semaphore = asyncio.Semaphore(max_concurrent)

    async def generate_missing_thumbnails(self, folder_path: str) -> int:
        """Generate thumbnails for all images missing them in a folder."""
        _, items = await self.storage.list_directory(folder_path)
        
        # Find items without thumbnails
        missing_thumbs = [item for item in items if not item.hasThumb]
        
        if not missing_thumbs:
            return 0
        
        # Generate thumbnails concurrently
        tasks = [
            self._generate_thumbnail_safe(item.path)
            for item in missing_thumbs
        ]
        
        results = await asyncio.gather(*tasks, return_exceptions=True)
        
        # Count successful generations
        success_count = sum(1 for result in results if result is True)
        
        print(f"Generated {success_count}/{len(missing_thumbs)} thumbnails for {folder_path}")
        return success_count

    async def _generate_thumbnail_safe(self, image_path: str) -> bool:
        """Generate thumbnail with concurrency control."""
        async with self._semaphore:
            try:
                return await self.generator.ensure_thumbnail(self.storage, image_path)
            except Exception as e:
                print(f"Failed to generate thumbnail for {image_path}: {e}")
                return False

    async def process_folder_recursive(self, root_path: str) -> int:
        """Process all folders recursively to generate missing thumbnails."""
        total_generated = 0
        
        try:
            # Process current folder
            generated = await self.generate_missing_thumbnails(root_path)
            total_generated += generated
            
            # Get subdirectories
            dirs, _ = await self.storage.list_directory(root_path)
            
            # Process subdirectories
            for dir_entry in dirs:
                subdir_path = f"{root_path.rstrip('/')}/{dir_entry.name}"
                subdir_generated = await self.process_folder_recursive(subdir_path)
                total_generated += subdir_generated
                
        except Exception as e:
            print(f"Error processing folder {root_path}: {e}")
        
        return total_generated

    async def get_thumbnail_stats(self, folder_path: str) -> dict:
        """Get thumbnail statistics for a folder."""
        try:
            _, items = await self.storage.list_directory(folder_path)
            
            total_images = len(items)
            with_thumbs = sum(1 for item in items if item.hasThumb)
            missing_thumbs = total_images - with_thumbs
            
            return {
                "total_images": total_images,
                "with_thumbnails": with_thumbs,
                "missing_thumbnails": missing_thumbs,
                "coverage_percent": (with_thumbs / total_images * 100) if total_images > 0 else 100
            }
            
        except Exception as e:
            return {"error": str(e)}
