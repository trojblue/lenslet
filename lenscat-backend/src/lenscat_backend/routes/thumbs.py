from __future__ import annotations
from fastapi import APIRouter, Response, HTTPException, Request
from ..utils.thumbs import make_thumbnail
from ..config import settings
from ..utils.exif import basic_meta
from ..utils import jsonio

router = APIRouter()

@router.get("/thumb")
def get_thumb(path: str, request: Request):
    storage = request.state.storage
    if storage is None:
        raise HTTPException(500, "Storage not configured")
    thumb_path = path + ".thumbnail"
    try:
        if storage.exists(thumb_path):
            return Response(content=storage.read_bytes(thumb_path), media_type="image/webp")
    except ValueError:
        raise HTTPException(400, "invalid path")
    # generate on demand
    try:
        if not storage.exists(path):
            raise HTTPException(404, "file not found")
        raw = storage.read_bytes(path)
    except ValueError:
        raise HTTPException(400, "invalid path")
    thumb = make_thumbnail(raw, settings.thumb_long_edge, settings.thumb_quality)
    try:
        storage.write_bytes(thumb_path, thumb)
    except ValueError:
        raise HTTPException(400, "invalid path")
    # optionally write dimensions to sidecar if missing
    try:
        sc_path = path + ".json"
        if storage.exists(sc_path):
            data = jsonio.loads(storage.read_bytes(sc_path))
            if not data.get('exif'):
                data['exif'] = basic_meta(raw)
                storage.write_bytes(sc_path, jsonio.dumps(data))
    except Exception:
        pass
    return Response(content=thumb, media_type="image/webp")
