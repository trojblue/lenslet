

# PRD — Backend (Python, FastAPI + Workers)

**Codename:** lenslet-backend
 **Owner:** You
 **Version:** v0.1 (MVP)
 **Date:** [Insert date]

------

## 1. Problem Statement

We need a backend to serve and update folder manifests, sidecar metadata, and thumbnails for a file-based gallery. Backend must be lightweight, flat (no SQL DB), async, and good at handling images/JSON on local filesystem or S3. Heavy jobs (indexing, thumbnailing) are handled by workers.

------

## 2. Goals

- Serve folder listings (`_index.json`) and image sidecars from local/S3.
- Handle metadata updates (tags/notes) by writing sidecar JSON next to images.
- Provide access to thumbnails (`.thumbnail` files), generate missing thumbs on demand.
- Provide search results from rollup manifest (`_rollup.json`).
- Offload heavy work (indexing, EXIF, thumbnails) to async workers.
- Use flat files (JSON, WebP) as single source of truth.
- Keep minimal local state; be stateless wherever possible.

------

## 3. Non-Goals

- Full-featured database (Postgres, etc.).
- Rich format support beyond JPEG/PNG/WebP.
- Real-time collaboration/conflict resolution (last-writer-wins only).
- Rating/stars, AI recall, advanced metadata.

------

## 4. API Requirements

### 4.1 Endpoints

1. **Folders**
   - `GET /folders?path=...` → returns `_index.json` for folder.
   - If missing, build index (list items/dirs, basic metadata).
2. **Items**
   - `GET /item?path=...` → returns sidecar JSON merged with basic EXIF.
   - `PUT /item?path=...` → updates/creates sidecar JSON (tags, notes, updatedAt, updatedBy).
3. **Thumbnails**
   - `GET /thumb?path=...` → returns `<file>.thumbnail` (binary WebP).
   - If missing, trigger worker to generate, return 202 + polling URL.
4. **Search**
   - `GET /search?q=...&limit=...` → returns matches from `_rollup.json` (filename, tags, notes).
   - Rollup built by worker.
5. **Health**
   - `GET /health` → returns backend + worker health, storage backend status.

### 4.2 Auth

- S3: use IAM role or presigned URLs.
- Local: no auth (dev mode only).
- MVP: token-based auth optional.

------

## 5. Data Contracts

### 5.1 Sidecar (`foo.webp.json`)

```json
{
  "v": 1,
  "tags": ["portrait", "pink-hair"],
  "notes": "Final pick for cover.",
  "exif": { "width": 1200, "height": 900, "createdAt": "2025-02-15T12:32:00Z" },
  "hash": "blake3:abc123...",
  "updatedAt": "2025-02-16T23:12:55Z",
  "updatedBy": "user@device"
}
```

### 5.2 Thumbnail (`foo.webp.thumbnail`)

- WebP, ≤ 256px long edge, q≈70.
- Generated via pyvips.

### 5.3 Folder Manifest (`_index.json`)

```json
{
  "v": 1,
  "path": "art/2025/",
  "generatedAt": "2025-02-16T23:10:00Z",
  "items": [
    { "name": "foo.webp", "w": 1200, "h": 900, "size": 96255, "hasThumb": true, "hasMeta": true, "hash": "blake3:..." }
  ],
  "dirs": [
    { "name": "A", "kind": "branch" },
    { "name": "B", "kind": "leaf-real" }
  ]
}
```

### 5.4 Rollup Manifest (`_rollup.json`)

- Top-level JSON with flattened items for search:

```json
{
  "v": 1,
  "generatedAt": "2025-02-16T23:20:00Z",
  "items": [
    { "path": "art/2025/foo.webp", "tags": ["portrait"], "notes": "cover", "name": "foo.webp" }
  ]
}
```

------

## 6. Worker Responsibilities

- **Indexer**: scan folders, build `_index.json` if missing/stale.
- **Thumbnailer**: generate `.thumbnail` files for images missing thumbs.
- **Rollup builder**: aggregate sidecars into `_rollup.json` for search.
- **Metrics**: track missing thumbs, orphan sidecars, broken pointers → write `_health.json`.

Tools: asyncio + aioboto3 for S3, pyvips for thumbs, orjson for JSON, blake3 for hashing.

------

## 7. Performance Requirements

- **Latency**:
  - `GET /folders`: <500ms for 1k items (cached).
  - `GET /item`: <200ms for sidecar fetch.
  - `GET /thumb`: <200ms if exists, <1s if generated.
- **Indexing throughput**: ≥300 items/sec EXIF + thumb generation.
- **Scalability**: up to 500k assets per root folder.
- **Statelessness**: server scales horizontally; workers scale independently.

------

## 8. Failure Modes

- Missing `_index.json` → rebuild on-demand.
- Missing sidecar → create on first write.
- S3 permission denied → 403 error surfaced to client.
- Worker backlog → return 202 (Accepted) with retry hint.
- Pointer loops → detect and return error JSON.

------

## 9. Risks & Mitigation

- **S3 cost explosion (GET/HEAD flood)** → use folder manifests, cache aggressively.
- **Large manifests (10k+ items)** → paginate `_index.json` (`_index_0.json`, `_index_1.json`).
- **Worker backlog delay** → prioritization queue (thumb > rollup).
- **Conflicts in sidecar updates** → last-writer-wins w/ timestamp, additive merge for tags.

------

## 10. Success Metrics

- 95% of `GET /folders` served from existing manifests.

- > 85% thumbnail cache hit.

- Worker SLA: new file indexed + thumbed within 2 minutes.

- Zero server crashes under 500k assets.

- P95 API latency <500ms for reads.

------

## 11. Roadmap

**MVP (this doc):**

- Endpoints: folders, item CRUD, thumbs, search, health.
- Workers: indexer, thumb gen, rollup builder.
- Local + S3 backends.

**Future:**

- Auth/ACLs.
- Tauri backend provider.
- AI recall indexing (embeddings).
- Collaboration (multi-user sidecar updates).

