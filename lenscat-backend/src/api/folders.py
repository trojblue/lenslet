"""Folder API endpoints."""
from fastapi import APIRouter, Depends, HTTPException, Query
from typing import Optional

from ..models.types import FolderIndex
from ..storage.base import StorageBackend
from ..workers.indexer import FolderIndexer
from .dependencies import get_storage_dependency as get_storage

router = APIRouter(prefix="/folders", tags=["folders"])


@router.get("", response_model=FolderIndex)
async def get_folder(
    path: str = Query(..., description="Folder path to list"),
    page: Optional[int] = Query(None, description="Page number for pagination"),
    storage: StorageBackend = Depends(get_storage)
):
    """Get folder contents, building index if missing or stale."""
    try:
        indexer = FolderIndexer(storage)
        
        # Clean up path
        folder_path = path.strip("/")
        if not folder_path:
            folder_path = ""
        
        # Check if we have a valid index
        index_path = f"{folder_path}/_index.json" if folder_path else "_index.json"
        
        if await storage.exists(index_path) and not await indexer.is_index_stale(folder_path):
            # Load existing index
            try:
                index_data = await storage.read_text(index_path)
                index = FolderIndex.parse_raw(index_data)
                
                # Handle pagination if requested
                if page is not None:
                    # Simple pagination (could be optimized)
                    page_size = 100
                    start_idx = page * page_size
                    end_idx = start_idx + page_size
                    
                    total_items = len(index.items)
                    page_count = (total_items + page_size - 1) // page_size
                    
                    index.items = index.items[start_idx:end_idx]
                    index.page = page
                    index.pageCount = page_count
                
                return index
                
            except Exception as e:
                print(f"Failed to load existing index: {e}")
                # Fall through to rebuild
        
        # Build new index
        index = await indexer.build_and_save_index(folder_path)
        
        # Handle pagination
        if page is not None:
            page_size = 100
            start_idx = page * page_size
            end_idx = start_idx + page_size
            
            total_items = len(index.items)
            page_count = (total_items + page_size - 1) // page_size
            
            index.items = index.items[start_idx:end_idx]
            index.page = page
            index.pageCount = page_count
        
        return index
        
    except Exception as e:
        print(f"Error getting folder {path}: {e}")
        raise HTTPException(status_code=500, detail=f"Failed to get folder: {str(e)}")


@router.post("/{folder_path:path}/reindex")
async def reindex_folder(
    folder_path: str,
    storage: StorageBackend = Depends(get_storage)
):
    """Force reindex of a folder."""
    try:
        indexer = FolderIndexer(storage)
        index = await indexer.build_and_save_index(folder_path)
        
        return {
            "message": f"Reindexed folder: {folder_path}",
            "items_count": len(index.items),
            "dirs_count": len(index.dirs)
        }
        
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to reindex: {str(e)}")
