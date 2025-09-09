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
    if not storage.exists(sidecar_path):
        # create a minimal read-only view
        sc = Sidecar(tags=[], notes="", exif=None, updated_at=datetime.now(timezone.utc).isoformat(), updated_by="server")
        return sc
    data = jsonio.loads(storage.read_bytes(sidecar_path))
    return Sidecar(**data)

@router.put("/item")
def put_item(path: str, body: Sidecar, request: Request):
    storage = request.state.storage
    if storage is None:
        raise HTTPException(500, "Storage not configured")
    sidecar_path = path + ".json"
    storage.write_bytes(sidecar_path, jsonio.dumps(body.model_dump()))
    return body
