Here are my critiques + lean implementation suggestions, mapped to the implementer’s questions, and then a few concrete “add this to the plan” items that will save you pain later.

------

## First: a couple of high‑leverage critiques of the current plan vs the actual code

### 1) **Path canonicalization is currently inconsistent**

In `MemoryStorage`, `get_metadata()` / `set_metadata()` store keys exactly as passed (`"animals/cat.jpg"` vs `"/animals/cat.jpg"` can become two different entries). Other storages normalize.

If you add versioning + persistence + SSE, **a single canonical item key becomes mandatory** or you’ll get:

- “conflicts” that aren’t real conflicts
- duplicate state
- missing updates on some clients

**Lean fix:** introduce one canonicalization function in the server layer (or a required method on storages) and *always* use it for:

- metadata map keys
- version checks
- SSE payload `path`
- persistence keys

### 2) Your current `PUT /item` shape is “full replace by accident”

`Sidecar` has defaults (`tags=[]`, `notes=""`). If the client sends only `star`, you’ll wipe tags/notes unless you treat it as a patch.

Even if the frontend currently sends the full object, collaboration will introduce retries/rebases where partials can happen.

**Lean fix:** either:

- make `PUT /item` explicitly **patch semantics** (recommended), or
- add a `PATCH /item` and keep `PUT` as full replace

Patch semantics also reduces conflict pain.

------

## Now, answers to the implementer’s 7 questions (with recommendations)

### 1) Scope: in‑memory only vs write‑behind persistence?

**Recommendation:** **Persistence must be part of the MVP** *when workspace is writable*.
If `--no-write` or workspace isn’t available, run in “ephemeral collaboration” mode with a prominent banner.

But I’d push back on “every few minutes is fine.” In practice, losing 2–5 minutes of labeling due to a crash feels awful.

**Lean persistence approach (pick one):**

**Option A (very lean, no new deps): JSONL event log + occasional compaction**

- Append each accepted update as a single line in: `.lenslet/labels.log.jsonl`
- Periodically write a compact snapshot to: `.lenslet/labels.snapshot.json`
- On startup: load snapshot → replay log
- This is easy to reason about and avoids rewriting a huge JSON map frequently.

**Option B (also lean, arguably less wheel‑reinventing): SQLite (stdlib)**

- Store sidecars by `path` in a sqlite file in `.lenslet/labels.sqlite`
- Atomic writes, no custom compaction logic, scales better
- Still “a file”, but not “running a DB”

If you strongly want “no DB”, Option A is the sweet spot.

**Key policy to state in the plan:**

- Memory is authoritative for realtime.
- Disk is durability (write‑behind).
- Flush interval should be **seconds**, not minutes (e.g., 1–10s or every N updates).

------

### 2) Transport: SSE only (no polling fallback)?

**Recommendation:** **SSE as primary + minimal fallback** (cheap insurance).

SSE is great here: one-way server→client, simple, works with FastAPI.

But in real environments SSE can drop (proxy buffering, laptop sleep, flaky wifi). A fallback can be extremely small:

- If SSE disconnects and can’t reconnect after backoff → enable polling every ~10–30s (or refetch on focus), and turn it off once SSE is healthy again.

This keeps the codebase lean because:

- Backend doesn’t change for fallback.
- Frontend change is small (a “connection state” + a refetch interval toggle).

**Also add to plan:** support `Last-Event-ID` and event IDs (details below). That makes reconnect correct without polling most of the time.

------

### 3) Presence: per‑gallery counts only, or viewing vs editing counts?

**Recommendation:** **Counts only is enough**, but include **viewing vs editing** because it’s basically free once presence exists.

I would *not* define “editing = has ever made a change” because that becomes meaningless after 2 minutes (everyone becomes “editing”).

**Better definition (still simple):**

- `editing` = user has **sent a write** in the last *N seconds* (e.g., 30s)
- `viewing` = SSE connected + currently browsing that gallery, and not “editing” by the above rule

This gives you “active editors” which is what people expect.

UX idea you already mentioned is good:

- Pill shows total: `3 here`
- Hover shows: `1 editing · 2 viewing`

------

### 4) Metrics: include async job API, or only ingestion path?

You said: “I want a working system when done.” For the *label sync* scope, a metrics job system is a rabbit hole.

**Recommendation:** **Only implement the ingestion + broadcast path now.**

- Keep event types for `metrics-updated` (future-proof)
- Allow server-side code to set metrics in the same metadata record (or a dedicated endpoint), and broadcast when it happens
- Do **not** add “create job / progress / cancel” APIs yet unless metrics computation is required for a near-term workflow

Concretely:

- Add optional `metrics` to your stored sidecar record
- Add `PUT /item/metrics` or allow `PATCH /item` with `{metrics: {...}}`
- Broadcast `metrics-updated`

That yields a “working system” without a job framework.

------

### 5) Conflict handling: auto rebase+retry vs manual choice?

Your draft: “maybe don’t even have user choice, just drop the change?”

**Strong recommendation:** **Never silently drop a user’s change.**
That will destroy trust immediately.

**Lean and safe default:**

- On `409`, show “Newer change detected” with two buttons:
    - **Apply mine again** (explicit overwrite on top of latest)
    - **Keep theirs** (discard my local edits)

That’s already in your plan and is the right balance.

**Optional improvement without much complexity:**

- Auto-merge only for **commutative operations** if you track diffs:
    - tags: add/remove operations merge well
- notes: do **not** auto-merge by default (text conflicts are messy)
- star: could be last-write-wins, but still better to surface conflict than silently override

If you want to reduce conflicts *and* keep code lean, the biggest win is:

- Make updates **patch/diff based**, not “replace the whole sidecar”

Example patch model:

```json
{
  "base_version": 12,
  "set_star": 4,
  "set_notes": "…",
  "add_tags": ["cute"],
  "remove_tags": ["blurry"]
}
```

Then even if version mismatches, the server can sometimes apply tag ops safely (depending on policy).

But if you want absolute minimal change: keep the manual resolver UI and stop there.

------

### 6) Gallery identity: what is `gallery_id` used for?

It’s only used for **presence aggregation** (and optionally “recent activity in this folder” banners).

So it doesn’t need to be fancy. It just needs to be:

- stable across clients
- consistent
- cheap

**Recommendation:** use the **normalized folder path** the user is currently viewing:

- root: `"/"`
- folder: `"/animals"`
- in dataset mode it naturally includes dataset prefix (e.g. `"/datasetA"`)

That’s enough and keeps everything simple.

If you later introduce “multiple datasets in one server instance with overlapping paths”, you can prefix with a dataset label, but you’re not there.

------

### 7) Frontend UI: is your list sufficient?

Yes — your current set is enough:

- global sync indicator
- per-item conflict badge
- recent activity banner
- presence pill

Two small additions I’d suggest because they reduce confusion a lot:

1. **Connection status** (tiny)

- `Live` / `Reconnecting…` / `Offline (polling)`
- This helps users understand why they aren’t seeing others’ changes

1. **Flash/highlight on remote update**

- When an `item-updated` SSE event arrives for an item visible in the grid, briefly highlight it.
- This makes “someone changed stuff” tangible without being noisy.

Both are small and high ROI.

------

## Answers to the questions you were unsure about (my “call it” suggestions)

### “SSE only or not sure?”

Do **SSE + fallback polling**. It’s the least risk and still lean.

### “Metrics job API or not sure?”

Skip jobs. Implement only ingestion + SSE events.

### “409: drop change for simplicity?”

Don’t. Use manual conflict UI. “Apply mine again” is a simple overwrite; it’s the simplest resolver that doesn’t betray the user.

### “What’s gallery_id used for?”

Presence grouping and possibly folder-scoped activity. Use normalized folder path.

------

## Concrete additions I’d put into the plan (these will make implementation smoother)

### A) Add event IDs + `Last-Event-ID` support to SSE

This is small but prevents “missed updates” on reconnect.

- Maintain a monotonic `event_seq` (global per server process is fine)
- Each SSE message includes:
    - `id: <seq>`
    - `event: item-updated`
    - `data: {...}`

On connect:

- client sends `Last-Event-ID` automatically if it reconnects
- server can optionally replay buffered events since that ID

**Lean buffering:** keep a ring buffer of last ~1k events in memory.

If `Last-Event-ID` is too old:

- send a `resync-required` event → client refetches folder/items.

### B) Make update atomic with a lock (per-item or global)

Because FastAPI will run sync endpoints in a threadpool, you need atomicity for:

- check version
- apply update
- increment version
- persist enqueue
- broadcast

**Lean approach:** `locks: dict[path, Lock]` + fallback global lock for lock-map creation.

### C) Define patch semantics explicitly (reduces conflicts)

If you keep full replace semantics, collaboration will feel fragile.

**Minimal patch model:**

- Optional fields + `exclude_unset=True`
- Only apply provided fields
- Keep `tags` replacement as-is (or optionally support add/remove later)

### D) Persistence format + flush policy (write this down)

Whatever you choose, specify:

- file location under workspace
- flush interval (seconds)
- behavior when `--no-write`
- recovery on startup

This avoids “we implemented persistence but it’s flaky.”

### E) Normalize paths in one place

Add a single helper and mandate its use everywhere.

Example policy:

- “Canonical path is storage-normalized item path (no leading slash, forward slashes).”
- Or “Canonical path always has leading slash.”
    Pick one and enforce.

### F) Keep updated_at real (and stop synthetic timestamps)

Update `_build_sidecar()` so:

- `updated_at` comes from stored metadata
- `updated_by` comes from stored metadata
- server sets them only on accepted writes

This is core to making collaboration trustworthy.

------

## If you want the plan to stay lean, here’s the “minimal but solid” decision set

If I had to hand the implementer a crisp direction:

1. **Include persistence** (workspace write-behind), default on when writable.
2. **SSE primary + polling fallback** if SSE isn’t healthy.
3. **Presence counts** per folder path; show viewing vs editing, where “editing” = wrote in last 30s.
4. **No metrics job system**, only accept/broadcast metrics updates if they happen.
5. **No silent drops**. 409 → conflict badge + “apply mine again / keep theirs”.
6. `gallery_id = normalized current folder path`.
7. UI list is sufficient + add connection status + remote-update highlight.

