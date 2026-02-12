# Collaboration Sync Ops Notes (Sprint 4)

## Core Operating Constraints

- **Single worker only.** Presence and SSE replay state are in-memory per process. Run with `UVICORN_WORKERS=1` and `WEB_CONCURRENCY=1`.
- **SSE replay is bounded.** Replay uses an in-memory ring buffer; older events may be unavailable after churn.
- **Presence is ephemeral.** Presence is not persisted to disk; stale entries converge by TTL + prune interval.

## Presence Tuning Knobs

- `presence_view_ttl` (default `75s`)
- `presence_edit_ttl` (default `60s`)
- `presence_prune_interval` (default `5s`)
- CLI rollout gate: `--presence-lifecycle-v2` (default) / `--no-presence-lifecycle-v2`

Convergence targets:
- explicit `move/leave`: `<= 5s`
- crash/no-leave: `<= (view_ttl + prune_interval + 5s)`

## Observability Endpoints

- `GET /presence/diagnostics` returns:
  - `active_clients`
  - `active_scopes`
  - `stale_pruned_total`
  - `invalid_lease_total`
  - `replay_miss_total`
  - replay window diagnostics (`replay_buffer_size`, `replay_buffer_capacity`, `replay_oldest_event_id`, `replay_newest_event_id`)
  - `connected_sse_clients`
- `GET /health` includes a `presence` object with the same key counters and `lifecycle_v2_enabled`.

## Rollout / Rollback Runbook

### Rollout (lifecycle-v2 enabled)

1. Start Lenslet with default behavior or explicit flag:
   - `lenslet /path/to/images --presence-lifecycle-v2`
2. Restart expectation:
   - Changing lifecycle mode requires a process restart.
3. Smoke checks:
   - `POST /presence/join` returns `lease_id`.
   - `POST /presence/move` enforces lease/scope semantics.
   - `GET /presence/diagnostics` shows `lifecycle_v2_enabled: true`.

### Rollback (legacy heartbeat semantics)

1. Restart Lenslet with legacy gate:
   - `lenslet /path/to/images --no-presence-lifecycle-v2`
2. Restart expectation:
   - Existing leases are process-local and reset after restart.
3. Post-rollback smoke checks:
   - `GET /presence/diagnostics` reports `lifecycle_v2_enabled: false`.
   - `POST /presence/join` still returns canonical presence payload + `lease_id`.
   - `POST /presence/move` responds successfully via heartbeat-style convergence.
   - `POST /presence/leave` returns `removed: false` and `mode: "legacy_heartbeat"`.
   - SSE `item-updated` and `metrics-updated` streams remain live.

## Manual QA Checklist

1. **Two-client realtime update**
   - Open two browsers on the same gallery.
   - Edit tags/stars/notes in client A; verify client B updates without refresh.
2. **Presence refresh + move convergence**
   - Join two tabs, refresh one tab, move the other to a new folder.
   - Verify counts converge to expected values within bounds.
3. **Crash/no-leave prune**
   - Close one tab without clean leave and wait past configured TTL + prune interval.
   - Verify stale count is removed and `stale_pruned_total` increases.
4. **Invalid lease signal**
   - Send one request with an invalid lease.
   - Verify `invalid_lease_total` increments in diagnostics.
5. **Replay miss signal**
   - Force replay from an event id older than the current replay window.
   - Verify `replay_miss_total` increments.
6. **Rollback mode smoke**
   - Restart with `--no-presence-lifecycle-v2` and verify rollback checks above.
