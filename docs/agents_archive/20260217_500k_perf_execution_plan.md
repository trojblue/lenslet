# 2026-02-17 Lenslet 500k Image Performance Execution Plan

## Goal

Make Lenslet feel smooth at **500k images** in a single dataset scope.

Smooth means:

- No UI jank during normal scroll/navigation.
- Predictable first-paint/first-thumb behavior.
- No unbounded client/server work queues.
- Startup that does not block serving for long preindex work.

This plan is based on:

- `docs/20260214_dit03_perf_findings.md`
- `docs/20260214_dit03_perf_probe.json`
- `docs/20260214_dit03_perf_probe_warm.json`
- `docs/20260214_dit03_api_bench.json`

---

## Baseline Problems (Confirmed)

1. Recursive browse payloads are too large and too frequent.
- `GET /folders?recursive=1` returns tens of MB and ~1s+ response times.
- Current browse flow hydrates full recursive item arrays into React state.

2. Tree rendering is not bounded.
- Opening large branches mounts thousands of tree rows and tens of thousands of DOM nodes.
- Tree expansion state remains sticky across navigation, so root can inherit subtree DOM debt.

3. Thumbnail scheduling is bounded in inflight, but not bounded in demand.
- Client queue grows into thousands while inflight stays at 6.
- Prefetch demand is stale relative to current viewport under fast scroll/navigation.

4. Client computes too much per navigation.
- Filter/sort/layout work is performed on full in-memory item arrays.
- Adaptive row build is O(n) over all current items.

5. Startup preindex path still spends tens of seconds in scan/signature work.
- Cold/warm startup still performs expensive full-scan validation workflows.

---

## Foundational Design Decisions

Treat these as architecture constraints, not optimizations:

1. **Windowed data model**
- UI never hydrates full recursive item sets for large scopes.
- UI operates on windows/cursors; server owns canonical ordering/filtering.

2. **Constant-size UI structure**
- Tree and grid DOM scale with viewport, not dataset cardinality.

3. **Bounded queues everywhere**
- Every queue has strict hard caps and cancellation semantics keyed by navigation revision.

4. **Serve fast, validate async**
- Startup should serve from last known good preindex/cache quickly, then validate/rebuild in background.

---

## Performance Budgets (500k Target)

These are pass/fail budgets for acceptance:

- First grid item visible:
  - warm: <= 500ms
  - cold: <= 1500ms
- First thumbnail visible:
  - warm: <= 800ms
  - cold: <= 2000ms
- Scroll smoothness:
  - p95 frame gap <= 20ms
  - max frame gap <= 50ms in normal browse
- Payload:
  - default folder browse response <= 250KB compressed
- DOM:
  - total nodes <= 8k during normal browse
  - rendered tree rows bounded to virtual window
- Queue bounds:
  - client queued thumb requests <= 128 hard cap
  - server thumb queued jobs <= configured hard cap

---

## PR Plan

## PR1: Immediate UI/Queue Stabilization

### Scope

- `frontend/src/features/folders/FolderTree.tsx`
- `frontend/src/features/browse/components/VirtualGrid.tsx`
- `frontend/src/features/browse/components/ThumbCard.tsx`
- `frontend/src/api/requestBudget.ts`
- `frontend/src/api/client.ts`
- `frontend/src/app/hooks/useAppDataScope.ts`
- `frontend/src/app/AppShell.tsx`

### Changes

1. Tree virtualization and expansion hygiene.
- Flatten visible tree rows and virtualize.
- On folder navigation, keep only ancestor chain expanded by default.
- Render row action controls lazily (hover/focus only).

2. Prefetch backpressure and cancellation.
- Introduce hard queue gates by intent type (visible vs adjacent prefetch).
- Drop prefetch requests immediately when queue pressure exceeds threshold.
- Add request-budget cancellation by token/revision, not only global endpoint cancellation.

3. Large-dataset mode switch.
- Force non-adaptive grid mode when scope item count is above threshold.
- Disable non-critical grid adornments in large mode.

### Acceptance

- No tree DOM explosion after entering/leaving large branches.
- Thumb queue no longer grows into thousands in probe runs.
- Subfolder scroll average frame gap materially reduced.

---

## PR2: Replace Recursive Browse Transport with Windowed API

### Scope

- `src/lenslet/server_routes_common.py`
- `src/lenslet/server_browse.py`
- `src/lenslet/server_models.py`
- `src/lenslet/storage/table.py`
- `src/lenslet/storage/table_facade.py`
- `frontend/src/api/client.ts`
- `frontend/src/api/folders.ts`
- `frontend/src/app/hooks/useAppDataScope.ts`

### Changes

1. Add new browse endpoint for windowed reads.
- Example: `GET /browse?path=/x&cursor=...&limit=...&sort=...&filters=...`
- Response includes items window, total count, next/prev cursor, generation token.

2. Keep `/folders` for compatibility, but stop using recursive full payload in primary UI path.

3. Server-side sort/filter.
- Move expensive sort/filter from client full arrays to server-side operations over indexed storage.

4. Slim browse payload fields.
- Return only fields required for grid browse hotpath.
- Defer heavy/rare fields to on-demand detail requests.

### Acceptance

- Default browse payload size and parse cost drop by an order of magnitude.
- Folder transitions are no longer dominated by recursive payload hydration.

---

## PR3: Thumbnail QoS on Server

### Scope

- `src/lenslet/thumbs.py`
- `src/lenslet/server_media.py`
- `src/lenslet/server_browse.py` (telemetry integration)

### Changes

1. Priority classes in thumb scheduler.
- Prioritize viewport-visible over speculative prefetch.
- Keep LIFO/FIFO policy explicit per class, not accidental.

2. Queue hard caps with drop policy.
- Reject stale/low-priority work early under pressure.

3. Navigation revision cancellation.
- Carry revision header from client; cancel stale queued work on mismatch.

4. Add queue wait/generate telemetry.
- p50/p95 wait time
- p50/p95 generation time
- canceled queued/inflight counts by reason

### Acceptance

- Reduced long-tail thumb latency under scroll.
- Queue depth remains bounded and stable under rapid navigation.

---

## PR4: Startup and Preindex Fast Path

### Scope

- `src/lenslet/preindex.py`
- `src/lenslet/server_factory.py`
- `src/lenslet/cli.py`
- `src/lenslet/workspace.py`

### Changes

1. Cheap unchanged fast-path.
- Add lightweight dataset manifest/fingerprint checks to avoid full rescan/signature when safe.

2. Serve-first startup.
- Load previous valid preindex quickly and start serving.
- Run validation/rebuild in background and swap generation when ready.

3. Better health diagnostics.
- Expose preindex decision reason in `/health`:
  - reused
  - validating
  - rebuilding
  - mismatch reason

### Acceptance

- Startup wall time to healthy serve is materially reduced on unchanged datasets.
- Rebuilds become explicit background work, not hard startup blockers.

---

## PR5: Optional, High-Scale Hardening

1. Move search path to indexed structures for large datasets.
2. Add persistent sorted-index artifacts for common sort keys.
3. Add memory guards for client caches and dynamic cache sizing.

---

## Items to Axe Immediately

1. Full recursive hydration in main browse flow.
2. Non-virtualized recursive tree rendering.
3. Unbounded speculative thumb prefetch behavior.
4. Adaptive full-list row computation for very large item sets by default.
5. Any UI-side O(n) recompute on each navigation for full scope item arrays.

---

## Validation Protocol

Use browser-in-the-loop measurement for every PR:

1. Extend existing probe scripts to capture:
- queue depth over time
- cancellation counts
- frame-gap distributions
- payload bytes and parse durations

2. Benchmark tiers:
- fixture: `data/fixtures/large_tree_40k`
- synthetic: 100k
- synthetic: 500k

3. Regression gates:
- fail PR if budgets above are violated on warm runs.

---

## Rollout Notes

1. Keep old `/folders?recursive=1` path available short-term for compatibility.
2. Gate new browse path behind feature flag until probe baselines are stable.
3. Flip default once probe and smoke checks pass at 40k and 100k, then validate 500k.

---

## Expected Outcome

After PR1-PR4:

- UI responsiveness is bounded by viewport complexity instead of dataset cardinality.
- Network/parse/GC pressure from recursive mega-payloads is removed from the hot path.
- Thumbnail behavior becomes queue-stable under aggressive scrolling.
- Startup behavior becomes practical for repeated use on large mostly-stable datasets.
