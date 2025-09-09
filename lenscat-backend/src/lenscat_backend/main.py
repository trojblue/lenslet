from __future__ import annotations
import os
from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from .config import settings
from .storage.local import LocalStorage
from .storage.s3 import S3Storage
from .routes import folders, items, thumbs, search, files

app = FastAPI(title="Lenscat Backend")

# CORS for local dev
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)

# Choose storage
STORAGE = None
if settings.s3_bucket:
    STORAGE = S3Storage(bucket=settings.s3_bucket, prefix=settings.s3_prefix, region=settings.aws_region, endpoint=settings.s3_endpoint)
else:
    STORAGE = LocalStorage(root=settings.root_path)

# simple dependency injection via state
@app.middleware("http")
async def attach_storage(request: Request, call_next):
    request.state.storage = STORAGE
    response = await call_next(request)
    return response

# route include
app.include_router(folders.router)
app.include_router(items.router)
app.include_router(thumbs.router)
app.include_router(search.router)
app.include_router(files.router)

@app.get("/health")
def health():
    return {"ok": True}
