# Collaboration Sync Ops Notes (Sprint 3)

## Operational Notes

- **Single worker only.** In-memory sync state is not shared across workers. Multiple workers must be avoided.
- **SSE replay across reload.** Clients store the last seen event id and reconnect to `/events?last_event_id=...`.
- **Keepalive pings.** The SSE stream sends periodic `: ping` comments to keep idle connections open.
- **Polling fallback.** If SSE cannot reconnect after backoff, the UI polls folder/search/sidecar data every ~10-20s and stops polling once SSE is live.
- **Durability.** When workspace is writable, updates append to `.lenslet/labels.log.jsonl` and snapshots are written to `.lenslet/labels.snapshot.json`.
- **Compaction.** After a snapshot, logs are compacted when they exceed ~5MB (atomic rewrite).
- **Ephemeral mode.** When `--no-write` or workspace is read-only, labels remain in memory only and are not persisted.

## Known Limits

- Presence is best-effort and TTL-based; it is not persisted or replayed.
- SSE replay buffer is in-memory and bounded (recent events only).
- Fallback polling is best-effort; very large galleries may still need manual refresh after long offline windows.

## Manual QA Checklist

1. **Two-client realtime update**
   - Open two browsers on the same gallery.
   - Edit tags/stars/notes in client A; verify client B updates without refresh.
2. **Conflict flow**
   - Edit the same item in both clients with stale version.
   - Confirm conflict banner appears and both actions resolve correctly.
3. **Replay on reload**
   - While client B is open, update an item in client A.
   - Reload client B; confirm the update appears immediately (replay).
4. **SSE offline + polling fallback**
   - Stop the server or block `/events`.
   - Confirm connection status shows Offline and polling refreshes the current view.
   - Restore the server; confirm SSE returns to Live and polling stops.
5. **Persistence**
   - Make updates, restart the server, and verify labels persist.
6. **No-write warning**
   - Run with `--no-write` and confirm the UI banner indicates labels are ephemeral.
