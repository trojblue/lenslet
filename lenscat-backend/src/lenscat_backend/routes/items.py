from __future__ import annotations
from fastapi import APIRouter, HTTPException, Request
from datetime import datetime, timezone
from ..models import Sidecar
from ..utils import jsonio

router = APIRouter()

@router.get("/item")
def get_item(path: str, request: Request):
    storage = request.state.storage
    if storage is None:
        raise HTTPException(500, "Storage not configured")
    sidecar_path = path + ".json"
    try:
        exists = storage.exists(sidecar_path)
    except ValueError:
        raise HTTPException(400, "invalid path")
    if not exists:
        # create a minimal read-only view
        sc = Sidecar(tags=[], notes="", exif=None, star=None, updated_at=datetime.now(timezone.utc).isoformat(), updated_by="server")
        return sc
    try:
        data = jsonio.loads(storage.read_bytes(sidecar_path))
    except ValueError:
        raise HTTPException(400, "invalid path")
    return Sidecar(**data)

@router.put("/item")
def put_item(path: str, body: Sidecar, request: Request):
    storage = request.state.storage
    if storage is None:
        raise HTTPException(500, "Storage not configured")
    sidecar_path = path + ".json"
    try:
        # Write atomically where possible: write temp then replace
        data = jsonio.dumps(body.model_dump())
        tmp = sidecar_path + ".tmp"
        try:
          storage.write_bytes(tmp, data)
          # best-effort: some backends may not support atomic rename; fallback
          storage.write_bytes(sidecar_path, data)
        except Exception:
          storage.write_bytes(sidecar_path, data)
    except ValueError:
        raise HTTPException(400, "invalid path")
    return body
