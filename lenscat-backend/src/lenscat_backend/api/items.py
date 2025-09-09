"""Item API endpoints."""
from datetime import datetime
from fastapi import APIRouter, Depends, HTTPException, Query, Body
from fastapi.responses import Response

import orjson

from ..models.types import Sidecar
from ..storage.base import StorageBackend
from ..utils import extract_exif
from .dependencies import get_storage_dependency as get_storage

router = APIRouter(prefix="/item", tags=["items"])


@router.get("", response_model=Sidecar)
async def get_item(
    path: str = Query(..., description="Item path"),
    storage: StorageBackend = Depends(get_storage)
):
    """Get item metadata, merging sidecar with EXIF."""
    try:
        # Check if image exists
        if not await storage.exists(path):
            raise HTTPException(status_code=404, detail="Image not found")
        
        sidecar_path = f"{path}.json"
        sidecar = None
        
        # Load existing sidecar if it exists
        if await storage.exists(sidecar_path):
            try:
                sidecar_data = await storage.read_text(sidecar_path)
                sidecar = Sidecar.parse_raw(sidecar_data)
            except Exception as e:
                print(f"Failed to parse sidecar for {path}: {e}")
        
        # If no sidecar exists, create basic one with EXIF
        if sidecar is None:
            exif_data = await extract_exif(storage, path)
            sidecar = Sidecar(
                tags=[],
                notes="",
                exif=exif_data,
                updatedAt=datetime.utcnow(),
                updatedBy="system"
            )
        
        return sidecar
        
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to get item: {str(e)}")


@router.put("", response_model=Sidecar)
async def update_item(
    path: str = Query(..., description="Item path"),
    sidecar: Sidecar = Body(...),
    storage: StorageBackend = Depends(get_storage)
):
    """Update item metadata."""
    try:
        # Check if image exists
        if not await storage.exists(path):
            raise HTTPException(status_code=404, detail="Image not found")
        
        sidecar_path = f"{path}.json"
        
        # Handle conflict resolution (last-writer-wins with additive tags)
        existing_sidecar = None
        if await storage.exists(sidecar_path):
            try:
                existing_data = await storage.read_text(sidecar_path)
                existing_sidecar = Sidecar.parse_raw(existing_data)
            except Exception:
                pass
        
        # Merge tags additively if there's an existing sidecar
        if existing_sidecar and existing_sidecar.updatedAt > sidecar.updatedAt:
            # Existing is newer, merge tags additively
            merged_tags = list(set(existing_sidecar.tags + sidecar.tags))
            sidecar.tags = merged_tags
            sidecar.updatedAt = datetime.utcnow()
        
        # Ensure EXIF is preserved if not provided
        if not sidecar.exif and existing_sidecar and existing_sidecar.exif:
            sidecar.exif = existing_sidecar.exif
        
        # Save updated sidecar
        sidecar_json = orjson.dumps(
            sidecar.dict(by_alias=True),
            option=orjson.OPT_UTC_Z | orjson.OPT_INDENT_2
        )
        
        await storage.write_bytes(sidecar_path, sidecar_json)
        
        return sidecar
        
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to update item: {str(e)}")


@router.delete("")
async def delete_item_metadata(
    path: str = Query(..., description="Item path"),
    storage: StorageBackend = Depends(get_storage)
):
    """Delete item sidecar metadata."""
    try:
        sidecar_path = f"{path}.json"
        
        if await storage.exists(sidecar_path):
            await storage.delete(sidecar_path)
            return {"message": "Metadata deleted"}
        else:
            raise HTTPException(status_code=404, detail="No metadata found")
            
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to delete metadata: {str(e)}")
