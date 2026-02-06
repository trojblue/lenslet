# Collaboration Sync API (Sprint 1)

This document defines the backend contract for realtime metadata sync and durability.

## Path Canonicalization

All item and folder paths are normalized to a canonical form:

- leading `/`
- no trailing slash (except `/`)
- multiple slashes collapsed

Clients should treat server responses as canonical, and use those paths for future calls.

## Sidecar Schema

`Sidecar` is returned by `GET /item` and as the response for metadata writes.

```json
{
  "v": 1,
  "tags": ["cute"],
  "notes": "golden hour",
  "exif": {"width": 1024, "height": 768},
  "star": 4,
  "version": 12,
  "updated_at": "2026-01-23T19:22:05Z",
  "updated_by": "web"
}
```

Notes:
- `version` is the optimistic concurrency counter (increments on each accepted update).
- `updated_at` and `updated_by` reflect the last write, not the request time.
- `updated_by` uses `x-updated-by` when provided, otherwise falls back to `x-client-id`.

## Endpoints

### `GET /item?path=...`
Returns a `Sidecar` for the given path.

### `PUT /item?path=...`
Full replace of tags/notes/star.

- No optimistic concurrency check.
- Increments `version`.

### `PATCH /item?path=...`
Patch semantics with optimistic concurrency.

Headers:
- `Idempotency-Key` **required**
- `If-Match` (optional) — integer version

Request body:

```json
{
  "base_version": 12,
  "set_star": 4,
  "set_notes": "golden hour",
  "set_tags": ["cute", "warm"],
  "add_tags": ["portrait"],
  "remove_tags": ["blurry"]
}
```

Rules:
- If `If-Match` is present, it must match `base_version` if both are provided.
- Either `base_version` or `If-Match` is required.
- If the expected version does not match the current `version`, the server returns 409.
- `Idempotency-Key` ensures retries return the same response without double-applying.

Conflict response (409):

```json
{
  "error": "version_conflict",
  "current": { /* latest Sidecar */ }
}
```

### `GET /events`
Server-Sent Events stream for realtime updates.

- Reconnect replay uses `Last-Event-ID` header or `last_event_id` query param.
- Server emits periodic `: ping` keepalive comments to keep idle connections alive.
- Events are buffered in-memory; only recent IDs can be replayed.

Event examples:

```
event: item-updated
id: 128
data: {"path":"/animals/cat.jpg","version":12,"tags":["cute"],"notes":"golden hour","star":4,"updated_at":"2026-01-23T19:22:05Z","updated_by":"web"}
```

```
event: metrics-updated
id: 129
data: {"path":"/animals/cat.jpg","version":13,"metrics":{"score":0.91},"updated_at":"2026-01-23T19:22:08Z","updated_by":"server"}
```

```
event: presence
id: 130
data: {"gallery_id":"/animals","viewing":2,"editing":1}
```

## Presence Lifecycle (v2)

Presence is tracked as **one active scope per client session**.
The server issues a `lease_id` at join time; `move` and `leave` must provide that lease.
The mode can be rolled back at startup with `--no-presence-lifecycle-v2`.

SSE `presence` event payload shape:

```json
{
  "gallery_id": "/animals",
  "viewing": 2,
  "editing": 1
}
```

HTTP lifecycle response payload shape (`join` and legacy heartbeat):

```json
{
  "gallery_id": "/animals",
  "client_id": "tab-abc",
  "lease_id": "8f2f6d7f3f0a4eb09f0d39c74ce39f3a",
  "viewing": 2,
  "editing": 1
}
```

### `POST /presence/join`

Request:

```json
{
  "gallery_id": "/animals",
  "client_id": "tab-abc",
  "lease_id": "optional-existing-lease"
}
```

Behavior:
- creates or refreshes a session in `gallery_id`
- returns canonical counts + active `lease_id`
- when `lease_id` matches current lease, the call is idempotent

### `POST /presence/move`

Request:

```json
{
  "from_gallery_id": "/animals",
  "to_gallery_id": "/animals/cats",
  "client_id": "tab-abc",
  "lease_id": "8f2f6d7f3f0a4eb09f0d39c74ce39f3a"
}
```

Response:

```json
{
  "client_id": "tab-abc",
  "lease_id": "8f2f6d7f3f0a4eb09f0d39c74ce39f3a",
  "from_scope": {"gallery_id": "/animals", "viewing": 1, "editing": 0},
  "to_scope": {"gallery_id": "/animals/cats", "viewing": 2, "editing": 0}
}
```

### `POST /presence/leave`

Request:

```json
{
  "gallery_id": "/animals/cats",
  "client_id": "tab-abc",
  "lease_id": "8f2f6d7f3f0a4eb09f0d39c74ce39f3a"
}
```

Response includes `removed` (`true` on first leave, `false` on idempotent replay).

### Legacy `POST /presence` (compatibility)

Legacy heartbeat remains supported and now routes through the lifecycle model.

Request:

```json
{
  "gallery_id": "/animals",
  "client_id": "tab-abc",
  "lease_id": "optional"
}
```

Response uses the same normalized presence payload shape and always includes server `lease_id`.

### Lifecycle Gate Behavior

When lifecycle-v2 is disabled (`--no-presence-lifecycle-v2`):

- `POST /presence/join` uses heartbeat semantics (`touch_view`) to keep clients online.
- `POST /presence/move` degrades to destination heartbeat semantics (best-effort from/to scope counts).
- `POST /presence/leave` returns `removed: false` with `mode: "legacy_heartbeat"` (TTL/prune convergence path).

### Presence Errors

- `409 {"error":"invalid_lease", ...}` for stale/forged leases
- `409 {"error":"scope_mismatch", ...}` when `move/leave` scope disagrees with active scope

### Stale Cleanup

- stale sessions are pruned periodically even when a scope is idle
- defaults: `view_ttl=75s`, `edit_ttl=60s`, prune interval `5s`
- each prune publishes corrected `presence` events for affected scopes

Convergence bounds:
- explicit `move/leave` convergence target: `<= 5s` from request completion to corrected presence payloads
- crash/no-leave convergence target: `<= (view_ttl + prune_interval + 5s)` at configured defaults

### `GET /presence/diagnostics`

Debug-safe runtime counters:

```json
{
  "lifecycle_v2_enabled": true,
  "view_ttl_seconds": 75.0,
  "edit_ttl_seconds": 60.0,
  "prune_interval_seconds": 5.0,
  "active_clients": 2,
  "active_scopes": 2,
  "stale_pruned_total": 14,
  "invalid_lease_total": 3,
  "replay_miss_total": 1,
  "replay_buffer_size": 500,
  "replay_buffer_capacity": 500,
  "replay_oldest_event_id": 221,
  "replay_newest_event_id": 720,
  "connected_sse_clients": 2
}
```

### `GET /health`
Includes persistence status and presence diagnostics:

```json
{
  "ok": true,
  "mode": "memory",
  "labels": {
    "enabled": true,
    "log": "/path/to/.lenslet/labels.log.jsonl",
    "snapshot": "/path/to/.lenslet/labels.snapshot.json"
  },
  "presence": {
    "lifecycle_v2_enabled": true,
    "active_clients": 2,
    "active_scopes": 2,
    "stale_pruned_total": 14,
    "invalid_lease_total": 3,
    "replay_miss_total": 1
  }
}
```

## Durability

When the workspace is writable, accepted updates are appended to:

- `.lenslet/labels.log.jsonl`

Periodic snapshots are written to:

- `.lenslet/labels.snapshot.json`

On startup the server loads the snapshot, then replays log entries.
Snapshots are written atomically, and the log is compacted after snapshots when it exceeds a size threshold (~5MB).

If `--no-write` is used, the server stays in-memory only and does not write logs or snapshots.
