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

## Short visual viewport: product defect D07

After the original corrected toolbar gate passed, a targeted 800×400 CSS-pixel
viewport at four-times pinch zoom exposed an actual product defect. The visible
viewport was 200×100, but the grid context menu was 184×153.375 at (8,8), ending
at y=161.375. The shared CSS max-height still resolved to 384px from layout
`100vh`, so the last actions were outside the visual viewport. Evidence:
`/tmp/lenslet-jaku-delivery-toolbar-short-zoom.log` and
`/tmp/lenslet-jaku-delivery/toolbar-short-zoom-before.json`.

Severity: HIGH under `better-accessibility` (a reachable zoom scenario hides
actions); this is separate from the D05 harness defect.

The ContextMenu owner now limits height using the same visual-viewport bounds
that already position it, retains its existing internal scroll behavior, and
sets fixed positioning explicitly like the shared Dropdown. The base dropdown
rule previously overrode the Tailwind fixed utility. Natural scroll height is
used when reclamping so enlarging a previously constrained menu also stays
inside bounds. The toolbar gate now uses the shorter zoomed viewport, checks a
fresh menu's first painted frames, and verifies the final action is reachable
through internal scrolling. The first integration bundle passed the focused menu check: menu bounds were
(8,8)–(192,92), height 84, inside the 200×100 visual viewport; the last action
was reachable and all first-paint samples passed. Evidence:
`/tmp/lenslet-jaku-delivery/menu-short-zoom-after.json`. Integration build 2 includes the natural-height reclamp revision and modal
popup ownership hook. Its menu and Similarity stages completed successfully;
the full gate then failed a separate toolbar mounted-control invariant (Back
in browse, Upload in Viewer) after another integration change made those
controls conditional. Evidence:
`/tmp/lenslet-jaku-delivery/toolbar-build2.json`. The layout owner and root reviewed the semantics: Back belongs only to
explicit Viewer mode, and Upload had no production caller at all and is being
removed. The root owns the corresponding canonical explicit-mode exception.
The updated gate requires Back absent in every browse snapshot and visible,
enabled, keyboard reachable and inside viewport in Viewer, and requires dead
Upload absent in every mode. Refresh/search mounted-control and geometry
invariants remain unchanged. Integration build 3 (`index-B_0Yd0ra.js`) passed the full strengthened toolbar
gate: `/tmp/lenslet-jaku-delivery/toolbar-build3.json`. Toolbar and outer-anchor
deltas were 0px. The short zoomed menu was (8,8)–(192,92), its final action was
reachable, and fresh mount samples were opaque and inside viewport. Similarity
validation reported focused=true, invalid=true, and the associated message
“Paste a base64 vector for the query.” The explicit-mode Back and removed Upload
checks also passed.

That integration also intentionally moved Similarity input errors from a generic
alert into an `aria-describedby` field error. The toolbar gate now requires a
focused, `aria-invalid=true` vector input with a visible nonempty associated
message. Shell/header/footer geometry and stale-completion assertions remain
unchanged. This validates the improved recovery contract rather than requiring
an obsolete generic alert.

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

## Final integration probe lifecycle correction D08

The first final-build grid run completed all geometry, media, hover and ranking
subsections but reported `top rail status fixture was not visible`. This was
not a status-copy regression: earlier snapshots showed the zoom warning visible,
with the correct rail reset, and all relevant geometry deltas were zero. The
probe evaluated `.grid-top-status-list` after `cdp_session.detach()`, which
clears the emulated 110% zoom and may legitimately remove that warning.

The probe now checks the exact “Browser zoom 110%.” message and its named
“Dismiss browser zoom warning” button while emulation is still active, before
teardown. All existing context visibility, scroll reset, and geometry checks
remain. Initial evidence: `/tmp/lenslet-jaku-final-delivery/grid.json`. The corrected
full grid rerun passed: `/tmp/lenslet-jaku-final-delivery/grid-after.json`.

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
- Final build 4 full grid probe after lifecycle correction:
  `/tmp/lenslet-jaku-final-delivery/grid-after.json` — passed, including
  geometry, browse, decoded media and hover continuity.
- Final build 4 strengthened toolbar probe:
  `/tmp/lenslet-jaku-final-delivery/toolbar.json` — passed; entry
  `index-CX8d8Oj4.js`, stylesheet `index-Dpsf9UVB.css`.
- Final strengthened toolbar probe on integration build 3:
  `/tmp/lenslet-jaku-delivery/toolbar-build3.json` — passed, including short
  visual viewport, fresh popup paint, field recovery and explicit toolbar modes.
- Corrected grid probe: `/tmp/lenslet-jaku-delivery/grid-after.json` — passed
  after restoring the source fixture between suites; decoded-pixel and
  mixed-identity checks remain unchanged.
- Gzip experiments used `httpx.ASGITransport` against `create_api_app` plus
  `mount_frontend`, then direct `gzip.compress` repeated 12 times per level.
  They include Python response handling and exclude network transport.

All temporary fixtures and logs stay under `/tmp`; no source datasets were
modified. The preferred server port owned by this audit is 7116; the standard harness
may allocate an ephemeral fallback when that port is temporarily occupied.
