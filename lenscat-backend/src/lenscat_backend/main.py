"""Main FastAPI application."""
import os
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles

from .api import api_router


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Application lifespan manager."""
    # Startup
    print("🚀 Lenscat backend starting up...")
    
    # TODO: Initialize background workers here if needed
    
    yield
    
    # Shutdown
    print("🛑 Lenscat backend shutting down...")


def create_app() -> FastAPI:
    """Create and configure FastAPI application."""
    app = FastAPI(
        title="Lenscat Backend",
        description="Minimal gallery backend with flat file storage",
        version="0.1.0",
        lifespan=lifespan
    )
    
    # CORS middleware for frontend
    app.add_middleware(
        CORSMiddleware,
        allow_origins=["*"],  # In production, specify actual origins
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )
    
    # Include API routes
    app.include_router(api_router)
    
    # Health check at root
    @app.get("/")
    async def root():
        return {"message": "Lenscat Backend", "version": "0.1.0"}
    
    # Serve static files for local storage (development)
    if os.getenv("STORAGE_TYPE", "local").lower() == "local":
        static_dir = os.getenv("LOCAL_ROOT", "./data")
        if os.path.exists(static_dir):
            app.mount("/api/files", StaticFiles(directory=static_dir), name="files")
    
    return app


# Create app instance
app = create_app()


if __name__ == "__main__":
    import uvicorn
    
    host = os.getenv("HOST", "0.0.0.0")
    port = int(os.getenv("PORT", "8000"))
    reload = os.getenv("RELOAD", "false").lower() == "true"
    
    uvicorn.run(
        "src.main:app",
        host=host,
        port=port,
        reload=reload,
        reload_dirs=["src"] if reload else None
    )
