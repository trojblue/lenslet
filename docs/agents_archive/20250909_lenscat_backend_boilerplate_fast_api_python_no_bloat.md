Below is a tiny backend you can drop into `backend/`. It matches the PRD, stays flat-file, and leaves room for workers—without spawning a microservices zoo.

---

# Repository Layout
```
backend/
├─ pyproject.toml
├─ README.md
├─ .env.example
├─ Makefile
├─ app/
│  ├─ __init__.py
│  ├─ main.py
│  ├─ config.py
│  ├─ models.py
│  ├─ utils/
│  │  ├─ jsonio.py
│  │  ├─ hashing.py
│  │  ├─ thumbs.py
│  │  └─ exif.py
│  ├─ storage/
│  │  ├─ base.py
│  │  ├─ local.py
│  │  └─ s3.py
│  └─ routes/
│     ├─ folders.py
│     ├─ items.py
│     ├─ thumbs.py
│     └─ search.py
└─ workers/
   ├─ __init__.py
   ├─ indexer.py
   └─ run_worker.py
```

---

## pyproject.toml (minimal deps)
```toml
[project]
name = "lenslet-backend"
version = "0.1.0"
description = "lenslet flat-file backend (FastAPI)"
readme = "README.md"
requires-python = ">=3.10"
authors = [{ name = "you" }]
dependencies = [
  "fastapi>=0.115",
  "uvicorn[standard]>=0.30",
  "orjson>=3.10",
  "aioboto3>=13.0",
  "boto3>=1.34",
  "python-dotenv>=1.0",
  "blake3>=0.4",
  "pillow>=10.4",
]

[tool.uvicorn]
host = "127.0.0.1"
port = 7070
reload = true

[build-system]
requires = ["hatchling"]
build-backend = "hatchling.build"
```

> Note: `pyvips` is optional. Pillow is fine to start; swap in pyvips later if you need speed.

---

## .env.example
```env
# Root path (local) OR S3 bucket/prefix. You can support both; define multiple roots via config file if needed.
ROOT_PATH=./data

# S3 config (only required if you use s3 storage)
S3_BUCKET=your-bucket
S3_PREFIX=art/
AWS_REGION=us-east-1
AWS_ACCESS_KEY_ID=
AWS_SECRET_ACCESS_KEY=
S3_ENDPOINT= # optional, e.g., http://localhost:9000 for MinIO

# Misc
API_BASE=http://127.0.0.1:7070
THUMB_LONG_EDGE=256
THUMB_QUALITY=70
```

---

## Makefile
```make
.PHONY: dev worker fmt

dev:
	uvicorn app.main:app --reload --host 127.0.0.1 --port 7070

worker:
	python -m workers.run_worker

fmt:
	ruff check --fix || true
	black app workers || true
```

---

## app/__init__.py
```py
# empty on purpose
```

## app/config.py
```py
from __future__ import annotations
import os
from dataclasses import dataclass

@dataclass(frozen=True)
class Settings:
    root_path: str = os.getenv("ROOT_PATH", "./data")
    s3_bucket: str | None = os.getenv("S3_BUCKET")
    s3_prefix: str = os.getenv("S3_PREFIX", "")
    aws_region: str | None = os.getenv("AWS_REGION")
    s3_endpoint: str | None = os.getenv("S3_ENDPOINT")
    thumb_long_edge: int = int(os.getenv("THUMB_LONG_EDGE", "256"))
    thumb_quality: int = int(os.getenv("THUMB_QUALITY", "70"))

settings = Settings()
```

## app/models.py
```py
from __future__ import annotations
from pydantic import BaseModel, Field
from typing import Literal

Mime = Literal['image/webp','image/jpeg','image/png']

class Item(BaseModel):
    path: str
    name: str
    type: Mime
    w: int
    h: int
    size: int
    hasThumb: bool = False
    hasMeta: bool = False
    hash: str | None = None

class DirEntry(BaseModel):
    name: str
    kind: Literal['branch','leaf-real','leaf-pointer']

class FolderIndex(BaseModel):
    v: int = 1
    path: str
    generatedAt: str
    items: list[Item] = Field(default_factory=list)
    dirs: list[DirEntry] = Field(default_factory=list)
    page: int | None = None
    pageCount: int | None = None

class Sidecar(BaseModel):
    v: int = 1
    tags: list[str] = Field(default_factory=list)
    notes: str = ""
    exif: dict | None = None
    hash: str | None = None
    updatedAt: str
    updatedBy: str

class SearchResult(BaseModel):
    items: list[Item]
```

## app/utils/jsonio.py
```py
from __future__ import annotations
import orjson
from typing import Any

OPT = orjson.OPT_INDENT_2 | orjson.OPT_SORT_KEYS

def dumps(obj: Any) -> bytes:
    return orjson.dumps(obj, option=OPT)

def loads(b: bytes | bytearray | memoryview):
    return orjson.loads(b)
```

## app/utils/hashing.py
```py
from __future__ import annotations
from blake3 import blake3

def blake3_hex(data: bytes) -> str:
    return blake3(data).hexdigest()
```

## app/utils/exif.py
```py
from __future__ import annotations
from PIL import Image
from io import BytesIO

# Minimal EXIF/dimensions; extend later.

def basic_meta(img_bytes: bytes) -> dict:
    with Image.open(BytesIO(img_bytes)) as im:
        w, h = im.size
        return {"width": w, "height": h}
```

## app/utils/thumbs.py
```py
from __future__ import annotations
from PIL import Image
from io import BytesIO

# Generate a WebP thumbnail with long edge limit and quality.

def make_thumbnail(img_bytes: bytes, long_edge: int = 256, quality: int = 70) -> bytes:
    with Image.open(BytesIO(img_bytes)) as im:
        w, h = im.size
        if w >= h:
            new_w = long_edge
            new_h = int(h * (long_edge / w))
        else:
            new_h = long_edge
            new_w = int(w * (long_edge / h))
        im = im.convert("RGB").resize((max(1,new_w), max(1,new_h)), Image.LANCZOS)
        out = BytesIO()
        im.save(out, format="WEBP", quality=quality, method=6)
        return out.getvalue()
```

---

## app/storage/base.py
```py
from __future__ import annotations
from typing import Protocol, Iterable

class Storage(Protocol):
    def list_dir(self, path: str) -> tuple[list[str], list[str]]:
        """Return (files, dirs) names in path (no recursion)."""
    def read_bytes(self, path: str) -> bytes:
        ...
    def write_bytes(self, path: str, data: bytes) -> None:
        ...
    def exists(self, path: str) -> bool:
        ...
    def size(self, path: str) -> int:
        ...
    def join(self, *parts: str) -> str:
        ...
    def etag(self, path: str) -> str | None:
        ...
```

## app/storage/local.py
```py
from __future__ import annotations
import os
from .base import Storage

class LocalStorage(Storage):
    def __init__(self, root: str):
        self.root = os.path.abspath(root)

    def _abs(self, path: str) -> str:
        return os.path.abspath(os.path.join(self.root, path.lstrip("/")))

    def list_dir(self, path: str):
        p = self._abs(path)
        files, dirs = [], []
        for name in os.listdir(p):
            full = os.path.join(p, name)
            if os.path.isdir(full):
                dirs.append(name)
            else:
                files.append(name)
        return files, dirs

    def read_bytes(self, path: str) -> bytes:
        with open(self._abs(path), 'rb') as f:
            return f.read()

    def write_bytes(self, path: str, data: bytes) -> None:
        full = self._abs(path)
        os.makedirs(os.path.dirname(full), exist_ok=True)
        with open(full, 'wb') as f:
            f.write(data)

    def exists(self, path: str) -> bool:
        return os.path.exists(self._abs(path))

    def size(self, path: str) -> int:
        return os.path.getsize(self._abs(path))

    def join(self, *parts: str) -> str:
        return "/".join([p.strip("/") for p in parts if p])

    def etag(self, path: str) -> str | None:
        try:
            st = os.stat(self._abs(path))
            return f"{st.st_mtime_ns}-{st.st_size}"
        except FileNotFoundError:
            return None
```

## app/storage/s3.py
```py
from __future__ import annotations
import os
import boto3
from botocore.client import Config
from .base import Storage

class S3Storage(Storage):
    def __init__(self, bucket: str, prefix: str = "", region: str | None = None, endpoint: str | None = None):
        self.bucket = bucket
        self.prefix = prefix.strip('/')
        session = boto3.session.Session(region_name=region)
        self.s3 = session.client('s3', endpoint_url=endpoint, config=Config(s3={'addressing_style':'virtual'}))

    def _key(self, path: str) -> str:
        path = path.lstrip('/')
        return f"{self.prefix}/{path}".strip('/') if self.prefix else path

    def list_dir(self, path: str):
        key = self._key(path)
        if key and not key.endswith('/'):
            key += '/'
        paginator = self.s3.get_paginator('list_objects_v2')
        files, dirs = [], []
        for page in paginator.paginate(Bucket=self.bucket, Prefix=key, Delimiter='/'):
            for c in page.get('CommonPrefixes', []):
                name = c['Prefix'][len(key):].strip('/')
                if name:
                    dirs.append(name)
            for obj in page.get('Contents', []):
                name = obj['Key'][len(key):]
                if name and '/' not in name:
                    files.append(name)
        return files, dirs

    def read_bytes(self, path: str) -> bytes:
        key = self._key(path)
        r = self.s3.get_object(Bucket=self.bucket, Key=key)
        return r['Body'].read()

    def write_bytes(self, path: str, data: bytes) -> None:
        key = self._key(path)
        self.s3.put_object(Bucket=self.bucket, Key=key, Body=data)

    def exists(self, path: str) -> bool:
        key = self._key(path)
        try:
            self.s3.head_object(Bucket=self.bucket, Key=key)
            return True
        except self.s3.exceptions.NoSuchKey:
            return False
        except Exception:
            return False

    def size(self, path: str) -> int:
        key = self._key(path)
        r = self.s3.head_object(Bucket=self.bucket, Key=key)
        return r['ContentLength']

    def join(self, *parts: str) -> str:
        return "/".join([p.strip("/") for p in parts if p])

    def etag(self, path: str) -> str | None:
        key = self._key(path)
        try:
            r = self.s3.head_object(Bucket=self.bucket, Key=key)
            return r.get('ETag', '').strip('"')
        except Exception:
            return None
```

---

## app/routes/folders.py
```py
from __future__ import annotations
from fastapi import APIRouter, HTTPException
from datetime import datetime, timezone
from ..models import FolderIndex, Item, DirEntry
from ..utils import jsonio
from ..utils.exif import basic_meta
from ..storage.base import Storage

router = APIRouter()

INDEX_NAME = "_index.json"

# Simplified: build manifest on demand if missing
@router.get("/folders", response_model=FolderIndex)
def get_folder(path: str, storage: Storage | None = None):  # storage is injected in main
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
        # best effort minimal meta (no full read if avoidable)
        # For local, we could open file. For S3, skip heavy read; dimensions can be absent until sidecar exists.
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
```

## app/routes/items.py
```py
from __future__ import annotations
from fastapi import APIRouter, HTTPException
from datetime import datetime, timezone
from ..models import Sidecar
from ..utils import jsonio
from ..storage.base import Storage

router = APIRouter()

@router.get("/item")
def get_item(path: str, storage: Storage | None = None):
    if storage is None:
        raise HTTPException(500, "Storage not configured")
    sidecar_path = path + ".json"
    if not storage.exists(sidecar_path):
        # create a minimal read-only view
        sc = Sidecar(tags=[], notes="", exif=None, updatedAt=datetime.now(timezone.utc).isoformat(), updatedBy="server")
        return sc
    data = jsonio.loads(storage.read_bytes(sidecar_path))
    return Sidecar(**data)

@router.put("/item")
def put_item(path: str, body: Sidecar, storage: Storage | None = None):
    if storage is None:
        raise HTTPException(500, "Storage not configured")
    sidecar_path = path + ".json"
    storage.write_bytes(sidecar_path, jsonio.dumps(body.model_dump()))
    return body
```

## app/routes/thumbs.py
```py
from __future__ import annotations
from fastapi import APIRouter, Response, HTTPException
from ..storage.base import Storage
from ..utils.thumbs import make_thumbnail
from ..utils.exif import basic_meta
from ..utils import jsonio

router = APIRouter()

@router.get("/thumb")
def get_thumb(path: str, storage: Storage | None = None):
    if storage is None:
        raise HTTPException(500, "Storage not configured")
    thumb_path = path + ".thumbnail"
    if storage.exists(thumb_path):
        return Response(content=storage.read_bytes(thumb_path), media_type="image/webp")
    # generate on demand
    if not storage.exists(path):
        raise HTTPException(404, "file not found")
    raw = storage.read_bytes(path)
    thumb = make_thumbnail(raw)
    storage.write_bytes(thumb_path, thumb)
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
```

## app/routes/search.py
```py
from __future__ import annotations
from fastapi import APIRouter, HTTPException
from ..models import SearchResult, Item
from ..storage.base import Storage
from ..utils import jsonio

router = APIRouter()

@router.get("/search", response_model=SearchResult)
def search(q: str = "", limit: int = 100, storage: Storage | None = None):
    if storage is None:
        raise HTTPException(500, "Storage not configured")
    rollup_path = "_rollup.json"
    if not storage.exists(rollup_path):
        return SearchResult(items=[])
    data = jsonio.loads(storage.read_bytes(rollup_path))
    items = []
    ql = q.lower()
    for it in data.get('items', []):
        hay = (it.get('name','') + ' ' + ' '.join(it.get('tags',[])) + ' ' + it.get('notes','')).lower()
        if ql in hay:
            items.append(Item(**{
                'path': it['path'], 'name': it.get('name',''), 'type': it.get('type','image/jpeg'),
                'w': it.get('w',0), 'h': it.get('h',0), 'size': it.get('size',0),
                'hasThumb': it.get('hasThumb', False), 'hasMeta': True, 'hash': it.get('hash')
            }))
            if len(items) >= limit: break
    return SearchResult(items=items)
```

## app/main.py
```py
from __future__ import annotations
import os
from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from .config import settings
from .storage.local import LocalStorage
from .storage.s3 import S3Storage
from .routes import folders, items, thumbs, search

app = FastAPI(title="lenslet Backend")

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

# Dependency shim
from fastapi import Depends
from typing import Annotated
from .storage.base import Storage

def get_storage(request: Request) -> Storage:
    return request.state.storage

# route include with dependency override
router_kwargs = {"dependencies": [Depends(get_storage)]}
app.include_router(folders.router, **router_kwargs)
app.include_router(items.router, **router_kwargs)
app.include_router(thumbs.router, **router_kwargs)
app.include_router(search.router, **router_kwargs)

@app.get("/health")
def health():
    return {"ok": True}
```

---

## workers/indexer.py (skeleton)
```py
from __future__ import annotations
import os, asyncio
from datetime import datetime, timezone
from app.storage.local import LocalStorage
from app.storage.s3 import S3Storage
from app.utils import jsonio
from app.utils.thumbs import make_thumbnail
from app.utils.exif import basic_meta

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
        sc = {"v":1, "tags":[], "notes":"", "exif":meta, "updatedAt": datetime.now(timezone.utc).isoformat(), "updatedBy":"worker"}
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
```

## workers/run_worker.py
```py
from __future__ import annotations
import os, asyncio
from app.config import settings
from app.storage.local import LocalStorage
from app.storage.s3 import S3Storage
from .indexer import walk_and_index, build_rollup

async def main():
    if settings.s3_bucket:
        storage = S3Storage(settings.s3_bucket, settings.s3_prefix, settings.aws_region, settings.s3_endpoint)
    else:
        storage = LocalStorage(settings.root_path)
    root = "/"  # logical root inside storage
    await walk_and_index(storage, root)
    await build_rollup(storage, root)

if __name__ == '__main__':
    asyncio.run(main())
```

---

## README.md (how to run)
```md
# lenslet Backend (Boilerplate)
Flat-file FastAPI backend for lenslet-lite. No database. JSON + thumbnails next to originals.

## Quickstart
```bash
cd backend
python -m venv .venv && source .venv/bin/activate
pip install -e .
cp .env.example .env  # adjust ROOT_PATH or S3 vars
make dev   # starts FastAPI at http://127.0.0.1:7070
```

## Endpoints
- `GET /folders?path=/subdir` → `_index.json` (builds if missing)
- `GET /item?path=/subdir/foo.webp` → sidecar (creates minimal on the fly)
- `PUT /item?path=/subdir/foo.webp` → update sidecar
- `GET /thumb?path=/subdir/foo.webp` → returns/generates `foo.webp.thumbnail`
- `GET /search?q=term` → quick search via `_rollup.json`
- `GET /health` → health check

## Worker
```bash
make worker  # walks tree, builds indexes & rollup
```

## Notes
- Keep logic tiny. If you need a helper, write a 10–30 line function, not a framework.
- Sidecars and thumbnails are the source of truth. Browser caches are disposable.
- Swap `LocalStorage` for `S3Storage` by setting env vars—no code changes.
```

---

This is intentionally small. Fill in behavior where marked, and don’t “optimize” by adding four new layers of abstraction. If you need me to wire up MinIO docker-compose for local S3, say the word, captain.