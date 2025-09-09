"""Thumbnail API endpoints."""
from fastapi import APIRouter, Depends, HTTPException, Query
from fastapi.responses import Response
from typing import Optional

from ..storage.base import StorageBackend
from ..utils.thumbnails import ThumbnailGenerator
from .dependencies import get_storage_dependency as get_storage

router = APIRouter(prefix="/thumb", tags=["thumbnails"])


@router.get("")
async def get_thumbnail(
    path: str = Query(..., description="Image path"),
    storage: StorageBackend = Depends(get_storage)
):
    """Get thumbnail for an image, generate if missing."""
    try:
        # Check if image exists
        if not await storage.exists(path):
            raise HTTPException(status_code=404, detail="Image not found")
        
        thumbnail_path = f"{path}.thumbnail"
        
        # Return existing thumbnail if available
        if await storage.exists(thumbnail_path):
            try:
                thumbnail_data = await storage.read_bytes(thumbnail_path)
                return Response(
                    content=thumbnail_data,
                    media_type="image/webp",
                    headers={
                        "Cache-Control": "public, max-age=86400",  # Cache for 1 day
                        "ETag": f'"{hash(thumbnail_data)}"'
                    }
                )
            except Exception as e:
                print(f"Failed to read existing thumbnail for {path}: {e}")
                # Fall through to regenerate
        
        # Generate thumbnail on demand
        generator = ThumbnailGenerator()
        thumbnail_data = await generator.generate_thumbnail(storage, path)
        
        if thumbnail_data is None:
            raise HTTPException(status_code=500, detail="Failed to generate thumbnail")
        
        # Save thumbnail for future use
        try:
            await storage.write_bytes(thumbnail_path, thumbnail_data)
        except Exception as e:
            print(f"Failed to save thumbnail for {path}: {e}")
            # Continue anyway, we can still return the generated thumbnail
        
        return Response(
            content=thumbnail_data,
            media_type="image/webp",
            headers={
                "Cache-Control": "public, max-age=86400",
                "ETag": f'"{hash(thumbnail_data)}"'
            }
        )
        
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to get thumbnail: {str(e)}")


@router.post("")
async def generate_thumbnail(
    path: str = Query(..., description="Image path"),
    force: bool = Query(False, description="Force regeneration even if exists"),
    storage: StorageBackend = Depends(get_storage)
):
    """Generate thumbnail for an image."""
    try:
        # Check if image exists
        if not await storage.exists(path):
            raise HTTPException(status_code=404, detail="Image not found")
        
        thumbnail_path = f"{path}.thumbnail"
        
        # Check if thumbnail already exists and force is not set
        if not force and await storage.exists(thumbnail_path):
            return {"message": "Thumbnail already exists", "path": thumbnail_path}
        
        # Generate thumbnail
        generator = ThumbnailGenerator()
        success = await generator.ensure_thumbnail(storage, path)
        
        if success:
            return {"message": "Thumbnail generated successfully", "path": thumbnail_path}
        else:
            raise HTTPException(status_code=500, detail="Failed to generate thumbnail")
            
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to generate thumbnail: {str(e)}")


@router.delete("")
async def delete_thumbnail(
    path: str = Query(..., description="Image path"),
    storage: StorageBackend = Depends(get_storage)
):
    """Delete thumbnail for an image."""
    try:
        thumbnail_path = f"{path}.thumbnail"
        
        if await storage.exists(thumbnail_path):
            await storage.delete(thumbnail_path)
            return {"message": "Thumbnail deleted"}
        else:
            raise HTTPException(status_code=404, detail="Thumbnail not found")
            
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to delete thumbnail: {str(e)}")
