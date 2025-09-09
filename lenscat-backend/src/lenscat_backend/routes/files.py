from __future__ import annotations
from fastapi import APIRouter, Response, HTTPException, Request

router = APIRouter()

def _guess_mime(name: str) -> str:
    n = name.lower()
    if n.endswith('.webp'): return 'image/webp'
    if n.endswith('.png'): return 'image/png'
    return 'image/jpeg'

@router.get("/file")
def get_file(path: str, request: Request):
    storage = request.state.storage
    if storage is None:
        raise HTTPException(500, "Storage not configured")
    if not storage.exists(path):
        raise HTTPException(404, "file not found")
    data = storage.read_bytes(path)
    return Response(content=data, media_type=_guess_mime(path))


