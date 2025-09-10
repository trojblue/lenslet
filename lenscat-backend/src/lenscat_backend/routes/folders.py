from __future__ import annotations
from fastapi import APIRouter, HTTPException, Request
from datetime import datetime, timezone
from ..models import FolderIndex, Item, DirEntry
from ..utils import jsonio
from ..utils.exif import basic_meta

router = APIRouter()

INDEX_NAME = "_index.json"

# Simplified: build manifest on demand if missing
@router.get("/folders", response_model=FolderIndex)
def get_folder(path: str, request: Request):
    storage = request.state.storage
    if storage is None:
        raise HTTPException(500, "Storage not configured")

    index_path = storage.join(path, INDEX_NAME)
    if storage.exists(index_path):
        data = jsonio.loads(storage.read_bytes(index_path))
        return FolderIndex(**data)

    files, dirs = storage.list_dir(path)
    items: list[Item] = []
    for name in files:
        if not (name.lower().endswith(('.jpg','.jpeg','.png','.webp'))):
            continue
        full = storage.join(path, name)
        size = storage.size(full)
        # Try sidecar first for dimensions
        w = h = 0
        try:
            scp = full + '.json'
            if storage.exists(scp):
                data = jsonio.loads(storage.read_bytes(scp))
                exif = data.get('exif') or {}
                w = int(exif.get('width', 0) or 0)
                h = int(exif.get('height', 0) or 0)
            if (not w or not h) and storage.exists(full):
                # As a fallback for local storage, read once to get basic dimensions
                meta = basic_meta(storage.read_bytes(full))
                w = int(meta.get('width', 0) or 0)
                h = int(meta.get('height', 0) or 0)
        except Exception:
            w = h = 0
        thumb = storage.exists(full + ".thumbnail")
        meta = storage.exists(full + ".json")
        items.append(Item(path=full, name=name, type=_guess_mime(name), w=w, h=h, size=size, hasThumb=thumb, hasMeta=meta))

    dir_entries = [DirEntry(name=d, kind='branch') for d in dirs]
    idx = FolderIndex(path=path, generatedAt=datetime.now(timezone.utc).isoformat(), items=items, dirs=dir_entries)
    storage.write_bytes(index_path, jsonio.dumps(idx.model_dump()))
    return idx

def _guess_mime(name: str) -> str:
    n = name.lower()
    if n.endswith('.webp'): return 'image/webp'
    if n.endswith('.png'): return 'image/png'
    return 'image/jpeg'
