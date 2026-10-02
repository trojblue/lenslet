# Frontend delivery and continuity gate audit

Scope: main gallery delivery, thumbnail/backend hot paths, and browser validation.
Ranking behavior is outside this refinement. Read the repository continuity
contract, `better-code` backend guidance, and Jaku `better-ui/performance.md`.
Observations below were taken from the initial packaged UI at `122df55`; timing
measurements are local microbenchmarks, not end-to-end network speed claims.

## Findings and decisions

| ID | Finding | Evidence | Decision |
| --- | --- | --- | --- |
| D01 | Fingerprinted Vite assets lack explicit cache lifetime | `web/frontend.py` only sets HTML headers. ASGI GETs of `assets/index-A1wR_75P.js` and CSS returned ETag/Last-Modified but no Cache-Control | Implement immutable caching only for `/assets/<name>-<8-character Vite hash>.js` and `.css`. Preserve shell no-store and ordinary static-file behavior. Test both initial and conditional requests. |
| D02 | Main JS is recompressed at gzip level 9 per request | Main JS 556,569 bytes, gzip 163,502; seven warm ASGI GETs 23.75–24.07 ms. Direct gzip benchmark median level9 19.87 ms, level6 15.92 ms (163,838 bytes), level4 8.49 ms (171,203 bytes), level1 5.29 ms (195,669 bytes) | Do not change compression during this pass. Asset caching and bundle reduction address repeated cost. Precompression can avoid compression CPU entirely, but needs build ownership, encoding negotiation and a representative delivery benchmark. |
| D03 | Thumbnail and media ownership already have substantial bounded infrastructure | Backend scheduler: four workers, 128 queued, 256 inflight keys, per-key waiter deduplication, foreground admission that can drop queued background jobs. Frontend BlobLRUCache owns bounded blobs/inflight requests; request budgets and thumbnail prefetch queue checks already exist | Preserve these owners; no second cache/scheduler. Any further change must show queue saturation, repeated requests or stalled foreground work in a representative trace. |
| D04 | Thumbnail URLs have mutable source identity | Backend `/thumb` returns WebP without immutable headers. Source-column changes reuse logical image paths; frontend clears media caches at source boundaries | Do not apply static-asset immutable policy to media or API paths. A media HTTP cache requires explicit versioned identity or validation semantics first. |
| D05 | Standard toolbar gate conflates a disappearing tree owner with menu clamping | Fresh failure reproduced. Instrumented menu was present at 1440px in Exporting state, absent 132ms later at 160px, before the injected 500ms export delay. `AppShell.tsx` explicitly closes tree menus when folders surface hides | Separate export busy geometry, responsive tree-owner dismissal, and grid-owned menu viewport clamping. Preserve opacity and one-pixel bounds assertions. Corrected full toolbar gate passes, including the existing four-times zoom bounds. |
| D06 | Standard grid gate leaks backend source selection into independent media traces | `exercise_atomic_browse_continuity` switches source to `source_alt`; browser context close does not restore server state. Later Compare oracle still expects original green quick_01 pixels; alternate source fixture is magenta | Restore and assert fixture source `source` before independent media probes. Keep decoded-pixel and mixed-identity gates unchanged. |

## Existing validation coverage and gaps

The primary large-tree profile is 40,000 images across 10,000 folders, with
cold and warm runs required. Its current bounds are first grid/thumbnail within
5 seconds and maximum sampled frame gap 700 ms. The tiny 400-image profile is a
sanity check and explicitly cannot replace primary acceptance. It records
request-budget peaks and console/page errors. Reuse this workload for changes
to tree hydration or browse ownership; retain both cold and warm evidence.

The 700 ms maximum-frame-gap gate catches freezes but does not prove a smooth
60 Hz interaction. Before claiming scrolling improvements, compare frame-gap
percentiles/long-task counts and request peaks on the same environment, dataset,
viewport and interaction sequence. Do not silently tighten the historical gate
and turn machine noise into an unrelated failure.

Existing media routes stream local originals via FileResponse, remote originals
via a safe-header StreamingResponse, and only fall back to whole-file bytes
when storage lacks a stream path. This is already the correct shared ownership
for originals. Do not replace streaming with a new application-level buffer.

## Execution evidence

- Static header test: `pytest -q tests/web/app/test_frontend_shell_cache.py` —
  2 passed, including existing shell invalidation and asset/HTML cache policy.
- Focused Ruff check of changed delivery/harness files — passed.
- Before toolbar probe: `/tmp/lenslet-jaku-delivery/toolbar.json` — failed at
  missing context menu. Instrumentation:
  `/tmp/lenslet-jaku-delivery-toolbar-instrumented.log`.
- Corrected toolbar probe: `/tmp/lenslet-jaku-delivery/toolbar-after.json` —
  passed. Export geometry, tree-owner dismissal, grid-menu first paint, 160px
  viewport clamp, four-times zoom clamp, and all other standard toolbar checks
  passed. No ContextMenu product change was required for these scenarios.
- Gzip experiments used `httpx.ASGITransport` against `create_api_app` plus
  `mount_frontend`, then direct `gzip.compress` repeated 12 times per level.
  They include Python response handling and exclude network transport.

All temporary fixtures and logs stay under `/tmp`; no source datasets were
modified. The only server port owned by this audit is 7116.
