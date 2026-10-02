# Frontend performance investigation

Scope: main gallery, folders, search, Inspector, metrics, Viewer, Compare. Ranking is excluded. Applied `better-code` frontend-performance guidance and the canonical presentation contract: measure hot paths, preserve requested/presented identity and hidden state, and keep resources bounded.

## Reproducible baseline

Baseline served bundle: commit `122df55`; entry JavaScript is 556,569 bytes (allocated filesystem blocks are larger and must not be mistaken for transferred bytes). Synthetic fixture contains 40,000 100×200 JPEG images in 10,000 folders. No source datasets changed.

```sh
python -m scripts.browser.large_tree.smoke \
  --dataset-dir /tmp/lenslet-jaku-performance/fixture --port 7115 \
  --output-json /tmp/lenslet-jaku-performance/baseline.json
```

Existing primary acceptance passes, but its thresholds permit visibly poor responsiveness:

| Measurement | Baseline |
|---|---:|
| First visible grid | 4.456 s |
| First grid hot-path telemetry | 2.964 s |
| First thumbnail telemetry | 4.317 s |
| Five-second scroll sampled frames | 16 |
| Mean frame gap | 356.65 ms |
| Maximum frame gap | 500 ms |
| Request peaks folders/thumb/file | 2 / 6 / 0 |

A separate Chromium/CDP trace at 1440×960 observes 101,487 DOM elements, 10,001 folder treeitems, and only 66 virtual gridcells. During a five-second scroll interval, scripting occupies 4.62 seconds, versus 0.010 seconds layout and 0.018 seconds style recalculation. Hiding the folder tree with CSS does not help. CPU samples identify TreeNode, useFolder, query options/result updates, and React DOM prop diffing as dominant work. This is evidence of repeated JavaScript work, not merely a large layout.

Local evidence: `/tmp/lenslet-jaku-performance/{baseline.json,profile.json,cpu.json}`. Scripts `profile.py` and `cpu.py` reproduce the diagnosis. The served demo sessions on 7095/7096 were untouched.

## P01 — prevent unrelated gallery updates from rebuilding the folder tree

**Implemented, awaiting integrated validation.** AppShell supplies changing callback closures through LeftSidebar; visible-window updates therefore traversed all 10,001 TreeNode components. FolderTree now forwards actions through stable callbacks backed by the existing latest-ref primitive, and TreeNode uses React's ordinary shallow memoization. The callbacks still read the latest parent behavior; data, expansion, current path, activity and count invalidation remain explicit inputs.

With isolated rebuilt assets and the same fixture/browser, five seconds of scrolling improved from 19 sampled frames to 100, mean frame gap 278.69→50.84 ms, maximum gap 500→83.4 ms, and scripting duration 4.62→1.11 seconds. Measurements are individual samples, not statistical distributions. The large DOM remains, so cold startup and paint cost still warrant virtualization.

Focused FolderTree tests: 3 passed. Evidence: `/tmp/lenslet-jaku-performance/memoized.json`. The temporary build lives under `/tmp/lenslet-jaku-performance/build`; no shared generated assets were overwritten.

## Additional findings and assignments

- **P02 — folder virtualization:** Root expansion mounts 10,000 child components/queries. Flatten visible logical rows and virtualize them, while query ownership and retained expansion stay outside virtual row lifetime. Keyboard navigation must use logical rows (including offscreen Home/End targets), not only mounted DOM nodes. Preserve counts, actions, scroll and accessibility semantics. Investigation/implementation follows P01.
- **P03 — stale blob request ownership:** BlobLRUCache completion/finally handlers can repopulate a cleared cache and remove a replacement request after cancellation. Reported to root for separate owner-guard fix and adversarial deferred-promise tests.
- **P04 — large histogram argument overflow:** `Math.min(...values)` / `Math.max(...values)` fail with 200,000 entries (`RangeError` reproduced in Node). Reported to root for bounded-loop implementation and realistic population tests.
- **P05 — startup bundle reach:** Non-default Viewer, similarity, metrics/derived UI imports are in the entry graph; bundle agent owns measured import-graph investigation. Do not add loading-first frames or delay persisted panel presentation merely to shrink a chunk.
- Grid already virtualizes mounted cards, thumbnail/full-file caches already bound bytes, and thumbnail object URLs already use leases. Avoid speculative memoization or replacing these working ownership systems without targeted traces.

## Measurement limits

Synthetic images are deliberately cheap to decode and do not characterize real photographic decode cost, remote latency, or huge table metrics. Large-tree performance numbers must be rerun after final packaged assets are built. Existing acceptance thresholds are not evidence of 60 Hz smoothness; report frame distributions and script cost alongside pass/fail.
