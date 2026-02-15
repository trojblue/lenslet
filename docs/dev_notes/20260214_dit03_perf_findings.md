# 2026-02-14 UI Performance Findings (`/data/yada/data/dit03_hps_csway`)

## Scope

Follow-up performance audit using the same browser-in-the-loop method as:

- `docs/dev_notes/20260214_subfolder_thumb_burst_debug.md`

Dataset target:

- `/data/yada/data/dit03_hps_csway`

Artifacts produced:

- `docs/dev_notes/20260214_dit03_perf_probe.json` (cold-ish pass)
- `docs/dev_notes/20260214_dit03_perf_probe_warm.json` (warm pass)
- `docs/dev_notes/20260214_dit03_api_bench.json` (endpoint benchmarks)

## Method

1. Run Lenslet with `--no-write`.
2. Wait for `/health` indexing state `ready`.
3. Run headless Chromium scenario:
   - root load
   - root scroll
   - open `base_spine`
   - subfolder scroll
   - (cold pass also included return to root)
4. Capture:
   - `window.__lensletBrowseHotpath` telemetry
   - request durations by endpoint (`folders`, `thumb`, `file`)
   - frame-gap/jank probes
   - DevTools performance counters (`TaskDuration`, `LayoutCount`, `Nodes`, heap, listeners)
   - DOM geometry and rendered counts
5. Run direct API benchmarks to separate backend endpoint cost from frontend/render costs.

## Key Measurements

### Startup / Indexing

- `/health` readiness:
  - cold pass: `70.109s`
  - warm pass: `60.614s`
- Direct `ensure_local_preindex(...)` timing during test window:
  - run 1: `59.56s` (`reused=False`, `73944` images)
  - run 2: `51.401s` (`reused=False`, `73952` images)

### Recursive Folder Payload Cost

From `20260214_dit03_api_bench.json`:

- `GET /folders?path=/&recursive=1`
  - payload: `30,029,226` bytes
  - items: `73,835`
  - p50: `1721.276ms`
- `GET /folders?path=/base_spine&recursive=1`
  - payload: `19,951,262` bytes
  - items: `48,004`
  - p50: `923.303ms`
- `count_only` equivalents are tiny/fast:
  - root count-only p50: `1.073ms`
  - base count-only p50: `22.247ms`

### UI Hotpath / Browser

Cold pass (`20260214_dit03_perf_probe.json`):

- First visible grid item latency: `2494ms` (root), `2745ms` (base_spine)
- First thumbnail latency: `2590ms` (root), `2732ms` (base_spine)
- Root scroll (9s):
  - max frame gap: `33.4ms`
  - avg frame gap: `16.73ms`
  - thumb queue reached `3634` (`inflight` capped at `6`)
- Subfolder scroll (12s):
  - max frame gap: `66.8ms`
  - avg frame gap: `38.74ms` (janky)
  - thumb queue reached `1589`
- Opening `base_spine` created very heavy UI state:
  - rendered tree items: `8003`
  - DOM nodes snapshot: ~`90k`
  - long-task total: `2051ms`
  - longest long task: `694ms`

Warm pass (`20260214_dit03_perf_probe_warm.json`):

- Thumb latency improved significantly (cache effect):
  - `thumb` p50: `16.4ms`, p90: `100ms`, max: `175ms`
- But structural pressure remained:
  - root-scroll thumb queue still reached `2873`
  - base view still rendered `8003` tree rows and ~`73k` DOM nodes

### DOM Breakdown (Tree Explosion)

Targeted DOM census:

- root loaded:
  - total nodes: `1825`
  - tree nodes: `28`
- root after scroll:
  - total nodes: `2881`
  - tree nodes: `28`
- base_spine loaded:
  - total nodes: `72,142`
  - tree nodes: `72,029`
  - tree items: `8003`

Most nodes came from tree-row markup (`div`, `button`, `svg`, `circle`, `span`) repeated per row.

## Priority Improvement Areas

### 1) Folder Tree Virtualization (Highest UI Impact)

Problem:

- Entering `base_spine` mounts thousands of tree rows at once.
- This alone pushes DOM into ~`70k+` nodes and introduces long tasks up to `694ms`.

Change:

- Flatten tree model and virtualize visible rows.
- Avoid rendering per-row action controls/icons until row hover/focus.
- Keep subtree counts lazy for off-screen rows.

Expected win:

- Major reduction in long tasks, memory pressure, and subfolder scroll jank.

### 2) Stop Full Recursive Payloads as Default Browse Transport

Problem:

- Recursive payloads are very large (`~20-30MB`) and frequently requested.
- Current flow repeatedly asks for large `recursive=1` responses during navigation.

Change:

- Switch browse transport to paged/windowed recursive loading.
- Keep `count_only` for fast totals.
- Reduce item payload fields for browse (defer heavy metadata).

Expected win:

- Lower TTFB + parse time, less GC churn, faster folder transitions.

### 3) Thumb Prefetch Backpressure / Priority

Problem:

- Client thumb queue reaches thousands (`2873-3634`) while only `6` are inflight.
- This creates large deferred work and stale demand during navigation.

Change:

- Add hard backpressure gate (disable prefetch beyond queue threshold).
- Prioritize strictly visible cells over adjacent-row prefetch when queue is high.
- Cancel lower-priority queued thumb intents on rapid scroll direction/path changes.

Expected win:

- Better interactivity under scroll, fewer burst tails, less unnecessary work.

### 4) Startup Preindex Strategy

Problem:

- Cold starts repeatedly spend ~`50-70s` before `/health` is reachable.
- `ensure_local_preindex` cost dominates startup in this dataset size.

Change:

- Add cheap unchanged-fast-path (avoid full rescan/signature rebuild when safe).
- Move heavy preindex rebuild to background with early serve for existing cache.
- Expose preindex decision diagnostics in `/health` for easier ops debugging.

Expected win:

- Large startup responsiveness gain when dataset is stable or near-stable.

### 5) Add Missing Perf Observability

Current hotpath telemetry is useful, but missing two critical dimensions:

- thumbnail queue wait time (server-side)
- per-phase client queue depth over time (not just snapshots)

Add timers/counters for:

- thumb queue wait p50/p95
- thumb generation time p50/p95
- canceled thumb work (queued vs inflight) by navigation event

This will make the next optimization pass measurable and safer.
