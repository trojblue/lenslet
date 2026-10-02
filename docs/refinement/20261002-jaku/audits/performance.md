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

**Implemented and validated; P02 extends it.** AppShell supplies changing callback closures through LeftSidebar; visible-window updates therefore traversed all 10,001 TreeNode components. FolderTree now forwards actions through stable callbacks backed by the existing latest-ref primitive, and TreeNode uses React's ordinary shallow memoization. The callbacks still read the latest parent behavior; data, expansion, current path, activity and count invalidation remain explicit inputs.

With isolated rebuilt assets and the same fixture/browser, five seconds of scrolling improved from 19 sampled frames to 100, mean frame gap 278.69→50.84 ms, maximum gap 500→83.4 ms, and scripting duration 4.62→1.11 seconds. Measurements are individual samples, not statistical distributions. The large DOM remains, so cold startup and paint cost still warrant virtualization.

Focused FolderTree tests: 3 passed. Evidence: `/tmp/lenslet-jaku-performance/memoized.json`. The temporary build lives under `/tmp/lenslet-jaku-performance/build`; no shared generated assets were overwritten.

## Additional findings and assignments

- **P02 — folder virtualization:** Root expansion mounts 10,000 child components/queries. Flatten visible logical rows and virtualize them, while query ownership and retained expansion stay outside virtual row lifetime. Keyboard navigation must use logical rows (including offscreen Home/End targets), not only mounted DOM nodes. Preserve counts, actions, scroll and accessibility semantics. Implemented and validated below.
- **P03 — stale blob request ownership:** BlobLRUCache completion/finally handlers can repopulate a cleared cache and remove a replacement request after cancellation. Reported to root for separate owner-guard fix and adversarial deferred-promise tests.
- **P04 — large histogram argument overflow:** `Math.min(...values)` / `Math.max(...values)` fail with 200,000 entries (`RangeError` reproduced in Node). Reported to root for bounded-loop implementation and realistic population tests.
- **P05 — startup bundle reach:** Non-default Viewer, similarity, metrics/derived UI imports are in the entry graph; bundle agent owns measured import-graph investigation. Do not add loading-first frames or delay persisted panel presentation merely to shrink a chunk.
- Grid already virtualizes mounted cards, thumbnail/full-file caches already bound bytes, and thumbnail object URLs already use leases. Avoid speculative memoization or replacing these working ownership systems without targeted traces.

## Measurement limits

Synthetic images are deliberately cheap to decode and do not characterize real photographic decode cost, remote latency, or huge table metrics. Large-tree performance numbers must be rerun after final packaged assets are built. Existing acceptance thresholds are not evidence of 60 Hz smoothness; report frame distributions and script cost alongside pass/fail.

## P02 implementation and verification

The folder tree now builds a logical row model and virtualizes large trees using
its existing TanStack dependency. Small trees keep ordinary flow. Tree-level
query owners observe root, expanded and current paths, independently of row
mounting; collapsed branches retain settled payload/count records without
keeping an ever-growing set of inactive observers. Workspace/source identity
keys the tree and releases this state on a hard reset. Counts use the common
React Query owner instead of a second async cache, keeping settled counts during
refresh and preventing stale canceled work from repopulating a private cache.
Unknown closed-folder counts use a neutral dash; only real pending loads say
loading. Active text/count contrast and scoped folder Retry were integrated with
the parallel visual/writing findings.

Logical keyboard navigation covers offscreen Home/End and neighboring rows,
skips status rows, and keeps a mounted roving tab stop. `aria-level`,
`aria-posinset`, and `aria-setsize` describe the complete logical hierarchy.
Hidden tools keep their last nonzero viewport and measured row sizes. A callback
ref publishes actual scroll-container attachment before paint, including a warm
source-key remount where cached queries do not otherwise rerender the child.
There is no invented fixed viewport fallback.

The first isolated production sample reduced DOM elements **101,487→1,760**
and mounted folder rows **10,001→29**. Over five seconds it sampled **275 frames**
(mean gap **18.37 ms**, maximum **50.1 ms**) compared with the baseline 19 frames
(mean **278.69 ms**, maximum **500 ms**). This is a measured synthetic workload,
not a guarantee of sustained 60 Hz across devices. Final packaged repetitions are recorded below.

New gate:

```sh
python -m scripts.browser.folder_tree --base-url http://127.0.0.1:7115 \
  --output-json /tmp/lenslet-jaku-performance/folder-tree-gate.json
```

It reuses the existing large-tree fixture rather than generating a second
fixture family. It checks a bounded rendered row window, truly visible
Home/End targets across 10,000 folders, expansion/open selection, collapse/reopen,
and the earliest post-return painted frame including visible descendant text,
actions, expansion state and scroll position. A second scenario deliberately
finishes an unvisited folder request while Metrics is visible, then returns to
Folders. This catches both the virtualizer render loop found during development
and hidden zero-viewport frames that static markup/unit tests cannot detect.

Focused model/markup tests: five passed; TypeScript passed. The production
browser gate passed against both isolated assets and packaged build 5, including
an explicit assertion that the delayed cold request completed while hidden. The
initial hidden-tab gate failed (first frame mounted zero rows), drove the
viewport-owner fix, and was rerun successfully. Raw evidence stays under
`/tmp/lenslet-jaku-performance/`; do not count intermediate failing builds as
passing final validation.


## Final production measurements

Evidence: [performance.json](../evidence/performance.json). Three interleaved
baseline/update pairs used the same warm backend and 1440×960 viewport, a fresh
browser context per run, identical local asset interception for both builds,
a 500 ms settle interval, and the existing five-second scroll probe. Baseline
assets are the untouched previous motion-refresh bundle. All six runs had no
page errors.

| Paired measurement | Baseline | Updated |
|---|---:|---:|
| Median first visible grid | 4.576 s | 0.477 s |
| Median first thumbnail telemetry | 4,443 ms | 355 ms |
| Median of each run's mean frame gap | 295.36 ms | 18.11 ms |
| Median sampled frames / five seconds | 19 | 278 |
| Worst observed frame gap | 549.9 ms | 50.1 ms |
| Mounted folder rows | 10,001 | 29 |
| DOM elements (first pair) | 101,478 | 1,752 |

The independent existing primary large-tree gate at 1680×980 also passed with
a fresh server and browser: first grid **0.62 s**, first thumbnail **489 ms**,
maximum frame gap **66.6 ms**, and **232** sampled frames. Folder/thumbnail/file
request peaks stayed **2/6/0**, within the existing limits.

Direct packaged-browser reloads then reused one browser context and backend.
The initial fresh-browser visit took 0.976 s to first grid; two warm visits took
0.400 s and 0.425 s. Their mean frame gaps were 18.11, 19.16 and 19.07 ms,
with no page errors. These separate protocols are recorded individually, not
combined into a misleading aggregate.

The focused virtual-tree gate passed twice on packaged build 5. It confirms
visible logical End navigation, bounded rows, exact settled descendant content
on the first return frame, and a deliberately delayed unvisited-folder response
completing while hidden. The source/workspace reset remains the explicit release
boundary for retained branch presentation. Performance audit servers were stopped after
measurements; user-requested tmux demos were left running.
