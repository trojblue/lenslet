"""Health check API endpoints."""
from fastapi import APIRouter, Depends
from datetime import datetime

from ..models.types import HealthStatus
from ..storage.base import StorageBackend
from ..workers.thumbnailer import ThumbnailWorker
from .dependencies import get_storage_dependency as get_storage

router = APIRouter(prefix="/health", tags=["health"])


@router.get("", response_model=HealthStatus)
async def health_check(
    storage: StorageBackend = Depends(get_storage)
):
    """Get overall system health status."""
    try:
        # Check storage backend health
        storage_health = await storage.health_check()
        
        # Get thumbnail statistics
        thumb_worker = ThumbnailWorker(storage)
        thumb_stats = await thumb_worker.get_thumbnail_stats("")
        
        # Check for key system files
        has_rollup = await storage.exists("_rollup.json")
        has_root_index = await storage.exists("_index.json")
        
        return HealthStatus(
            status="healthy",
            backend={
                "timestamp": datetime.utcnow().isoformat(),
                "version": "0.1.0",
                "uptime_seconds": 0,  # TODO: Track actual uptime
            },
            workers={
                "thumbnail_stats": thumb_stats,
                "indexer_status": "operational",
            },
            storage={
                **storage_health,
                "has_rollup_manifest": has_rollup,
                "has_root_index": has_root_index,
            }
        )
        
    except Exception as e:
        return HealthStatus(
            status="unhealthy",
            backend={
                "timestamp": datetime.utcnow().isoformat(),
                "error": str(e),
            }
        )


@router.get("/storage")
async def storage_health(
    storage: StorageBackend = Depends(get_storage)
):
    """Get detailed storage backend health."""
    return await storage.health_check()


@router.get("/workers")
async def worker_health(
    storage: StorageBackend = Depends(get_storage)
):
    """Get worker system health and statistics."""
    try:
        thumb_worker = ThumbnailWorker(storage)
        
        # Get stats for root directory
        root_stats = await thumb_worker.get_thumbnail_stats("")
        
        return {
            "thumbnail_worker": {
                "status": "operational",
                "stats": root_stats,
            },
            "indexer": {
                "status": "operational",
                "last_run": None,  # TODO: Track last run times
            }
        }
        
    except Exception as e:
        return {
            "error": str(e),
            "status": "unhealthy"
        }
