from __future__ import annotations
from fastapi import APIRouter, Response, HTTPException, Request, UploadFile, File, Form
import os
from . import folders
from ..workers.indexer import build_index, ensure_thumb

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


@router.post("/file")
async def post_file(
    request: Request,
    dest: str = Form(...),
    file: UploadFile = File(...),
):
    storage = request.state.storage
    if storage is None:
        raise HTTPException(500, "Storage not configured")

    # sanitize filename and enforce supported formats
    name = os.path.basename(file.filename or "")
    if not name:
        raise HTTPException(400, "missing filename")
    lower = name.lower()
    if not (lower.endswith(".jpg") or lower.endswith(".jpeg") or lower.endswith(".png") or lower.endswith(".webp")):
        raise HTTPException(400, "unsupported file type")

    target_path = storage.join(dest, name)
    # write bytes
    blob = await file.read()
    if not blob:
        raise HTTPException(400, "empty upload")
    storage.write_bytes(target_path, blob)

    # Best-effort: generate thumbnail/sidecar and refresh index for the folder
    try:
        await ensure_thumb(storage, target_path)
    except Exception:
        pass
    try:
        await build_index(storage, dest)
    except Exception:
        pass

    return {"ok": True, "path": target_path}


@router.post("/move")
async def post_move(
    request: Request,
    src: str = Form(...),
    dest: str = Form(...),
):
    storage = request.state.storage
    if storage is None:
        raise HTTPException(500, "Storage not configured")
    if not storage.exists(src):
        raise HTTPException(404, "source not found")
    name = os.path.basename(src)
    target = storage.join(dest, name)
    # Read/write then remove original (works across Local/S3 APIs we expose)
    blob = storage.read_bytes(src)
    storage.write_bytes(target, blob)
    try:
        # Also move sidecar and thumbnail if present
        for suf in (".json", ".thumbnail"):
            sp = src + suf
            if storage.exists(sp):
                storage.write_bytes(target + suf, storage.read_bytes(sp))
    except Exception:
        pass
    # Best effort: delete originals (ignore on failure)
    try:
        _delete_path(storage, src)
        for suf in (".json", ".thumbnail"):
            _delete_path(storage, src + suf)
    except Exception:
        pass
    # Refresh indexes for both folders
    try:
        await build_index(storage, os.path.dirname(src))
    except Exception:
        pass
    try:
        await ensure_thumb(storage, target)
        await build_index(storage, dest)
    except Exception:
        pass
    return {"ok": True, "path": target}


def _delete_path(storage, path: str):
    # Local-only delete helper; for S3 use zero-byte overwrite pattern not supported here.
    try:
        from ..storage.local import LocalStorage
        if isinstance(storage, LocalStorage):
            ap = storage._abs(path)  # type: ignore[attr-defined]
            try:
                os.remove(ap)
            except FileNotFoundError:
                pass
    except Exception:
        pass
