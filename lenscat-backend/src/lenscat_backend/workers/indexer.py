from __future__ import annotations
import os, asyncio
from datetime import datetime, timezone
from ..storage.local import LocalStorage
from ..storage.s3 import S3Storage
from ..utils import jsonio
from ..utils.thumbs import make_thumbnail
from ..utils.exif import basic_meta

IMAGE_EXTS = (".jpg",".jpeg",".png",".webp")

async def build_index(storage, path: str):
    files, dirs = storage.list_dir(path)
    items = []
    for name in files:
        if not name.lower().endswith(IMAGE_EXTS):
            continue
        full = storage.join(path, name)
        size = storage.size(full)
        hasThumb = storage.exists(full + ".thumbnail")
        hasMeta = storage.exists(full + ".json")
        items.append({"path": full, "name": name, "type": _guess(full), "w": 0, "h": 0, "size": size, "hasThumb": hasThumb, "hasMeta": hasMeta})
    idx = {"v":1, "path": path, "generatedAt": datetime.now(timezone.utc).isoformat(), "items": items, "dirs": [{"name": d, "kind": "branch"} for d in dirs]}
    storage.write_bytes(storage.join(path, "_index.json"), jsonio.dumps(idx))

async def ensure_thumb(storage, full: str):
    tpath = full + ".thumbnail"
    if storage.exists(tpath):
        return
    raw = storage.read_bytes(full)
    th = make_thumbnail(raw)
    storage.write_bytes(tpath, th)
    scp = full + ".json"
    if not storage.exists(scp):
        # write minimal sidecar
        meta = basic_meta(raw)
        sc = {"v":1, "tags":[], "notes":"", "exif":meta, "updated_at": datetime.now(timezone.utc).isoformat(), "updated_by":"worker"}
        storage.write_bytes(scp, jsonio.dumps(sc))

async def walk_and_index(storage, root: str):
    stack = [root]
    while stack:
        path = stack.pop()
        await build_index(storage, path)
        _files, dirs = storage.list_dir(path)
        for d in dirs:
            stack.append(storage.join(path, d))

async def build_rollup(storage, root: str):
    # naive: collect from indexes/sidecars
    items = []
    stack = [root]
    while stack:
        path = stack.pop()
        idxp = storage.join(path, "_index.json")
        if not storage.exists(idxp):
            await build_index(storage, path)
        idx = jsonio.loads(storage.read_bytes(idxp))
        for it in idx.get('items', []):
            scp = it['path'] + ".json"
            name = it.get('name','')
            if storage.exists(scp):
                sc = jsonio.loads(storage.read_bytes(scp))
                items.append({"path": it['path'], "name": name, "tags": sc.get('tags',[]), "notes": sc.get('notes',''), "type": it.get('type','image/jpeg'), "w": it.get('w',0), "h": it.get('h',0), "size": it.get('size',0), "hasThumb": it.get('hasThumb', False)})
        for d in idx.get('dirs', []):
            stack.append(storage.join(path, d['name']))
    roll = {"v":1, "generatedAt": datetime.now(timezone.utc).isoformat(), "items": items}
    storage.write_bytes("_rollup.json", jsonio.dumps(roll))

def _guess(p: str) -> str:
    p = p.lower()
    if p.endswith('.webp'): return 'image/webp'
    if p.endswith('.png'): return 'image/png'
    return 'image/jpeg'
