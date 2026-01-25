# Collaboration & Label Sync Review (Lenslet)

Date: 2026-01-04 (updated 2026-01-23)

## Scope
Reviewed how label/progress metadata is stored and synchronized across users/sessions in the current codebase. Focused on server storage layers, API behavior, and frontend caching/refresh behavior. Updated to reflect new storage modes and disk write behavior.

## Current Goal
Minimum viable collaboration: **different users should see each other’s labeling changes without needing to refresh the page**, and configuration for this sync should be handled cleanly. **Shared filters/views or other UI preferences are explicitly out of scope** for this phase.

## Current State (What Actually Syncs Today)

### Storage & Persistence
- **Label metadata (stars/tags/notes)** is **still in-memory only** across all storage backends:
  - `src/lenslet/storage/memory.py` (`_metadata`, `set_metadata` comment “session-only, lost on restart”)
  - `src/lenslet/storage/dataset.py` (in-memory metadata keyed by logical path)
  - `src/lenslet/storage/table.py` (table-backed datasets; metadata cache only)
  - `src/lenslet/storage/parquet.py` exists but is **not the primary code path** for `.parquet` datasets
- **No disk persistence** for label metadata. If the server restarts, labels are lost.
- **Workspace writes are broader now** (still not label persistence):
  - **Smart Folders** are written under `.lenslet/views.json` for folder datasets, or to `<parquet>.lenslet.json` for parquet mode (`Workspace.views_override`).
  - **Thumbnail cache** can be written on disk under `.lenslet/thumbs` (or `<parquet>.cache/thumbs`).
  - **OG preview cache** can be written on disk under `.lenslet/og-cache` (or `<parquet>.cache/og-cache`).
  - **Optional parquet width/height caching** can write back to `items.parquet` (enabled by default; disable with `--no-cache-wh`, or with `--no-write`).

### Server API Behavior
- `PUT /item` updates **only the in-memory metadata** (`src/lenslet/server.py`); it does **not** persist to disk.
- `GET /item` returns a **fresh `updated_at` timestamp on every call**, not the true last-modified time. `updated_by` is static (`"server"`) on read.
- `PUT /item` ignores most sidecar fields (`exif`, `hash`, `original_position`) beyond tags/notes/star.
- No versioning, no ETags, no conflict detection, no locking, and no merge behavior.
- `PUT /views` writes the full views payload with **last-write-wins** semantics and no merge.

### Frontend Sync Behavior
- React Query **does not poll** and **does not refetch on window focus** (`frontend/src/App.tsx`, `frontend/src/api/folders.ts`, `frontend/src/api/items.ts`).
- Other users’ updates are not pushed to clients. They only see changes if they **manually trigger a refetch** (e.g., navigating or reloading).
- Some UI state (filters, star filters, layout prefs) is stored **locally in the browser** (`localStorage`) and is not shared.

### Multi‑User Reality Today
- **Multiple clients on the same server instance** will share the same in-memory labels, but **they won’t see each other’s updates in real time** without a refetch.
- **Multiple server instances** pointed at the same dataset **do not share labels at all**, since label data is not persisted.
- **Dataset and table modes** are effectively static for label updates; metadata remains in-memory only.

**Bottom line:** There is **no real synchronization** of labeling progress across multiple users today beyond in-memory sharing within a single running server process. This is not a reliable collaboration layer and resets on restart.

## Is There an Easier Way to Sync Changes Today?
Not really. The current design **still avoids writing label metadata** into the dataset directory and keeps all labels in memory, even though it now writes caches (thumbs/OG) and can write width/height back to parquet. Without **label persistence + a propagation mechanism**, real collaboration will be unreliable. At best, you can add a minimal persistence layer and lightweight polling/SSE, but it’s still a stop‑gap.

## Updated Implementation Paths

### 1) In‑Memory Real‑Time Sync (No DB File)
Goal: Enable multi‑user realtime label updates (5–10 collaborators) without introducing a database file. Authoritative state lives in memory, with optional write‑behind snapshots to parquet or workspace sidecars.

**Idea:** Keep a canonical in‑memory store of sidecar state + versions, add optimistic concurrency + idempotency, and broadcast changes via SSE. Optionally snapshot to workspace sidecars or parquet as a safety net.

Minimal building blocks:
- **In‑memory authoritative store** for `{tags, notes, star, metrics, updated_at, updated_by, version}` keyed by item path.
- **Optimistic concurrency** via `If-Match` (or `base_version`) on `PUT /item`; return `409` with latest state on version mismatch.
- **Idempotency** via `Idempotency-Key` header + in‑memory TTL cache to prevent duplicate writes on retries.
- **SSE events** for `item-updated`, `metrics-updated`, `presence` (and optional `metrics-progress`).
- **Presence tracking** in memory with heartbeat pings (per‑gallery counts).
- **Optional write‑behind**:
  - Snapshot to workspace sidecars (`.lenslet/sidecars/` or `<parquet>.cache/sidecars/`), or
  - Lazy write of merged metadata to parquet (if enabled).
- **Respect `--no-write`**: stay purely in memory and surface a clear warning banner.

This is enough for 5–10 users with basic conflict protection and realtime updates, without a database file.

### 2) Systematic / Pragmatic Collaboration Foundation (Optional)
Goal: Build a real collaboration layer and user system that can scale to multi-user labeling workflows.

Key design changes:
- **Centralized state store** (SQLite/Postgres) for sidecar metadata, annotations, and audit trails.
- **User system + auth**, with per-user attribution (`updated_by`), permissions, and per-workspace scopes.
- **Versioning / concurrency control** (ETags or record versions) to detect conflicting edits.
- **Event streaming** (WebSocket or SSE) for real-time updates to all clients.
- **Normalized data model** separating datasets, items, annotations, users, and workspaces.
- **Dataset ID strategy** (stable IDs vs. path-based keys). Parquet may provide `image_id`; local paths do not.
- **Background indexing / refresh** for dataset changes and derived stats (progress, completion rates, per-user summaries).
- **Migration path** from file sidecars to DB (import sidecar JSON into DB on first run).

This is heavier but sets the right foundation for collaboration and multiple profiles/workspaces.

## Spec Addendum (Realtime Labels + Async Metrics + Presence)

### Data Model (In‑Memory)
- **Sidecar** fields: `tags[]`, `notes`, `star`, `metrics{}`, `updated_at`, `updated_by`, `version`.
- **Version** is a monotonic integer; increment on each accepted write or metric update.
- **Presence** keyed by `gallery_id` with `{client_id -> {last_seen, status}}`.

### API Contract (Minimal)
- `GET /item?path=...` returns sidecar with **stored** `updated_at` and `version` (no synthetic timestamps).
- `PUT /item?path=...`
  - Requires `If-Match: <version>` (or `base_version` in body) for collaboration mode.
  - Requires `Idempotency-Key: <client_id>:<seq>`.
  - **409 Conflict** on version mismatch; response includes latest sidecar + version.
  - **200 OK** on success; response includes updated sidecar + new version.
- `GET /events` (SSE)
  - `item-updated`: `{path, version, tags, notes, star, updated_at, updated_by}`
  - `metrics-updated`: `{path, version, metrics, updated_at, updated_by}`
  - `presence`: `{gallery_id, viewers, editors, updated_at}`
- `POST /presence`
  - Body: `{gallery_id, client_id, status: "viewing" | "editing"}`
  - Server updates last_seen and broadcasts `presence` counts.

### Conflict + Idempotency Rules
- **Optimistic concurrency** prevents overwrite: stale `If-Match` returns 409.
- **Idempotency** prevents double‑apply on retries: duplicate key returns cached response.
- **Last-write-wins** applies only when the client explicitly rebases and retries.

### Frontend Sync UX
- **Per‑item save state**: `Saving...` -> `Saved` on 200/SSE ack -> `Not saved (newer change detected)` on 409.
- **Conflict action**: offer “Apply my change again” (rebase) or “Keep theirs”.
- **Sync progress indicator**: show “Syncing” while requests in flight; “All changes saved” when queue is empty.

### Activity + Presence UX
- **Gallery presence**: show `X viewing, Y editing` (updated via SSE).
- **Recent activity warning**: if `item-updated` events occurred in the last N seconds, show a subtle banner like “Someone updated items recently”.

### Async Metrics UX
- When metrics complete, server emits `metrics-updated`; the client updates the grid without refresh.
- Optional `metrics-progress` SSE event can drive a lightweight “computing metrics...” banner.

## Implementation Checklist (Minimal In‑Memory)
1) **Add versioning + idempotency**
   - Store per‑item `version` in the in‑memory metadata map.
   - Add an in‑memory idempotency cache with TTL (e.g., 10–30 minutes).
2) **Update `/item` API**
   - `GET /item` returns stored `updated_at` + `version` (no synthetic timestamps).
   - `PUT /item` enforces `If-Match` / `base_version`, returns `409` on mismatch.
   - Require `Idempotency-Key`; cache responses by key.
3) **Add SSE endpoint**
   - Stream `item-updated`, `metrics-updated`, and `presence`.
   - Broadcast on successful writes and metric updates.
4) **Presence tracking**
   - Add `/presence` heartbeat (POST) to update in‑memory presence.
   - Broadcast aggregated counts via SSE.
5) **Frontend sync states**
   - Add per‑item save state (`saving` → `saved` → `conflict`).
   - Add global sync indicator (“Syncing…” / “All changes saved”).
6) **Frontend event handling**
   - Subscribe to SSE; update cache on `item-updated` / `metrics-updated`.
   - Show recent activity banner if updates in last N seconds.
7) **Async metrics hook (future‑proof)**
   - Accept `metrics-updated` events and update current view.
   - Optional progress events for “computing metrics…” banner.
8) **Optional write‑behind**
   - Snapshot sidecars to workspace or parquet on interval or batch size.

## SSE Event Examples

```json
{
  "event": "item-updated",
  "data": {
    "path": "/animals/cat.jpg",
    "version": 12,
    "tags": ["cute", "pet"],
    "notes": "golden hour",
    "star": 4,
    "updated_at": "2026-01-23T19:22:05Z",
    "updated_by": "web"
  }
}
```

```json
{
  "event": "metrics-updated",
  "data": {
    "path": "/animals/cat.jpg",
    "version": 13,
    "metrics": { "aesthetic": 0.91, "blur": 0.03 },
    "updated_at": "2026-01-23T19:25:11Z",
    "updated_by": "metrics-worker"
  }
}
```

```json
{
  "event": "presence",
  "data": {
    "gallery_id": "root",
    "viewers": 3,
    "editors": 1,
    "updated_at": "2026-01-23T19:25:15Z"
  }
}
```

```json
{
  "event": "metrics-progress",
  "data": {
    "gallery_id": "root",
    "percent": 42,
    "message": "Computing metrics..."
  }
}
```

## UI Copy + Placement (Suggested)
- **Global sync indicator** (top toolbar, right side):  
  - `Syncing…` (when any in‑flight writes)  
  - `All changes saved` (steady state)  
  - `Not saved — retry` (after error)
- **Per‑item conflict badge** (inspector panel near stars/tags/notes):
  - `Newer change detected`  
  - Actions: `Apply my changes again` / `Keep theirs`
- **Presence indicator** (top toolbar, left or center):
  - `3 viewing · 1 editing`
- **Recent activity banner** (subtle, below toolbar):
  - `Someone updated items in the last 30s`

## Error Handling Matrix (Client UX)
- **200 OK (PUT /item)**: mark item `saved`, update cache with server payload + version.
- **202 Accepted (optional for async metrics)**: show “Queued” state; await SSE update.
- **400 Bad Request**: show “Invalid update” toast; keep local edits but mark `error`.
- **401/403**: show “Permission denied” banner; disable edits.
- **404 Not Found**: show “Item missing” warning; remove item from selection.
- **409 Conflict**: show “Newer change detected” badge; fetch latest and offer rebase.
- **429 Too Many Requests**: show “Sync paused (rate limit)” and retry with backoff.
- **5xx / network error**: show “Not saved — retry”; keep local changes queued.

## Handoff: Codebase Touchpoints + Plan
This section is intended as a handoff so another engineer can implement the design quickly.

### Backend Touchpoints
- `src/lenslet/server.py`
  - `Sidecar` model (add `version`, ensure `updated_at` is stored, not synthetic).
  - `GET /item` (`get_item`) and `PUT /item` (`put_item`) to enforce `If-Match` and idempotency.
  - Add `GET /events` (SSE) and `POST /presence`.
  - Update `_build_sidecar` to return stored timestamps and version.
- `src/lenslet/storage/*`
  - All storage backends keep metadata in memory; add `version` field storage.
  - Ensure any new fields (metrics) are part of metadata dicts.
- `src/lenslet/workspace.py`
  - Optional: add workspace sidecar snapshot folder helpers if write‑behind is desired.

### Frontend Touchpoints
- `frontend/src/api/items.ts`
  - Include `If-Match` and `Idempotency-Key` on `PUT /item`.
  - Handle `409` by surfacing conflict state.
- `frontend/src/api/client.ts`
  - Add SSE client for `/events`.
  - Add `/presence` heartbeat calls.
- `frontend/src/app/AppShell.tsx`
  - Global sync indicator + presence indicator.
  - Recent activity banner (based on last `item-updated` event).
- `frontend/src/features/inspector/*`
  - Per‑item conflict UI and retry controls near stars/tags/notes.

### Minimal Server Logic (Pseudo)
1) On `PUT /item`:
   - Check `Idempotency-Key` cache; if hit, return cached response.
   - Compare `If-Match` to in‑memory `version`; return `409` + latest on mismatch.
   - Apply patch, increment version, set `updated_at`, cache response.
   - Broadcast `item-updated` SSE event.
2) On `GET /item`:
   - Return stored sidecar including `version` and `updated_at`.
3) On presence heartbeat:
   - Update `{client_id, status, last_seen}` in memory.
   - Broadcast `presence` SSE with aggregate counts.

### Open Questions / Defaults (Recommended)
- **Client identity**: generate a stable `client_id` per browser (localStorage UUID).
- **Version origin**: start at `1` for new items.
- **Idempotency TTL**: 10–30 minutes; LRU cap (e.g., 10k keys).
- **Presence timeout**: consider a user stale if `last_seen > 15s`.
- **Recent activity window**: 30s for banner display.

### Testing Notes
- Use two browser tabs to confirm:
  - Realtime sync via SSE (no refresh).
  - 409 conflict and UI warning.
  - Presence count updates.
  - Idempotency on repeated retries (same key).

## Current Challenges & Risks for Collaboration
- **No persistence** of labeling progress; server restart wipes labels.
- **No real-time propagation** of changes; clients don’t auto-refresh.
- **No conflict detection**; concurrent edits will silently overwrite each other.
- **Misleading timestamps**: `GET /item` always returns “now,” so timestamps can’t be trusted for sync.
- **Lack of stable item identity** across datasets (path-based keys only).
- **No user model** (all updates look like “server” or “web”).
- **Views persistence is global** and not per-user; in parquet mode, views are stored in `<parquet>.lenslet.json`. No merge handling.
- **Dataset/table modes are static** with respect to label persistence; metadata remains in-memory only.

## Recommendation Summary
- **If you want multi-user realtime now**, implement the in‑memory spec above with optimistic concurrency, idempotency, SSE, and presence.
- **If collaboration and user systems become core goals**, plan for a durable store later (DB or robust write‑behind + log).

Both approaches can coexist: the tinkering pass buys time, but it should be seen as a temporary bridge.
