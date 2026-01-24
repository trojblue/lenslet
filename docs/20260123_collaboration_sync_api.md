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

### `GET /health`
Includes persistence status for sync durability:

```json
{
  "labels": {
    "enabled": true,
    "log": "/path/to/.lenslet/labels.log.jsonl",
    "snapshot": "/path/to/.lenslet/labels.snapshot.json"
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
