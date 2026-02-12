## Quick critique of your draft answers

### 1) “Write‑behind is not optional; it’s a must”

I agree with the intent (labels can’t be ephemeral), but I’d phrase it as:

- **Persistence is part of the MVP when `workspace.can_write == True`.**
- If `--no-write` (or `can_write=False`), collaboration can still work **in-memory**, but the UI must clearly warn **“labels won’t survive restart”**.

That gives a clean rule: *collab always works, persistence is best-effort when allowed, and the user can explicitly opt out.*

Also: in this repo, writing “a little” is already accepted (views/thumb cache/og cache), so label persistence won’t feel philosophically inconsistent anymore.

### 2) “SSE only? not sure”

SSE-only is totally viable **if you design for disconnections**. The big mistake is “SSE only, assume it’s always connected.” In practice you need:

- heartbeat/keepalive
- reconnect behavior
- a catch-up strategy (even if crude)

You can keep it lean without adding polling, but you can’t skip the reconnect/catch-up thinking.

### 3) Presence: “counts only, hover shows editing vs viewing; editing = at least one change made”

Counts-only is good and lean. But defining “editing” as “ever edited since page load” will make the UI misleading (someone edits once, then is forever “editing”).

Better definition (still simple):

- **editing = has sent an edit heartbeat recently OR has made a write in the last N seconds**
    (N=30–60s is plenty)

This makes presence feel “alive” instead of sticky.

### 4) Metrics: “not sure, I want a working system”

Given your codebase *today*, metrics aren’t an async job system; they’re mostly:

- precomputed columns loaded into `TableStorage` / `ParquetStorage` (`CachedItem.metrics`)
- not something computed by the server

So if you want a “working system when done,” don’t let metrics balloon the scope. You can include:

- “events can carry metrics updates” (plumbing)
- but **do not implement job creation/progress unless you already have a worker**

### 5) Conflict: “maybe don’t even have user choice; just drop the change?”

Dropping is the worst UX option: it guarantees confusion and silent data loss.

Lean options that don’t suck:

- **Option A (leanest): last-write-wins, no 409 at all**
    (acceptable if collisions are rare and you mainly want “see each other’s changes”)
- **Option B (still lean): 409 + auto-retry for safe operations, manual for unsafe**
    - safe: tag add/remove, star set
    - unsafe: free-text notes (manual choice)

Your original plan already assumes “collaboration,” which implies at least *some* conflict handling. So I’d steer you toward Option B.

### 6) Gallery identity: “what’s gallery_id used for?”

This is important to answer explicitly because it drives what you build:

- `gallery_id` is only needed to **aggregate presence and progress events** into a group.
- It’s basically “which shared space are we counting people in?”

If presence is only shown at the dataset level, `gallery_id` can just be the dataset identity.
If presence is shown per-folder/path scope, `gallery_id` can be the normalized folder path.

### 7) UI: “sufficient”

Mostly yes. The one thing I’d add is a connection/persistence truth signal:

- **Live / Reconnecting / Offline**
- **Persisted / Not persisted (no-write)**

That prevents tons of confusion during demos.

------

## Recommended answers to implementer questions (with lean implementation guidance)

### 1) Scope: in-memory only vs include write‑behind?

**Answer:** Include write-behind as part of the MVP *when `workspace.can_write` is true*.

**Why (in this repo):**

- Your storage backends are explicitly in-memory for labels today (`_metadata` dict everywhere).
- Without write-behind you’ll “successfully ship collaboration” and then lose all labels on restart. That will dominate perception of quality.

**Lean way to do it:**

- Persist *only the labeled subset*, not all images.
- Use **one JSON file** + atomic replace (same pattern as `views.json`).

Suggested file locations consistent with existing workspace patterns:

- Directory dataset mode: `.lenslet/labels.json`
- Parquet sidecar mode: `<parquet>.cache/labels.json` (parallel to thumbs/og-cache)

Suggested schema (small, future-proof):

```json
{
  "version": 1,
  "saved_at": "2026-01-23T19:25:15Z",
  "items": {
    "animals/cat.jpg": {
      "tags": ["cute"],
      "notes": "golden hour",
      "star": 4,
      "updated_at": "2026-01-23T19:22:05Z",
      "updated_by": "client:abc",
      "item_version": 12
    }
  }
}
```

Flush policy:

- time-based (e.g., every 10–30s) **and** dirty-count threshold (e.g., 25 updates)
- flush on shutdown (best effort)

That’s not much code, and it prevents catastrophic loss.

------

### 2) Transport: SSE only (no polling fallback)?

**Answer:** SSE as the primary mechanism is fine **if you include a reconnect + catch-up strategy**.

To keep it lean, I’d do SSE-only plus **one** of these catch-up strategies:

**Leanest catch-up:** on SSE reconnect, frontend refetches:

- current folder index (`GET /folders?path=...`)
- and the currently selected item sidecar (`GET /item?path=...`)

This is “dumb but effective.”

**Slightly better (still small):** add an event id + ring buffer replay:

- server assigns monotonically increasing `event_id`
- keep last N events in memory (e.g., N=1000)
- if client connects with `Last-Event-ID`, replay those events

That avoids missing updates during brief disconnects and still doesn’t require polling or a DB.

Also: **add heartbeat pings** on SSE every ~15s to keep proxies from killing the connection.

------

### 3) Presence: per-gallery counts only vs editing vs viewing?

**Answer:** Per-gallery counts + editing vs viewing is worth it and still lean.

Implementation I’d recommend:

- `/presence` heartbeat: `{gallery_id, client_id, status}`
- server stores: `last_seen`, `status`, `last_edit_at`
- status can be:
    - `"viewing"`
    - `"editing"` (or `"viewing"` + a derived `editing_recently`)

Define “editing” as:

- either explicit status `"editing"`, or
- `now - last_edit_at < 60s`

UI hover can show breakdown:

- `3 online` hover → `1 editing · 2 viewing`

This is minimal state, no user accounts, no names.

------

### 4) Metrics: include async job API or only event ingestion path?

**Answer:** **Only event ingestion / propagation path** for now.

Concretely:

- define `metrics-updated` event type and client handling
- maybe add a server internal method to “apply metrics update” to the in-memory item model if you ever have a worker
- do **not** implement job creation/progress APIs unless you already have a metrics worker pipeline

Reason: your current backend doesn’t compute metrics; it mostly *serves* metrics.

------

### 5) Conflict handling: auto rebase+retry or manual choice?

**Answer:** Hybrid: auto for safe operations, manual for notes.

- **Auto-retry** for:
    - tag add/remove (or set tags if you treat them as a set operation)
    - star set
- **Manual conflict UI** for:
    - notes (free text)

Why this is the best “lean but not awful” approach:

- Users will hit conflicts mostly when quickly toggling tags/stars—auto makes the system feel smooth.
- Notes conflicts can actually lose meaningful content; forcing a manual choice avoids silent clobber.

If you really want *maximum* simplicity, then drop 409 entirely and go last-write-wins. But I wouldn’t combine “409 exists” with “we drop your change.”

------

### 6) Gallery identity: what should `gallery_id` be?

**Answer:** Make it the **normalized folder path** (plus optionally dataset label).

You already have a good normalizer in `lenslet/og.py`:

- `og.normalize_path(path)` enforces leading `/` and removes trailing `/`.

So:

- if presence is per-folder: `gallery_id = og.normalize_path(current_folder_path)`
- if presence is dataset-level only: `gallery_id = "root"` or `gallery_id = _dataset_label(workspace)`

I’d pick **folder path** because it costs nothing and gives more accurate presence.

------

### 7) Frontend UI: is current set sufficient?

**Answer:** Yes, with two tiny additions that prevent confusion:

1. **Connection state** (SSE): `Live` / `Reconnecting…` / `Offline`
2. **Persistence state**: `Saved to disk` vs `Session-only (no-write)`

Everything else you listed is plenty for MVP.

------

## Very specific implementation critiques for *this* backend

These are the “gotchas” I’d warn the implementer about:

1. **`GET /item` is currently lying**
    `_build_sidecar()` always returns `updated_at = now()` and `updated_by="server"`.
    That breaks every sync strategy (can’t reason about recency).
2. **Path normalization differs across storage backends**
    - `TableStorage` normalizes keys (`_normalize_item_path`)
    - `MemoryStorage` does not normalize metadata keys
        If you store sidecars on disk keyed by path, be consistent about the exact path string you use (ideally whatever the frontend uses).
3. **Threading model matters for SSE**
    Most endpoints are sync (FastAPI runs them in a threadpool).
    If SSE broadcast uses `asyncio.Queue`, you need `loop.call_soon_threadsafe(...)` or you’ll hit cross-thread issues.
4. **Don’t persist width/height**
    Those are already handled elsewhere (and parquet caching exists). Keep labels persistence minimal.

------

## Concrete additions that would improve the plan (low complexity, high payoff)

Here are “plan upgrades” that are genuinely worth adding and still keep the repo lean:

### A) Add ETag/If-Match compatibility (even if you keep `version` in JSON)

- Response: `ETag: "12"`
- Request: `If-Match: "12"`
- Still include `version: 12` in the JSON body for convenience.

This makes the API feel standard and plays nicely with caching/proxies later.

### B) SSE keepalive + disconnect detection

- Server sends `: ping\n\n` every 15s
- Client uses that to show `Live` vs `Reconnecting`

This prevents “it works locally but dies in prod” problems.

### C) Ring buffer replay with `Last-Event-ID`

Keep last N events in memory and replay on reconnect. It’s a small amount of code and drastically reduces “missed updates.”

### D) Explicit “dirty flush” state in `/health`

Add fields like:

- `collab_enabled`
- `pending_label_flush_count`
- `last_label_flush_at`
- `sse_clients`

This is invaluable for debugging without adding a whole admin UI.

### E) Persist only items that differ from defaults

Store only entries where:

- tags non-empty OR notes non-empty OR star not null (and later metrics if needed)

That keeps `labels.json` small even for huge datasets.

### F) Shutdown flush hook

If you already have a background flush timer, also flush on shutdown. This reduces “I labeled 50 images and then Ctrl-C’d” data loss.

### G) Define “editing” as a derived property from writes

Instead of trusting the client to say “I’m editing,” you can derive:

- `last_edit_at` updated on `PUT /item`
- editing = recent write
    Client heartbeat still needed for “viewing” count.

That’s actually *less* code than complicated client state.

------

## What I’d tell the implementer as a crisp directive

If you want something you can ship confidently with minimal bloat:

- **SSE + versioning + idempotency + write-behind snapshot**
- **409 conflicts + auto-retry for tags/stars, manual for notes**
- **presence counts with “editing = recent write”**
- **SSE ping + reconnect refetch (or ring buffer replay)**

That’s “collaboration that feels real,” without introducing databases, auth, or heavy frameworks.