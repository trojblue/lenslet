# Lenslet Manual Refresh Plan (2025-11-30)

## Goal
Add a manual “Refresh” action so a user can right-click a folder in the UI and reload that folder and its descendants, updating file lists, item counts, and thumbnails without restarting the server. This replaces the earlier watcher idea for now.

## Scope
- Applies to CLI/memory mode. Programmatic datasets mode remains static unless extended later.
- No filesystem watcher, no toast notifications. Keep UX simple and predictable.

## Backend
- Add `invalidate_subtree(path: str)` to `MemoryStorage`:
  - Remove `_indexes` entries whose path matches or is under the target path.
  - Purge `_thumbnails`, `_metadata`, `_dimensions` for items whose paths start with that prefix.
  - Next `/folders`/`/thumb` calls rebuild lazily, so item counts and listings stay accurate.
- Add `POST /refresh?path=...`:
  - In memory/CLI mode: call `invalidate_subtree` and return `{ ok: true }`.
  - In dataset mode: respond `{ ok: true, note: "dataset mode is static" }` (no-op) to keep semantics explicit.

## Frontend
- Extend API client with `refreshFolder(path)` (POST /refresh).
- Folder tree context menu: prepend a “Refresh” item when right-clicking a folder.
  - While running: label shows “Refreshing…” and item is disabled.
  - On success: invalidate react-query folder caches whose key path starts with the target; if the current folder is inside that subtree, call `refetch()` so the grid updates. Optionally clear blob/thumb caches for matching paths to avoid stale thumbnails.
- No toast; rely on silent success. Errors can log to console for now.

## Testing
- Backend unit: `invalidate_subtree` removes index + per-item caches; subsequent `get_index` rebuilds.
- Backend API: create temp dir, fetch `/folders`, add/remove a file, call `/refresh`, then ensure `/folders` reflects the change.
- Frontend unit: context-menu handler issues `refreshFolder`, disables item during request, and triggers react-query invalidation for subtree keys.

## Future (if we revisit watching later)
- The same `invalidate_subtree` can be driven by a watcher or pushed to the UI via WebSocket, but that’s out of scope for this step.
