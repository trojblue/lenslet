# Collaboration & Label Sync Review (Lenslet)

Date: 2026-01-04

## Scope
Reviewed how label/progress metadata is stored and synchronized across users/sessions in the current codebase. Focused on server storage layers, API behavior, and frontend caching/refresh behavior.

## Current Goal
Minimum viable collaboration: **different users should see each other’s labeling changes without needing to refresh the page**, and configuration for this sync should be handled cleanly. **Shared filters/views or other UI preferences are explicitly out of scope** for this phase.

## Current State (What Actually Syncs Today)

### Storage & Persistence
- **Label metadata (stars/tags/notes)** is **in-memory only** across all storage backends:
  - `src/lenslet/storage/memory.py` (`_metadata`, `set_metadata` comment “session-only, lost on restart”)
  - `src/lenslet/storage/dataset.py` (in-memory metadata keyed by logical path)
  - `src/lenslet/storage/parquet.py` (metadata cache, **no writes back to parquet**)
- **No disk persistence** for label metadata. If the server restarts, labels are lost.
- **Only `views.json` is written on disk** under `.lenslet/`:
  - `src/lenslet/workspace.py` stores and reads `views.json` (Smart Folders)
  - Example data: `data_backup/.lenslet/views.json`

### Server API Behavior
- `PUT /item` updates **only the in-memory metadata** (`src/lenslet/server.py`).
- `GET /item` returns a **fresh `updated_at` timestamp on every call**, not the true last-modified time. `updated_by` is static (`"server"`) on read.
- No versioning, no ETags, no conflict detection, no locking, and no merge behavior.
- `PUT /views` writes the full `views.json` file with **last-write-wins** semantics and no merge.

### Frontend Sync Behavior
- React Query **does not poll** and **does not refetch on window focus** (`frontend/src/App.tsx`, `frontend/src/api/folders.ts`, `frontend/src/api/items.ts`).
- Other users’ updates are not pushed to clients. They only see changes if they **manually trigger a refetch** (e.g., navigating or reloading).
- Some UI state (filters, star filters, layout prefs) is stored **locally in the browser** (`localStorage`) and is not shared.

### Multi‑User Reality Today
- **Multiple clients on the same server instance** will share the same in-memory labels, but **they won’t see each other’s updates in real time** without a refetch.
- **Multiple server instances** pointed at the same dataset **do not share labels at all**, since label data is not persisted.
- **Dataset mode** is explicitly static; metadata remains in-memory only.

**Bottom line:** There is **no real synchronization** of labeling progress across multiple users today beyond in-memory sharing within a single running server process. This is not a reliable collaboration layer and resets on restart.

## Is There an Easier Way to Sync Changes Today?
Not really. The current design intentionally avoids writing into the dataset directory and keeps all labels in memory. Without persistence + a propagation mechanism, real collaboration will be unreliable. At best, you can add a minimal persistence layer and lightweight polling/SSE, but it’s still a stop‑gap.

## Two Possible Paths Forward

### 1) Tinkering Pass (Minimal Sync Add‑On)
Goal: Add the smallest possible mechanism to sync labeling progress across users without a full user system.

**Idea:** Persist sidecar metadata in `.lenslet/sidecars/` and add light polling/SSE so other clients receive updates.

Minimal building blocks:
- **Persist sidecars on disk** (per-image JSON under `.lenslet/sidecars/`).
  - Read on `GET /item`, write on `PUT /item` (atomic file replace).
  - Include `updated_at` and `updated_by` on server write.
- **ETag / If-None-Match** on `/item` responses so clients can cheaply check for changes.
- **Polling or SSE** in the frontend to refresh sidecar data (e.g., refetch every 10–30s or on SSE “item-changed” event).
- **Last-write-wins** conflict model (acceptable for a minimal pass, but it’s still lossy).

This gives “good enough” syncing for small teams but won’t handle conflicts, auditing, or per-user state correctly.

### 2) Systematic / Pragmatic Collaboration Foundation
Goal: Build a real collaboration layer and user system that can scale to multi-user labeling workflows.

Key design changes:
- **Centralized state store** (SQLite/Postgres) for sidecar metadata, annotations, and audit trails.
- **User system + auth**, with per-user attribution (`updated_by`), permissions, and potentially per-workspace scopes.
- **Versioning / concurrency control** (ETags or record versions) to detect conflicting edits.
- **Event streaming** (WebSocket or SSE) for real-time updates to all clients.
- **Normalized data model** separating datasets, items, annotations, users, and workspaces.
- **Dataset ID strategy** (stable IDs vs. path-based keys). Parquet has `image_id`, local paths do not.
- **Background indexing / refresh** for dataset changes and derived stats (progress, completion rates, per-user summaries).

This is heavier but sets the right foundation for collaboration and multiple profiles/workspaces.

## Current Challenges & Risks for Collaboration
- **No persistence** of labeling progress; server restart wipes labels.
- **No real-time propagation** of changes; clients don’t auto-refresh.
- **No conflict detection**; concurrent edits will silently overwrite each other.
- **Misleading timestamps**: `GET /item` always returns “now,” so timestamps can’t be trusted for sync.
- **Lack of stable item identity** across datasets (path-based keys only).
- **No user model** (all updates look like “server” or “web”).
- **Views persistence is global** (`views.json`), not per-user, and no merge handling.
- **Dataset mode is static**, not designed for write/update flows.

## Recommendation Summary
- **If you want a short-term multi-user sync**, add file‑based sidecars + polling/SSE (tinkering pass).
- **If collaboration and user systems are core goals**, move label data into a database with real-time update channels and versioned writes (systematic approach).

Both approaches can coexist: the tinkering pass buys time, but it should be seen as a temporary bridge.
