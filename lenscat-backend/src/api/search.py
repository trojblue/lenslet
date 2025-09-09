"""Search API endpoints."""
from fastapi import APIRouter, Depends, HTTPException, Query
from typing import List

from ..models.types import RollupManifest, SearchResult, RollupItem
from ..storage.base import StorageBackend
from ..workers.indexer import RollupBuilder
from .dependencies import get_storage_dependency as get_storage

router = APIRouter(prefix="/search", tags=["search"])


@router.get("", response_model=SearchResult)
async def search_items(
    q: str = Query(..., description="Search query"),
    limit: int = Query(100, description="Maximum results to return"),
    storage: StorageBackend = Depends(get_storage)
):
    """Search for items by filename, tags, and notes."""
    try:
        if not q.strip():
            return SearchResult(items=[], total=0)
        
        # Load rollup manifest
        rollup_path = "_rollup.json"
        rollup_manifest = None
        
        if await storage.exists(rollup_path):
            try:
                rollup_data = await storage.read_text(rollup_path)
                rollup_manifest = RollupManifest.parse_raw(rollup_data)
            except Exception as e:
                print(f"Failed to load rollup manifest: {e}")
        
        # If no rollup exists, build one on-demand (for development)
        if rollup_manifest is None:
            print("No rollup manifest found, building on-demand...")
            builder = RollupBuilder(storage)
            rollup_manifest = await builder.build_and_save_rollup("")
        
        # Perform simple text search
        query_terms = q.lower().split()
        matching_items = []
        
        for item in rollup_manifest.items:
            # Create searchable text
            searchable_text = " ".join([
                item.name.lower(),
                " ".join(item.tags).lower(),
                item.notes.lower()
            ])
            
            # Check if all query terms are present
            if all(term in searchable_text for term in query_terms):
                matching_items.append(item)
        
        # Apply limit
        limited_items = matching_items[:limit]
        
        return SearchResult(
            items=limited_items,
            total=len(matching_items)
        )
        
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Search failed: {str(e)}")


@router.post("/rebuild-index")
async def rebuild_search_index(
    storage: StorageBackend = Depends(get_storage)
):
    """Rebuild the search rollup index."""
    try:
        builder = RollupBuilder(storage)
        manifest = await builder.build_and_save_rollup("")
        
        return {
            "message": "Search index rebuilt",
            "items_indexed": len(manifest.items),
            "generated_at": manifest.generatedAt.isoformat()
        }
        
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to rebuild index: {str(e)}")


@router.get("/suggest")
async def get_search_suggestions(
    q: str = Query("", description="Partial search query"),
    limit: int = Query(10, description="Maximum suggestions"),
    storage: StorageBackend = Depends(get_storage)
):
    """Get search suggestions based on existing tags and filenames."""
    try:
        # Load rollup manifest
        rollup_path = "_rollup.json"
        
        if not await storage.exists(rollup_path):
            return {"suggestions": []}
        
        rollup_data = await storage.read_text(rollup_path)
        rollup_manifest = RollupManifest.parse_raw(rollup_data)
        
        # Collect all unique tags and common filename parts
        suggestions = set()
        query_lower = q.lower()
        
        for item in rollup_manifest.items:
            # Add matching tags
            for tag in item.tags:
                if query_lower in tag.lower():
                    suggestions.add(tag)
            
            # Add matching filename parts (without extension)
            name_parts = item.name.lower().replace(".", " ").split()
            for part in name_parts:
                if len(part) > 2 and query_lower in part:
                    suggestions.add(part)
        
        # Sort and limit suggestions
        sorted_suggestions = sorted(suggestions)[:limit]
        
        return {"suggestions": sorted_suggestions}
        
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to get suggestions: {str(e)}")
