# Collaboration Sync Plan (In‑Memory Realtime + Write‑Behind)


## Purpose / Big Picture


Implement realtime multi‑user label sync for Lenslet without adding a database file. Users will see stars/tags/notes update live across clients, understand whether their edits are safely synced, see lightweight presence counts, and receive live metric updates when they arrive. The system remains in‑memory authoritative with durable write‑behind to the workspace when writable, and behaves gracefully in no‑write mode.


## Progress


- [x] 2026-01-23: Plan drafted.
- [x] 2026-01-23: Sprint 1 backend implementation completed; manual SSE + restart checks passed.


## Surprises & Discoveries


The current storage backends store metadata in memory but do not canonicalize item paths consistently (especially `MemoryStorage`), which would cause duplicate keys and false conflicts when adding versioning and SSE. The existing `PUT /item` handler effectively behaves like a full replace, which is unsafe once partial updates and rebases are introduced.


## Decision Log


2026-01-23 — Use in‑memory authoritative state with write‑behind snapshots and a JSONL append log in the workspace. This avoids a database file while preventing data loss on restarts.

2026-01-23 — Introduce a `PATCH /item` endpoint with patch semantics; keep `PUT /item` as a full replace for backward compatibility. This reduces conflict pain and avoids accidental clobbering.

2026-01-23 — Use SSE as the primary realtime channel with reconnect replay via a short in‑memory ring buffer and `Last-Event-ID` support. Add a minimal polling fallback only when SSE is down.

2026-01-23 — Define `gallery_id` as the normalized folder path (using a shared canonicalizer) and track per‑gallery presence counts for viewing vs editing (editing defined as “write within last 60s”).


## Outcomes & Retrospective


Sprint 1 delivered backend realtime primitives and durability. Two SSE clients receive updates, version conflicts return 409, and labels persist across restart when the workspace is writable. See “Sprint 1 Handover Notes” for details and test status.


## Context and Orientation


Lenslet serves images via a FastAPI app (`src/lenslet/server.py`) and stores label metadata in memory in each storage backend. The frontend uses React Query and does not currently poll or refetch on focus. The plan is to extend the server with SSE, idempotency, and versioning, add a patch endpoint for metadata updates, and update the frontend to show sync and presence indicators.

Relevant files and modules include `src/lenslet/server.py` for routes and SSE, the storage backends in `src/lenslet/storage/memory.py`, `src/lenslet/storage/dataset.py`, `src/lenslet/storage/table.py`, and `src/lenslet/storage/parquet.py` for in‑memory metadata maps, `src/lenslet/workspace.py` for workspace write locations, and the frontend integration points in `frontend/src/api/client.ts`, `frontend/src/api/items.ts`, `frontend/src/app/AppShell.tsx`, and inspector components.


## Plan of Work


The work proceeds in two demoable sprints plus a hardening pass. Sprint 1 delivers backend realtime primitives with persistence and replay. Sprint 2 wires the frontend to these primitives and adds user‑visible sync/presence UI. Sprint 3 hardens reconnection, fallback, and tests to make the system reliable for 5–10 collaborators.

Sprint Plan:

1) Sprint 1 — Backend realtime core and durability. Demo outcome: two browser clients see tag/star/note changes live, version conflicts return 409, and data survives a server restart when workspace is writable. Tasks: T1–T9.
2) Sprint 2 — Frontend sync UX and presence. Demo outcome: global sync indicator, conflict banner, presence pill, recent activity banner, and persistence warning appear and react to remote edits. Tasks: T10–T17.
3) Sprint 3 — Reliability hardening and tests. Demo outcome: SSE reconnects and replays missed events, a polling fallback engages when SSE is down, and automated tests cover idempotency/conflicts/replay/persistence. Tasks: T18–T22.


## Concrete Steps


Commands are run from `/home/ubuntu/dev/lenslet`.

Task/Ticket Details:

1) T1 — Add a canonical path helper in `src/lenslet/server.py` and use it for all metadata keys, versioning, SSE payload paths, and `gallery_id` derivation. Affected: `src/lenslet/server.py`, storage access wrappers. Validation: update one item using `PUT /item` with `/path` and `path` variants and verify the same metadata record is used and the same SSE path is emitted.

2) T2 — Add per‑item version storage in all in‑memory metadata maps and initialize `version = 1` for new items. Affected: `src/lenslet/storage/memory.py`, `src/lenslet/storage/dataset.py`, `src/lenslet/storage/table.py`, `src/lenslet/storage/parquet.py`, `src/lenslet/server.py`. Validation: `GET /item` returns `version` and increments on each successful update.

3) T3 — Implement idempotency cache with TTL in `src/lenslet/server.py` and enforce `Idempotency-Key` on `PATCH /item`. Affected: `src/lenslet/server.py`. Validation: send the same key twice and verify the response is identical and no extra version increment occurs.

4) T4 — Document the API contract and event schema in a new doc (request/response shapes, headers, error payloads, SSE events) and align frontend TypeScript types with it. Affected: `docs/20260123_collaboration_sync_api.md` (new), frontend type definitions used by `frontend/src/api/*.ts` imports. Validation: doc exists in `docs/` and frontend types compile with the new schema.

5) T5 — Implement `PATCH /item` with patch semantics and optimistic concurrency (`If-Match` or `base_version`). Keep `PUT /item` as full replace for compatibility. Affected: `src/lenslet/server.py`, frontend calls in `frontend/src/api/items.ts`. Validation: send a partial patch to update star only and confirm tags/notes remain unchanged; send stale version and confirm 409 with latest state.

6) T6 — Add SSE endpoint `GET /events` with event IDs, ring buffer replay, and `Last-Event-ID` support. Broadcast `item-updated`, `metrics-updated`, and `presence`. Affected: `src/lenslet/server.py`. Validation: open two clients; confirm realtime updates without refresh, and a reconnect receives missed events using `Last-Event-ID`.

7) T7 — Implement write‑behind log append (`.lenslet/labels.log.jsonl`) for accepted updates and include event IDs for replay. Affected: `src/lenslet/workspace.py`, `src/lenslet/server.py`. Validation: inspect log lines and ensure each accepted update produces one line with the expected schema.

8) T8 — Implement snapshot writer (`.lenslet/labels.snapshot.json`) and startup replay (load snapshot then replay log). Affected: `src/lenslet/workspace.py`, `src/lenslet/server.py`. Validation: make edits, restart server, and confirm labels persist; replay is idempotent.

9) T9 — Add single‑worker guardrails and persistence status surfacing. Emit a warning or refuse multi‑worker mode, and ensure a backend flag for persistence status is available to the frontend (e.g., reuse `/health`). Affected: `src/lenslet/cli.py`, `src/lenslet/server.py`. Validation: starting with multiple workers logs a warning; `/health` exposes persistence status for UI banner.

10) T10 — Update frontend API layer to include `Idempotency-Key` and `If-Match` on updates; generate a stable `client_id` in localStorage and handle 409 conflicts by surfacing conflict state. Affected: `frontend/src/api/items.ts`, `frontend/src/api/client.ts`, `frontend/src/features/inspector/Inspector.tsx`. Validation: simulate a stale update and verify the conflict UI appears.

11) T11 — Add SSE client baseline (subscribe, cache updates for `item-updated` and `metrics-updated`) and minimal reconnect handling. Affected: `frontend/src/api/client.ts`, `frontend/src/app/AppShell.tsx`. Validation: remote edits in another client show within 1–2 seconds without refresh.

12) T12 — Implement global sync indicator states (“Syncing…”, “All changes saved”, “Not saved — retry”). Affected: `frontend/src/app/AppShell.tsx`. Validation: trigger a write and observe indicator transitions.

13) T13 — Add per‑item conflict badge with actions (“Apply my changes again” / “Keep theirs”) near stars/tags/notes, with auto‑merge for tags/stars and manual resolution for notes. Affected: `frontend/src/features/inspector/Inspector.tsx`, shared UI components. Validation: produce a conflict and verify both actions resolve correctly.

14) T14 — Add per‑gallery presence heartbeat and UI pill showing counts and editing vs viewing (editing = write within last 60s). Affected: `frontend/src/api/client.ts`, `frontend/src/app/AppShell.tsx`, `src/lenslet/server.py`. Validation: open two browsers; observe presence counts update; write in one and see editor count.

15) T15 — Add recent activity banner for updates within the last 30 seconds; optionally highlight updated grid items briefly. Affected: `frontend/src/app/AppShell.tsx`, grid components. Validation: remote update triggers banner and highlight.

16) T16 — Add persistence warning banner when workspace is not writable or `--no-write` is enabled. Affected: `frontend/src/app/AppShell.tsx`, `src/lenslet/server.py` (`/health`). Validation: run with `--no-write` and confirm banner appears and labels are marked ephemeral.

17) T17 — Add connection status UI (`Live` / `Reconnecting…` / `Offline`) derived from SSE state. Affected: `frontend/src/app/AppShell.tsx`. Validation: stop SSE endpoint and confirm UI transitions.

18) T18 — Add SSE heartbeat keepalive and reconnection backoff on the client; ensure `Last-Event-ID` is sent on reconnect. Affected: `frontend/src/api/client.ts`, `src/lenslet/server.py`. Validation: disconnect network briefly and confirm missed events replay after reconnect.

19) T19 — Add polling fallback when SSE cannot reconnect after backoff, and disable fallback once SSE recovers. Affected: `frontend/src/api/client.ts`, `frontend/src/api/folders.ts`. Validation: force SSE failure and confirm polling refetches; restore SSE and confirm polling stops.

20) T20 — Add snapshot/log compaction or rotation plus atomic write strategy (fsync/atomic rename) to prevent log growth and corruption. Affected: `src/lenslet/workspace.py`, `src/lenslet/server.py`. Validation: simulate a long log and confirm compaction keeps startup time bounded.

21) T21 — Add backend tests for `PATCH /item` conflict handling, idempotency, replay via `Last-Event-ID`, and snapshot/log persistence using `httpx.AsyncClient`. Affected: `tests/`, `src/lenslet/server.py`. Validation: `pytest` passes locally.

22) T22 — Add frontend QA checklist (manual) and update docs with operational notes and known limits (single worker, no‑write behavior, fallback polling). Affected: `docs/`, `frontend/`. Validation: doc updates are present and the checklist passes in a two‑client demo.


## Validation and Acceptance


Per Sprint:

Sprint 1 is accepted when canonicalized paths yield consistent item IDs, versioning prevents stale overwrites (409), SSE broadcasts are visible in a second client, labels persist across restart when workspace is writable, and a single‑worker warning is emitted when appropriate. Sprint 2 is accepted when users see sync status, conflicts, presence counts, recent activity, persistence warning banner, and connection status without refresh. Sprint 3 is accepted when SSE reconnects with replay, polling fallback works during disconnect, compaction keeps log size bounded, and automated tests cover idempotency/conflict/replay/persistence flows.

Overall acceptance requires a two‑user manual demo of realtime label updates, a forced conflict resolution flow, and a restart test that preserves labels under writable workspace conditions.


## Idempotence and Recovery


All write requests are idempotent via `Idempotency-Key`, so retries are safe and do not double‑apply. The JSONL log plus snapshot allows recovery after crashes; replay is deterministic and can be run repeatedly without duplication by ignoring already applied event IDs. Compaction/rotation prevents unbounded log growth, and atomic writes prevent snapshot corruption. When `--no-write` is enabled, the system remains in‑memory only and the UI must present a persistence warning banner. The system assumes a single worker process; multi‑worker runs must warn or be blocked because in‑memory authoritative state cannot be shared safely.


## Artifacts and Notes


SSE event example (no code fences):

    event: item-updated
    id: 128
    data: {"path":"/animals/cat.jpg","version":12,"tags":["cute"],"notes":"golden hour","star":4,"updated_at":"2026-01-23T19:22:05Z","updated_by":"web"}

PATCH payload example:

    {"base_version":12,"set_star":4,"set_notes":"golden hour","add_tags":["cute"],"remove_tags":["blurry"]}

Workspace persistence files:

    .lenslet/labels.log.jsonl
    .lenslet/labels.snapshot.json


## Interfaces and Dependencies


Backend interfaces include `PATCH /item?path=...` with `If-Match` and `Idempotency-Key` headers and patch payload, `PUT /item?path=...` for full replace compatibility, `GET /events` for SSE with `Last-Event-ID` support, `POST /presence` heartbeat for per‑gallery counts, and `GET /health` (or equivalent) to expose persistence status for the UI banner.

Frontend dependencies include a native `EventSource` SSE client, React Query cache updates on event arrival, LocalStorage‑persisted `client_id` generation for idempotency keys, and connection state tracking to drive UI (live/reconnecting/offline) and polling fallback.


## Sprint 1 Handover Notes (2026-01-23)

**What shipped (backend):**
- Canonical path helper now normalizes all paths to leading `/` with no trailing slash; server responses always return canonical paths.
- Sidecar metadata includes `version`, `updated_at`, `updated_by`; version increments on successful updates.
- `PATCH /item` implemented with patch semantics, requires `Idempotency-Key` and `base_version` (or `If-Match`); conflicts return 409 with the latest sidecar.
- `GET /events` SSE endpoint implemented with event IDs and in‑memory replay buffer; supports `Last-Event-ID`.
- Write‑behind durability: `.lenslet/labels.log.jsonl` append log + `.lenslet/labels.snapshot.json` snapshot; startup loads snapshot then replays log.
- `/health` now surfaces persistence status under `labels`.
- Single‑worker guardrail: CLI warns if `UVICORN_WORKERS` or `WEB_CONCURRENCY` > 1.

**Files touched (backend):**
- `src/lenslet/server.py` (canonicalization, PATCH, SSE, persistence wiring)
- `src/lenslet/workspace.py` (labels log/snapshot helpers)
- `src/lenslet/storage/*.py` (metadata defaults + canonical keys)
- `src/lenslet/cli.py` (single‑worker warning)
- `docs/20260123_collaboration_sync_api.md` (new API contract)

**Frontend type alignment:**
- Added `frontend/src/lib/types.ts` (Sidecar now includes `version`, `updated_*`).
- Updated `frontend/src/api/items.ts` and `frontend/src/features/inspector/Inspector.tsx` to include `version` in base sidecar model.

**Manual verification (Sprint 1):**
- Two SSE clients received `item-updated` events for a `PATCH /item`.
- Restarting the server preserved labels (verified via `GET /item`).
- Persistence files created under `.lenslet/`.

**Tests run (2026-01-23):**
- `pytest -q` after `pip install -e . -e ".[dev]"`.
- Failures are **unrelated to Sprint 1** changes and pre‑existing behavior expectations:
  - `test_api_simple.py::test_blocking_mode` and `tests/test_programmatic_api.py::test_blocking_mode` expect a narrower `lenslet.launch` signature (repo currently exposes `show_source`, `source_column`, `base_dir`).
  - `tests/test_metadata_endpoint.py::test_metadata_endpoint_rejects_non_png` expects `/metadata` to return 415 for JPEG; server currently allows JPEG/WebP/PNG.
  - Dep warning: `platformio` expects `starlette<0.47`; dev install pulled `starlette 0.50.0` via `fastapi`.

**Sprint 2 implementer checklist (what to know from Sprint 1):**
- Use `PATCH /item` for partial edits; **must** send `Idempotency-Key` and `base_version` or `If-Match`.
- Event payloads from SSE are canonical path + `version/tags/notes/star/updated_at/updated_by` (plus `metrics` when present).
- Canonical paths are enforced across storage and APIs; client should treat responses as source of truth.
- Persistence only when workspace is writable; check `/health.labels.enabled` for UI banner.
- SSE replay requires `Last-Event-ID` on reconnect.


When revising the plan, add a note at the bottom describing the change and why it was made.

Plan updated on 2026-01-23 to incorporate review_notes.txt feedback (task splitting, persistence banner, compaction, single-worker guardrail, and additional tests).

Plan updated on 2026-01-23 to record Sprint 1 implementation status, test failures (unrelated), and handover notes for Sprint 2.
