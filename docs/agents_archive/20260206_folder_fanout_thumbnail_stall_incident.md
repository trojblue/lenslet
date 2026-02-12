# Folder Fanout Thumbnail Stall Incident (2026-02-06)

## Summary

When Lenslet was pointed at a dataset shaped as:

- thousands of subfolders (each subfolder is a task)
- a small number of images per subfolder

the app appeared stuck on load, thumbnails showed up late, and initial navigation was slow.

## Observations

- Initial folder loading was delayed most in roots with very high subfolder fanout.
- Thumbnails often started appearing only after folder counting/index work settled.
- Folder tree and app shell were issuing expensive recursive folder requests that amplified startup cost.

## Root Causes

### Backend

- `MemoryStorage` triggered expensive leaf-batch preparation (`LeafBatchTracker.maybe_prepare`) for high-fanout directories. That path probes child folders and added heavy synchronous overhead before useful results were returned.
- Local directory listing used `os.listdir` + per-entry `os.path.isdir`, which is slower than `os.scandir` for large directories.
- Index builds for tiny folders still paid thread-pool and progress bookkeeping overhead that outweighed useful work.

### Frontend

- `FolderTree` eagerly computed subtree counts by recursively walking folder APIs, causing large request fanout.
- `TreeNode` fetched folder data for all rendered nodes, not only active/expanded nodes.
- `AppShell` did additional recursive count fetches (`/folders?recursive=1`) for scope/root totals even when equivalent data was already in query cache.

## Fixes Implemented

### Backend fixes

- Switched local directory listing to `os.scandir` in `src/lenslet/storage/local.py`.
- Added high-fanout guard in `src/lenslet/storage/memory.py`:
  - skip leaf-batch probing when directory count exceeds `LEAF_BATCH_MAX_DIRS`.
- Added small-folder heuristics in `src/lenslet/storage/memory.py`:
  - avoid parallel worker setup below `LOCAL_INDEX_PARALLEL_MIN_IMAGES`.
  - avoid progress updates below `LOCAL_PROGRESS_MIN_IMAGES`.
- Added regression tests in `tests/test_memory_index_performance.py`:
  - verifies high-fanout roots skip leaf-batch probe.
  - verifies tiny folder indexes avoid parallel worker setup.

### Frontend fixes

- Added optional `enabled` flag to folder query hook in `frontend/src/api/folders.ts`.
- Made `TreeNode` folder requests lazy in `frontend/src/features/folders/FolderTree.tsx`:
  - fetch only for root, expanded, or active nodes.
- Reduced subtree count pressure in `FolderTree`:
  - count recursively only when needed (expanded/active context).
  - reuse cached recursive query data before issuing network calls.
- Removed duplicate recursive count fetch logic from `frontend/src/app/AppShell.tsx`:
  - derive scope/root totals from already loaded folder data and cache instead of always re-fetching recursively.

## Validation

- Backend and frontend builds/tests passed after changes:
  - `pytest -q` -> 26 passed (existing unrelated warnings unchanged).
  - `cd frontend && npm run build` -> success.
- Synthetic sanity checks on high-fanout layout showed much faster root folder response and materially lower recursive-load latency.

## Outcome

The startup path is now less sensitive to directory fanout and avoids multiple redundant recursive traversals. In high-fanout task-folder datasets, initial folder render and thumbnail appearance are significantly more responsive.
