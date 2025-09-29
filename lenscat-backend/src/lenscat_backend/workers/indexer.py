from __future__ import annotations
import os, asyncio, time
from datetime import datetime, timezone
from ..storage.local import LocalStorage
from ..storage.s3 import S3Storage
from ..utils import jsonio
from ..utils.thumbs import make_thumbnail
from ..config import settings
from ..utils.exif import basic_meta

IMAGE_EXTS = (".jpg",".jpeg",".png",".webp")

async def build_index(storage, path: str):
    files, dirs = storage.list_dir(path)
    image_files = [name for name in files if name.lower().endswith(IMAGE_EXTS)]

    items: list[dict] = []

    # Bounded concurrency for per-file work
    sem = asyncio.Semaphore(max(1, int(settings.index_concurrency)))

    async def process_one(name: str):
        async with sem:
            full = storage.join(path, name)
            try:
                size = storage.size(full)
            except Exception:
                return
            hasThumb = storage.exists(full + ".thumbnail")
            hasMeta = storage.exists(full + ".json")
            w = h = 0
            try:
                if hasMeta:
                    data = jsonio.loads(storage.read_bytes(full + ".json"))
                    exif = data.get("exif") or {}
                    w = int(exif.get("width", 0) or 0)
                    h = int(exif.get("height", 0) or 0)
                if not w or not h:
                    meta = basic_meta(storage.read_bytes(full))
                    w = int(meta.get("width", 0) or 0)
                    h = int(meta.get("height", 0) or 0)
            except Exception:
                w = h = 0

            # Ensure thumb/sidecar exist
            if not hasThumb or not hasMeta:
                try:
                    await ensure_thumb(storage, full)
                    hasThumb = storage.exists(full + ".thumbnail")
                    hasMeta = storage.exists(full + ".json")
                except Exception:
                    pass

            items.append({"path": full, "name": name, "type": _guess(full), "w": w, "h": h, "size": size, "hasThumb": hasThumb, "hasMeta": hasMeta})

    # Progress reporter
    total = len(image_files)
    done = 0
    last_report = time.monotonic()

    async def runner():
        nonlocal done, last_report
        for name in image_files:
            await process_one(name)
            done += 1
            now = time.monotonic()
            if now - last_report >= settings.progress_interval_s:
                print(f"[index] {path or '/'} {done}/{total} ({int(done*100/max(1,total))}%)")
                last_report = now

    await runner()

    idx = {"v":1, "path": path, "generatedAt": datetime.now(timezone.utc).isoformat(), "items": items, "dirs": [{"name": d, "kind": "branch"} for d in dirs]}
    storage.write_bytes(storage.join(path, "_index.json"), jsonio.dumps(idx))
    # Also ensure parent index reflects this folder's presence when called
    try:
        parent = storage.join(path, "..") if path else ""
    except Exception:
        parent = ""

async def ensure_thumb(storage, full: str):
    tpath = full + ".thumbnail"
    if storage.exists(tpath):
        return
    # Offload PIL work to thread so we can run many in parallel
    loop = asyncio.get_running_loop()
    raw = await loop.run_in_executor(None, storage.read_bytes, full)
    th = await loop.run_in_executor(None, make_thumbnail, raw, settings.thumb_long_edge, settings.thumb_quality)
    await loop.run_in_executor(None, storage.write_bytes, tpath, th)
    scp = full + ".json"
    # write or update sidecar with basic EXIF
    try:
        meta = await loop.run_in_executor(None, basic_meta, raw)
        if storage.exists(scp):
            data = jsonio.loads(storage.read_bytes(scp))
            if not data.get("exif"):
                data["exif"] = meta
            await loop.run_in_executor(None, storage.write_bytes, scp, jsonio.dumps(data))
        else:
            sc = {"v":1, "tags":[], "notes":"", "exif":meta, "star": None, "updated_at": datetime.now(timezone.utc).isoformat(), "updated_by":"worker"}
            await loop.run_in_executor(None, storage.write_bytes, scp, jsonio.dumps(sc))
    except Exception:
        pass

async def walk_and_index(storage, root: str):
    stack = [root]
    while stack:
        path = stack.pop()
        files, dirs = storage.list_dir(path)
        # Recurse first to improve parallel spread
        for d in dirs:
            stack.append(storage.join(path, d))
        await build_index(storage, path)

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
