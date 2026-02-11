# S2 / T8: Presence and Sync No-op Fast Paths

Timestamp: 2026-02-11T05:15:47Z

## Goal

Reduce incidental overhead in presence prune/publish and sync replay paths without changing lifecycle semantics or event payload contracts.

## Changes

1. `src/lenslet/server_routes_presence.py`
   - Added a no-op guard in `publish_presence_deltas(...)`:
     - return immediately when `previous == current`.
   - This skips set-union/sort/delta iteration when prune snapshots are unchanged.

2. `src/lenslet/server_sync.py`
   - Optimized `EventBroker.replay(...)` for no-new-event calls:
     - return early when replay buffer is empty;
     - return early when `last_id >= newest_event_id`.
   - Preserved replay-miss accounting when callers are behind the oldest buffered event.

3. `src/lenslet/server_sync.py`
   - Reduced temporary allocations in `PresenceTracker` internals:
     - `_prune_stale_locked(...)` now gathers stale clients first, then removes them (avoids copying all sessions each call);
     - `_counts_locked(...)` removes stale scope members during a single tuple-backed pass (drops extra stale-members list + second pass).

4. `tests/test_presence_lifecycle.py`
   - Added `test_event_broker_replay_latest_event_returns_empty_without_replay_miss` to lock replay semantics for the new fast path.

## Validation

- `pytest -q tests/test_presence_lifecycle.py tests/test_collaboration_sync.py tests/test_hotpath_sprint_s4.py tests/test_import_contract.py`
  - Result: `25 passed in 1.90s`.
- `pytest -q --durations=10 tests/test_presence_lifecycle.py tests/test_collaboration_sync.py`
  - Result: `13 passed in 1.70s`.
- Import-contract probe script
  - Result: `import-contract-ok`.

## Notes

The main gain is algorithmic: no-op replay and no-op prune-delta cycles now avoid avoidable O(n) scanning/allocation work while preserving emitted events and diagnostics semantics.
