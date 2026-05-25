# 2026-02-27 Multi-Library Hub MVP Design

## Problem Statement

Lenslet currently encourages a one-process-per-gallery workflow:

- Start Lenslet on one folder.
- If another folder should be shared/browsed, start another Lenslet process.
- Repeat over time until many background instances exist.

This creates operator overhead:

- Too many local processes and ports to manage.
- Too many share URLs and unclear lifecycle for old galleries.
- Hard to revisit archival datasets without keeping all servers running.

Target outcome for this project:

- Keep one long-lived Lenslet server process.
- Add/remove/switch gallery libraries on demand.
- Use one URL and one UI shell for day-to-day browsing.
- Load only what is needed now; avoid keeping all historical galleries active.

Non-goals for MVP:

- Full concurrent browsing across multiple libraries with isolated URL scopes and isolated caches.
- Complex policy/fallback machinery.

## How Current Code Works

### Process and Sharing Model

- `lenslet <path>` launches one FastAPI app bound to one storage target.
- `--share` starts a cloudflared tunnel for that process/port only.
- If a second folder needs sharing, a second Lenslet process is typically started.

Key paths:

- CLI startup and `--share` tunnel: `src/lenslet/cli.py`
- App creation entrypoints: `src/lenslet/server_factory.py`, `src/lenslet/server.py`

### Storage Model

Lenslet has three server modes, chosen at startup:

- Filesystem mode (`create_app`) for local folders.
- Table mode (`create_app_from_table` / `create_app_from_storage`) for parquet/table-backed data.
- Dataset mode (`create_app_from_datasets`) for programmatic named datasets.

Important detail:

- `create_app` already uses `StorageProxy`, which supports swapping backing storage in-process.
- Dataset/table app factories are effectively static after startup.

Key paths:

- `StorageProxy` and app wiring: `src/lenslet/server_factory.py`
- Filesystem storage: `src/lenslet/storage/memory.py`, `src/lenslet/storage/local.py`
- Dataset storage: `src/lenslet/storage/dataset.py`
- Table storage: `src/lenslet/storage/table.py`

### API and Frontend Assumptions

Current API/UX assumes one active root tree:

- Folder/search endpoints are path-scoped and assume a single active data root.
- Frontend query keys are path-based (no library id namespace).
- Left sidebar root is fixed to `/`.

Implication:

- Runtime multi-library support needs explicit library identity in both backend state and frontend cache keys.

Key paths:

- Folder routes: `src/lenslet/server_routes_common.py`
- Request storage access: `src/lenslet/server_browse.py`
- Frontend sidebar root and folder UX: `frontend/src/app/components/LeftSidebar.tsx`
- Frontend folder query keys: `frontend/src/api/folders.ts`

## Proposed Delivery Approach (MVP)

### Product Shape

Introduce a **Hub Mode** with one long-lived server process and a managed library registry.

Core user flow:

1. Start one server: `lenslet serve`.
2. Add libraries: `lenslet add <path> [--name ...]`.
3. Switch active library from UI or CLI.
4. Remove/deactivate old libraries without killing the server.

MVP constraint:

- One **active** library at a time for browse/search/edit operations.
- Many libraries may be registered; inactive libraries are not actively loaded.

This keeps implementation small while solving process sprawl.

## MVP Scope

### 1) Library Registry

Add a small persisted registry file in Lenslet workspace state (hub-level state):

- `id`, `name`, `source`, `type` (folder/table/dataset), timestamps.
- `active_library_id`.

Operations:

- Add library.
- List libraries.
- Set active library.
- Remove library.

No background orchestration layer; plain file-backed registry is enough for MVP.

### 2) Runtime Active Library Switch

Use a single runtime pointer for the active library context:

- Active `storage`.
- Active `workspace`.
- Active optional embedding manager.

When switching:

- Swap runtime context atomically.
- Clear/invalidate request-layer caches tied to old library.
- Keep one process, one port, one share URL.

Implementation direction:

- Reuse existing `StorageProxy` seam.
- Extend app runtime state so routes resolve active context at request time, not only at startup capture time.

### 3) Minimal Hub API

Add explicit endpoints (local admin intent):

- `GET /libraries`
- `POST /libraries` (add)
- `POST /libraries/activate`
- `DELETE /libraries/{id}`
- `GET /libraries/active`

Keep these simple and deterministic. No soft-deletion lifecycle, no policy engine.

### 4) CLI Commands

Add thin commands on top of hub API:

- `lenslet serve`
- `lenslet add <path> [--name NAME]`
- `lenslet list`
- `lenslet use <id-or-name>`
- `lenslet rm <id-or-name>`

### 5) Frontend Changes (Minimal)

Add a lightweight library switcher:

- Show library list + current active library.
- Switch active library.

Technical requirement:

- Namespace query keys and session caches by `library_id` to avoid path collisions.

Out of scope for MVP:

- Multi-library side-by-side browsing.
- Per-library tab sets.

## Delivery-Critical Decisions (Keep It Boring)

1. One active library at a time.
2. Explicit activate action (no implicit auto-switch on add).
3. No opportunistic preloading of inactive libraries.
4. No fallback compatibility layer for old multi-process behavior beyond existing commands.
5. Keep registry and runtime state local and synchronous.

## Risks and What We Intentionally Do Not Solve in MVP

- Active switch latency for very large datasets is acceptable initially.
- No advanced eviction policy (active-only loading already limits memory growth materially).
- No per-library URL scope isolation yet.

These are conscious scope cuts to deliver quickly.

## Nice to Haves (Post-MVP)

1. Full multi-library concurrent browsing with stable per-library URL scope and isolated caches.
2. Auto-unload policy for inactive libraries (TTL/LRU with observability).
3. Background warmup for recently used libraries.
4. Stronger admin auth model for remote/shared environments.
5. Bulk import/export of library registry.

## Suggested Sprint Breakdown (for planning handoff)

1. Backend hub registry + active runtime context switching.
2. Hub API + tests.
3. CLI hub commands.
4. Frontend library switcher + cache key namespacing.
5. Integration tests + docs updates.
