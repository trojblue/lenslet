from __future__ import annotations
from fastapi import APIRouter, Response, HTTPException, Request, UploadFile, File, Form
import os
from . import folders
from ..workers.indexer import build_index, ensure_thumb
from pydantic import BaseModel
from ..storage.s3 import S3Storage
from ..utils import jsonio

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
    # Restrict served files to expected image types and safe paths
    lower = (path or "").lower()
    if not (lower.endswith(".jpg") or lower.endswith(".jpeg") or lower.endswith(".png") or lower.endswith(".webp")):
        raise HTTPException(400, "unsupported file type")
    try:
        if not storage.exists(path):
            raise HTTPException(404, "file not found")
        data = storage.read_bytes(path)
    except ValueError:
        # Raised by LocalStorage when the path escapes root
        raise HTTPException(400, "invalid path")
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
    try:
        storage.write_bytes(target_path, blob)
    except ValueError:
        raise HTTPException(400, "invalid path")

    # Best-effort: generate thumbnail/sidecar and refresh index for the folder
    try:
        await ensure_thumb(storage, target_path)
    except Exception:
        pass
    try:
        await build_index(storage, dest)
    except Exception:
        pass
    try:
        # Also refresh parent directory to reflect newly created folders
        parent = os.path.dirname(dest) or "/"
        await build_index(storage, parent)
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
    try:
        if not storage.exists(src):
            raise HTTPException(404, "source not found")
    except ValueError:
        raise HTTPException(400, "invalid path")
    name = os.path.basename(src)
    target = storage.join(dest, name)
    # Read/write then remove original (works across Local/S3 APIs we expose)
    try:
        blob = storage.read_bytes(src)
        storage.write_bytes(target, blob)
    except ValueError:
        raise HTTPException(400, "invalid path")
    try:
        # Also move sidecar and thumbnail if present
        for suf in (".json", ".thumbnail"):
            sp = src + suf
            if storage.exists(sp):
                if suf == ".json" and dest.strip("/").split("/")[-1] == "_trash_":
                    try:
                        data = jsonio.loads(storage.read_bytes(sp))
                        if not data.get("original_position"):
                            data["original_position"] = src
                        storage.write_bytes(target + suf, jsonio.dumps(data))
                    except Exception:
                        storage.write_bytes(target + suf, storage.read_bytes(sp))
                else:
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
    try:
        # Also refresh parent dir (e.g., root) to include any newly created folder names
        parent = os.path.dirname(dest) or "/"
        await build_index(storage, parent)
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


@router.post("/export-intent")
async def export_intent(request: Request, path: str = Form(...)):
    # Best-effort: simply acknowledge on server (placeholder for future export pipeline)
    try:
        print(f"export-intent: {path}")
    except Exception:
        pass
    return {"ok": True}


class DeleteBody(BaseModel):
    paths: list[str]


@router.post("/delete")
async def delete_files(request: Request, body: DeleteBody):
    storage = request.state.storage
    if storage is None:
        raise HTTPException(500, "Storage not configured")
    src_dirs: set[str] = set()
    for p in body.paths:
        if not p:
            continue
        src_dirs.add(os.path.dirname(p) or "/")
        # Delete main file and companions
        _delete_any(storage, p)
        for suf in (".json", ".thumbnail"):
            _delete_any(storage, p + suf)
    # Refresh indexes for affected folders
    for d in src_dirs:
        try:
            await build_index(storage, d)
        except Exception:
            pass
    return {"ok": True}


def _delete_any(storage, path: str):
    try:
        # Local
        from ..storage.local import LocalStorage
        if isinstance(storage, LocalStorage):
            ap = storage._abs(path)  # type: ignore[attr-defined]
            try:
                os.remove(ap)
            except FileNotFoundError:
                pass
            return
    except Exception:
        pass
    try:
        # S3
        if isinstance(storage, S3Storage):
            key = storage._key(path)  # type: ignore[attr-defined]
            try:
                storage.s3.delete_object(Bucket=storage.bucket, Key=key)
            except Exception:
                pass
            return
    except Exception:
        pass
