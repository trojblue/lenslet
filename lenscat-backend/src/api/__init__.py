"""API package."""
from fastapi import APIRouter

from . import folders, health, items, search, thumbnails

# Create main API router
api_router = APIRouter(prefix="/api")

# Include all route modules
api_router.include_router(folders.router)
api_router.include_router(items.router)
api_router.include_router(thumbnails.router)
api_router.include_router(search.router)
api_router.include_router(health.router)

__all__ = ["api_router"]
