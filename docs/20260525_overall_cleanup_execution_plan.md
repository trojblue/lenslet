# 2026-05-25 Overall Cleanup Execution Plan


## Outcome + Scope Lock


After implementation, Lenslet should feel like a deliberate gallery tool under real browser use. Justified rows should not create ugly strips for panorama, tall, missing-size, or last-row inputs. Hover preview should be bounded, cancellable, and thumbnail-based. Viewer and compare should preserve inspection context across resize. Their dialogs should trap and restore focus correctly. Menus should stay inside the visible viewport. Comparison export should work without an undeclared `unibox` dependency. The initial browse bundle should be split only along safe, named secondary surfaces.

Goals:

1. Replace the fragile adaptive-row behavior with a bounded justified-row contract and rename the user-facing mode from `Masonry` to `Justified rows`.
2. Resolve the comparison export contract by making Pillow the primary PNG/GIF composition path and removing `unibox_missing` as a normal failure mode.
3. Add an incremental browser evidence script that each sprint extends with the user-visible failure path it fixes.
4. Use visual viewport bounds for fixed-position menu and hover-preview placement without creating a broad viewport subsystem.
5. Make hover preview use direct abortable thumbnail/preview fetches, with stale-response guards and no full-file cache pollution.
6. Share viewer/compare transform math and preserve normalized image-space center on resize.
7. Replace fake viewer/compare Tab handling with a focused modal primitive for focus entry, Tab wrapping, Escape, and focus restore.
8. Stop browse-grid `Ctrl+wheel` from hijacking browser zoom while keeping explicit thumbnail-size controls.
9. Reduce the Vite main chunk by splitting only measured secondary surfaces after the behavior fixes land.

Non-goals:

1. Do not rewrite the app stack, package managers, storage model, table ingestion, CLI, or workspace formats.
2. Do not add Floating UI, PhotoSwipe, React Aria, OpenSeadragon, a masonry library, or any other dependency by default.
3. Do not implement true masonry columns, deep zoom, tiling, or persistent server-side preview generation.
4. Do not split all of `AppShell.tsx`, `VirtualGrid.tsx`, or `styles.css` just to satisfy file-size warnings.
5. Do not remediate dev-tooling audit findings or migrate uv dependency groups in this plan.
6. Do not downgrade sprint completion to unit tests only; every sprint needs browser evidence.

Pre-approved behavior changes:

1. The existing `adaptive` visual mode may be relabeled from `Masonry` to `Justified rows`; keep the persisted internal value unless a ticket proves a hard cutover is cleaner.
2. Comparison export no longer exposes a `unibox_missing` failure path. Tests should assert Pillow-only success plus existing invalid-input, metadata, size-limit, and format errors.
3. Hover preview may show `/thumb` or another bounded preview image instead of the full source file, and may skip preview on failed or aborted preview fetches.
4. Viewer and compare may preserve current image-space center on resize instead of always resetting to fit.
5. Viewer and compare may move focus into the dialog, cycle focus inside, close on Escape, and restore focus to the invoking thumbnail or control.
6. Browse `Ctrl+wheel` may stop resizing thumbnails so browser zoom remains browser-owned; the existing toolbar slider remains the explicit thumbnail-size control.
7. Menus may change DOM roles to use consistent selection-list or command-menu semantics.
8. Secondary surfaces may be lazy-loaded if visible behavior stays unchanged after load.

Requires sign-off before implementation:

1. Adding or upgrading npm, Python, or system dependencies.
2. Introducing a new gallery, gesture, menu, modal, or accessibility library.
3. Adding a backend preview endpoint beyond existing `/thumb`.
4. Changing persisted localStorage/workspace schema in a way that needs migration logic.
5. Removing existing user commands instead of moving them to explicit controls.
6. Expanding cleanup into a broad AppShell, VirtualGrid, or CSS rewrite.
7. Accepting a sprint without the sprint-specific live-browser evidence.

Deferred or out of scope:

1. True masonry columns and deep-zoom/tiled image support are deferred.
2. Ranking fullscreen focus behavior is observed but deferred unless the viewer/compare primitive makes it a near-zero diff.
3. A full accessibility audit outside viewer/compare dialogs and touched menu primitives is deferred.
4. Dev dependency security/tooling updates are deferred to a dedicated tooling branch.
5. Broad file splitting is deferred; extraction is allowed only where it naturally supports the behavior tickets.


## Context


This plan is based on `docs/20260525_overall_cleanup_review.md`. It also preserves the regression gates from `docs/20260525_responsive_layout_structural_plan.md`, which already closed the earlier responsive `R1` through `R8` failures with live-browser evidence. The new work should not re-plan those completed fixes; it should keep them passing while addressing the next cleanup wave.

No `PLANS.md` was found in the current repo scan. The active planning constraints are the user-provided repository instructions and the Lenslet skill guidance. `docs/agents_archive/` remains historical context only.

Important current code facts:

1. `frontend/src/features/browse/model/adaptive.ts` owns a greedy justified-row algorithm with no min/max row-height contract or outlier policy.
2. `frontend/src/features/browse/hooks/useVirtualGrid.ts` feeds adaptive rows into TanStack Virtual, so row-count and height changes can affect scroll restoration and hot-path render timing.
3. `frontend/src/features/browse/components/VirtualGrid.tsx` owns hover-preview timer and object-URL lifecycle and currently calls full-file `api.getFile`.
4. `frontend/src/api/client.ts`, `frontend/src/lib/fetcher.ts`, and `frontend/src/lib/blobCache.ts` already have lower-level abortable fetch pieces, but not a clean abortable hover-preview API.
5. `frontend/src/lib/menuPosition.ts` clamps against layout viewport dimensions; `Dropdown`, `DropdownMenu`, toolbar filter, context menu, and theme settings menu have separate behavior.
6. `frontend/src/features/viewer/hooks/useZoomPan.ts` and `frontend/src/features/compare/hooks/useCompareZoomPan.ts` duplicate transform, wheel, pan, pinch, and resize-reset behavior.
7. `frontend/src/features/viewer/Viewer.tsx` and `frontend/src/features/compare/CompareViewer.tsx` expose modal dialogs but need a real shared focus primitive.
8. `src/lenslet/web/comparison_export.py` dynamically imports `unibox`, even though `pyproject.toml` does not declare it.
9. The current Vite build succeeds but emits a main-chunk warning, so bundle work must target measured secondary surfaces rather than arbitrary module splitting.

Plan review feedback incorporated:

1. The original draft was collapsed from eight phases to five sprints to reduce scope pressure.
2. The browser harness is incremental. It starts with Sprint 1 evidence and gains assertions as each sprint changes behavior.
3. Visual viewport work is limited to a small visible-bounds helper unless failing evidence proves a hook/model is needed.
4. Menu semantics are split into selection-list and command-menu primitives instead of forcing one ARIA pattern everywhere.
5. Adaptive layout gets concrete bounds and large-tree validation because it affects virtualized row geometry.
6. Bundle splitting is last and measured; it must not block the core gallery behavior fixes if safe boundaries do not remove the warning.


## Plan of Work


The plan uses five sprints and fourteen implementation tickets. Each sprint must produce a runnable browser state and update this document continuously, especially Progress Log and Artifacts and Handoff. After each sprint, add clear handoff notes before starting the next sprint.

For minor script-level uncertainties, such as exact fixture filenames, whether the browser checks live in a new `scripts/overall_cleanup_browser.py` or an extension of an existing Playwright script, and exact evidence output paths, proceed according to this approved plan to maintain momentum. After the sprint, ask for clarification and apply follow-up adjustments if the user wants a different placement.

For every ticket with non-trivial code changes, the implementing agent must use the `better-code` skill before and during implementation. State the ticket assumptions, acceptance criteria, core invariants, smallest robust approach, and verification evidence before editing. Apply Karpathy-style guardrails: surface ambiguities before coding, prefer the smallest non-speculative solution, touch only lines tied to the request or verification, remove only unused code introduced by the change, and attach a concrete verification check to each step.

Delegate subagents early when they can find real codepaths or review sprint changes faster. Let subagents run long enough to produce useful results; if any are still running after 10 minutes, request a progress update and why more time is needed rather than terminating them to return faster.

### Scope Budget and Guardrails


Scope budget is five sprints, fourteen tickets, and a narrow file set: adaptive layout and tests, VirtualGrid hover-preview extraction, menu positioning primitives, viewer/compare hooks and components, AppShell `Ctrl+wheel` behavior, comparison export internals, measured Vite split boundaries, focused browser scripts, and generated frontend assets at final handoff.

Debloat and removal targets:

1. Remove the row-geometry behavior that can create tiny panorama strips or oversized last rows.
2. Remove `unibox` as a required comparison export success path.
3. Remove full-file hover-preview fetches from the hover path.
4. Remove duplicated viewer/compare transform math into a shared transform core.
5. Remove fake dialog Tab blocking after the modal primitive is active.
6. Remove browse-grid `Ctrl+wheel` thumbnail resizing if browser evidence confirms explicit controls still work.
7. Remove duplicated viewport-size logic from touched menu paths.
8. Track net effect with `git diff --stat`, targeted `rg` checks for removed behavior, and Vite chunk-size output.

Quality guardrails:

1. Browser evidence is primary. Unit tests, type checks, and builds are secondary.
2. Do not hide visual failures with overflow clipping, z-index, or opacity if the user-facing geometry remains wrong.
3. Do not add dependencies unless sign-off and the dependency security gate are complete.
4. Do not broaden a behavior ticket into a general refactor.
5. If a ticket grows past its named file set or behavior boundary, stop and reduce scope before continuing.

### Sprint Plan


Sprint 1 goal: close the export dependency bug and seed browser evidence.

Demo outcome: a live browser can open a temporary fixture gallery and trigger comparison export successfully without `unibox`. The new browser evidence path records the baseline state and can be extended by later sprints.

Tasks:

1. `OCR-1`: Seed the incremental overall-cleanup browser script.
   Add a minimal browser path that starts a Lenslet server with a temporary fixture dataset, opens browse mode, selects two images, opens comparison/export UI, records viewport/layout evidence, writes JSON, and saves screenshots on failure. Keep this script small; later sprints add their own assertions. Validation: the script runs once against the current fixture and writes evidence JSON even before all cleanup assertions exist.
2. `OCR-2`: Make Pillow the comparison export implementation.
   Replace `unibox` stitching/annotation use with local Pillow helpers. Preserve request/response payloads, PNG/GIF metadata, output naming, alpha flattening, size limits, format limits, and invalid-input errors. Remove or rewrite the test that expects `unibox_missing`; that path is no longer part of the contract. Validation: `pytest -q tests/test_compare_export_endpoint.py` passes without `unibox`, and the Sprint 1 browser script proves UI export success.

Sprint 2 goal: make justified rows robust and honestly named.

Demo outcome: the current adaptive mode renders bounded, sane rows for panoramas, tall screenshots, missing dimensions, single-item rows, and last-row leftovers at phone, half-screen, and short-height browser sizes.

Tasks:

3. `OCR-3`: Define adaptive row geometry tests before changing behavior.
   Add focused tests for `computeAdaptiveRows` with `10:1`, `6:1`, `1:8`, `0:0`, missing width/height, one-image rows, mixed screenshots, and last-row leftovers. The contract should be concrete: unknown dimensions use the existing safe fallback ratio; non-last row image heights stay within a bounded band derived from `targetHeight`; no row including gaps exceeds `containerWidth` beyond rounding tolerance; panorama/tall outliers may use contained full-row cards but must not create tiny strips below the lower bound. Validation: at least one new outlier test fails against the current greedy implementation before `OCR-4`.
4. `OCR-4`: Harden `computeAdaptiveRows`.
   Implement the smallest robust row breaker that satisfies the tests. Prefer constrained greedy or a small local dynamic-programming helper over a dependency. Preserve the `AdaptiveRow` surface unless a narrow extra field is required for contained outliers. Validation: adaptive tests pass, normal grid mode stays unchanged, the browser script adds adaptive geometry checks at `320x700`, `390x700`, `760x430`, `1024x480`, and half-screen desktop, and the large-tree browser probe runs after the change because row counts and measured heights are hot-path behavior.
5. `OCR-5`: Rename the visible mode label to `Justified rows`.
   Update toolbar, mobile drawer, and tests that assert user-facing copy. Keep the persisted internal value `adaptive` unless a simpler hard cutover is explicitly justified. Validation: browser evidence proves the mode switch is reachable and labeled correctly, and settings persistence still works.

Sprint 3 goal: keep menus and hover preview inside the visible viewport, and cancel hover work.

Demo outcome: menus and hover previews stay inside the visible viewport near edges and under zoom-equivalent conditions. Hover preview uses abortable thumbnail/preview fetches, never full-file fetches, and cannot display stale responses after rapid pointer changes.

Tasks:

6. `OCR-6`: Add visible viewport bounds for fixed surfaces.
   Add a tiny `getVisibleViewportBounds()` helper that returns visual viewport left/top/width/height when available and layout viewport bounds otherwise. Use it in menu positioning and hover-preview placement. Do not add pointer-mode, DPR, reduced-motion, or a reactive viewport hook unless browser evidence proves it is needed. Validation: unit tests cover visual-viewport fallback, offset, and oversized-surface clamping.
7. `OCR-7`: Harden menu positioning and semantics.
   Update shared menu/dropdown primitives to use visible viewport bounds and remove the current `listbox`/`menuitem` mismatch. Keep two semantic paths: selection lists use `listbox`/`option`, command menus use `menu`/`menuitem`. Migrate toolbar sort/layout/filter, context menu, and theme settings only as far as needed for consistent bounds and roles. Validation: menu tests cover edge anchors, oversized panels, above/below flips, Escape/outside-click dismissal, and browser evidence opens sort, filter, theme, and context menus near all viewport edges with no off-screen controls.
8. `OCR-8`: Make hover preview abortable, bounded, and stale-safe.
   Add a preview-specific frontend path using direct abortable `/thumb` fetches and local object-URL lifecycle. Do not reuse full-file `api.getFile` or pollute the full-file cache. Add a request token so late responses cannot replace the active preview. Validation: tests prove abort invocation, stale-response rejection, object-URL cleanup, and no full-file cache use; browser evidence proves rapid hover enter/leave does not show stale previews and previews stay within the visible viewport.

Sprint 4 goal: repair viewer/compare resize behavior, modal focus, and browser zoom ownership.

Demo outcome: users can zoom/pan in viewer or compare, resize the browser or change panel state, and keep the inspected region centered within tolerance. Viewer and compare behave like real modal dialogs. Browse mode no longer steals `Ctrl+wheel` from browser zoom.

Tasks:

9. `OCR-9`: Extract shared transform math.
   Add a pure transform module for fit bounds, zoom-around-point, pan offsets, normalized image-space center capture, and resize restoration. Cover wide, tall, square, and compared-image cases before migrating hooks. Validation: focused Vitest tests prove center preservation, fit reset, zoom-around-point, and clamping behavior.
10. `OCR-10`: Migrate viewer and compare hooks to the shared transform core.
    Keep hook return shapes stable where practical. Reset on image identity changes and explicit reset; preserve normalized center on `ResizeObserver` changes. If panning on the stage/backdrop while zoomed is a small event change, include it; otherwise record it as deferred. Validation: existing hook tests pass, new tests cover resize preservation, and browser evidence zooms/pans viewer and compare, resizes from desktop to half-width and short-height viewports, and verifies the same region remains centered within tolerance.
11. `OCR-11`: Add and apply a viewer/compare modal focus primitive.
    Implement a small shared helper for focus entry, Tab and Shift+Tab wrapping, Escape close, and focus restore. The primitive owns focus behavior; AppShell owns visual/layout inertness. If browser evidence shows background focus leakage, fix the smallest AppShell inert path in this sprint. Validation: unit tests cover focus target choice, wrapping, Escape, restore fallback, and browser evidence confirms no background toolbar/sidebar focus leak.
12. `OCR-12`: Stop browse-grid `Ctrl+wheel` hijacking.
    Remove or narrowly gate the AppShell wheel listener so browser `Ctrl+wheel` remains browser-owned in browse mode. Keep toolbar slider and explicit thumbnail-size controls working. Validation: browser evidence confirms `Ctrl+wheel` over browse does not mutate grid item size, toolbar slider still changes thumbnail size, and viewer/compare wheel zoom still works inside their surfaces.

Sprint 5 goal: split measured secondary bundle surfaces and complete conservative cleanup.

Demo outcome: the core gallery fixes remain green, the Vite build has either removed the current main-chunk warning through safe named splits or records a concrete residual blocker, and touched coordinator files are smaller or better isolated because behavior-owned units were extracted.

Tasks:

13. `OCR-13`: Measure and split only safe secondary surfaces.
    Record current Vite output, then choose named secondary surfaces such as compare viewer, comparison export UI, similarity modal/panels, ranking mode, metrics-heavy panels, or debug-only views. Implement the smallest safe dynamic imports. Do not split tiny modules or critical browse path code. Validation: `npm run build` records before/after chunk sizes; the main warning is gone or a residual blocker is documented with a sign-off request; browser evidence opens every lazy-loaded surface touched by the split.
14. `OCR-14`: Final cleanup, review, asset sync, and handoff.
    Remove dead helpers introduced by the plan, keep structural cleanup limited to behavior-owned extraction already created, regenerate packaged frontend assets if UI changed, run cleanup and review gates, and record final evidence paths. Validation: all final gates pass, `git diff --stat` shows the cleanup scope, and the plan contains final handoff notes.

### Task Gate Routine


Every ticket must use this gate routine.

0. Plan gate.
   The code agent briefly restates the ticket goal, acceptance criteria, material assumptions or ambiguities, and files expected to change. If an ambiguity would change behavior, stop and ask. If the ticket includes substantive code work, invoke `better-code` first and state the key invariants, smallest robust approach, and verification evidence.
1. Implement gate.
   Implement the smallest coherent slice that satisfies the ticket. Avoid speculative features, one-off abstractions, unrelated cleanup, broad refactors, and behavior changes outside the approval matrix. Run ticket-specific tests, typecheck, browser checks, or command checks.
2. Cleanup gate.
   After each sprint, run the `code-simplifier` routine below and apply only conservative cleanup.
3. Review gate.
   After cleanup, run the review routine below. Address findings and rerun review when needed before closing the sprint.

### code-simplifier routine


After each complete sprint, spawn a subagent and instruct it to use the `code-simplifier` skill to scan the current sprint changes. Start with non-semantic cleanup only: formatting or lint autofixes, obvious dead code removal, small readability edits that do not change behavior, and docs/comments that reflect what is already true.

Keep this pass conservative. Do not expand into semantic refactors unless explicitly approved. Once this cleanup subagent starts, do not interrupt or repurpose it just to save time. If it runs long, wait or request a progress update; fall back to manual cleanup review only if the subagent is unavailable, fails, or the user explicitly approves the downgrade.

### review routine


After each complete sprint and after the cleanup subagent finishes, spawn a fresh agent and request a code review using the `code-review` skill. Instruct it to be constructively adversarial: look for failure modes, weak validation, unclear scope, removable complexity, and under-engineered shortcuts while keeping feedback actionable.

Use the best available model in the environment with `reasoning_effort` set to `medium`. Review the post-cleanup diff, apply fixes, and rerun review when needed to confirm resolution. Once the review subagent starts, do not interrupt, repurpose, or terminate it to save time. Manual diff review is a fallback only when the review subagent is unavailable, fails after a reasonable wait plus progress check, or the user explicitly approves a downgrade.


## Validation and Acceptance


Primary acceptance checks are live-browser checks. Secondary checks are fast unit, backend, type, build, and lint gates that catch regressions but cannot replace browser validation.

Primary per-sprint checks:

1. Sprint 1.
   Run the new incremental browser script against a temporary fixture dataset and trigger comparison export through the UI. Expected: export succeeds without `unibox`, evidence JSON is written, failure screenshots are available, and the script is small enough for later sprint assertions.
2. Sprint 2.
   Run justified-row browser checks at `320x700`, `390x700`, `760x430`, `1024x480`, and half-screen desktop with panorama, tall, missing-size, single-row, and last-row fixtures. Expected: no tiny strips below the tested lower row-height bound, no horizontal overflow, sane contained outliers, correct `Justified rows` label, stable keyboard navigation, and a scoped large-tree browser probe after `OCR-4`.
   Current status, 2026-05-25 04:52 UTC: focused adaptive geometry tests, full frontend tests, Vite build, packaged frontend sync, repo lint, `scripts/overall_cleanup_browser.py`, and the primary large-tree probe passed for the Sprint 2 behavior path. Large-tree evidence was written to `/tmp/lenslet-large-tree-overall-cleanup.json` with first grid `4.34s`, hotpath `3974ms`, first thumbnail `4052ms`, max frame gap `350.1ms`, and zero `/file` requests.
3. Sprint 3.
   Run menu/hover checks at phone widths, short desktop height, edge anchors, and ordinary zoom-equivalent visual viewport cases. Expected: menus and previews stay inside visible bounds, selection-list and command-menu roles are consistent, hover leave aborts pending work, stale hover responses do not render, and hover never calls the full-file path.
   Current status, 2026-05-25 05:15 UTC: focused viewport/menu/hover tests, full frontend tests, Vite build, packaged frontend sync, repo lint, `tests/test_playwright_large_tree_smoke.py`, and `scripts/overall_cleanup_browser.py` passed for the Sprint 3 behavior path. Browser evidence was written to `/tmp/lenslet-overall-cleanup-sprint3.json`; the hover preview path issued one `/thumb` request and zero `/file` requests, scroll cancellation left zero stale previews, and sort/filter/theme/context surfaces stayed inside visible bounds.
4. Sprint 4.
   Run viewer/compare checks through zoom, pan, resize, panel-state changes, Tab/Shift+Tab, Escape, and focus return. Expected: normalized center stays within tolerance after resize, explicit reset still fits, background controls are not focusable/interactable, browse `Ctrl+wheel` does not mutate thumbnail size, and viewer/compare wheel zoom still works.
5. Sprint 5.
   Run build-size evidence and full browser smoke for touched lazy-loaded surfaces. Expected: the main chunk warning is removed or a concrete residual blocker is documented; all behavior from Sprints 1 through 4 remains green; packaged frontend assets are regenerated if UI output changed.

Primary final gates:

1. Run the existing GUI smoke:

       python scripts/gui_smoke_acceptance.py

2. Run the responsive geometry script that protects the prior `R1` through `R8` work:

       python scripts/responsive_geometry_harness.py --output-json /tmp/lenslet-responsive-geometry-overall-cleanup.json

3. Run the overall cleanup browser evidence script after all sprint assertions have been added:

       python scripts/overall_cleanup_browser.py --output-json /tmp/lenslet-overall-cleanup-final.json

4. Run the large-tree probe after adaptive layout changes:

       python scripts/playwright_large_tree_smoke.py --dataset-dir data/fixtures/large_tree_40k --output-json /tmp/lenslet-large-tree-overall-cleanup.json

5. Manually use the browser at `320px` through `390px`, one half-screen desktop width, one short-height desktop viewport, and browser zoom in/out. Expected: no overlap, no off-screen commands, no broken dialog focus, no ugly justified-row strips, and no stale hover preview.

Secondary fast gates:

1. Run focused frontend tests for touched modules, then full frontend tests:

       cd frontend && npm run test

2. Run focused backend export tests when backend export code changes:

       pytest -q tests/test_compare_export_endpoint.py

3. Run frontend build and record chunk sizes:

       cd frontend && npm run build

4. Run repo lint before handoff:

       python scripts/lint_repo.py

5. If UI assets changed, regenerate and sync packaged frontend assets under `src/lenslet/frontend/`, then rerun the relevant browser smoke.

Dependency security gate:

Run dependency checks only if `package.json`, `package-lock.json`, `pyproject.toml`, or another package manifest changes. If dependencies change, perform fresh online compromise and vulnerability checks before installation, then run the relevant audit command and capture a package decision note. For npm changes, include:

       npm audit --omit=dev
       npm audit signatures

Final acceptance criteria:

1. Justified-row layout handles panorama, tall, missing-size, single-row, and last-row cases without tiny strips or overflow in required browser scenarios.
2. Fixed-position preview and menu surfaces use visible viewport bounds and stay visible at tested edges and zoom-equivalent scenarios.
3. Toolbar, drawer, search, sidebar, overlay, and inspector responsive evidence from the prior structural plan still passes.
4. Viewer and compare preserve normalized center on resize and retain explicit reset behavior.
5. Browse `Ctrl+wheel` no longer hijacks browser zoom; explicit thumbnail-size controls still work.
6. Viewer and compare dialogs satisfy focus entry, focus trap, Escape close, focus restore, and background inert checks.
7. Hover preview is cancellable, stale-safe, bounded, and does not use full-file fetch as the hover path.
8. Comparison export succeeds without `unibox` installed and preserves metadata, limit, format, and invalid-input contracts.
9. Vite main chunk warning is removed by safe named splits or a residual blocker is documented with a sign-off request.
10. Structural slimming is limited to behavior-owned extraction and does not become a broad rewrite.


## Risks and Recovery


Hidden dependencies:

1. Adaptive row heights feed TanStack Virtual. Bad row math can break scroll restoration, keyboard navigation, and hot-path rendering.
2. Hover preview sits near explicit viewer/compare full-file loading. Abort and cache rules must not cancel or downgrade explicit opens.
3. Visual viewport behavior differs across desktop zoom, pinch zoom, and mobile browser UI. Browser evidence must record both layout and visible viewport values where relevant.
4. Menu ARIA changes can break tests or selectors that assumed one role model. Selection-list and command-menu semantics must be explicit.
5. Dialog focus and AppShell inert ownership overlap. The modal primitive owns focus; AppShell owns inert/visibility unless a focused fix proves otherwise.
6. Lazy loading can reduce chunk size but regress first-use behavior if boundaries are poorly chosen.
7. Removing `unibox` changes composition internals. Preserve contracts through tests and browser export evidence, not through implementation details.

Recovery:

1. Keep each sprint committable and reviewable.
2. If a sprint regresses core browsing, revert only that sprint's touched files and preserve failing browser evidence.
3. Do not revert unrelated user changes in the worktree.
4. Keep generated fixture datasets and Playwright evidence under `/tmp` or ignored paths unless the user approves committed fixtures.
5. If the large-tree fixture is unavailable, stop after Sprint 2 browser checks and ask whether to generate a local substitute or defer that gate; do not mark Sprint 2 complete without a scale gate or explicit approval.
6. If a proposed dependency fails security review or sign-off, keep the local implementation path or split dependency adoption into a separate plan.
7. If the Vite warning remains after safe named splits, document the blocker and request follow-up approval instead of arbitrary chunk chasing.


## Progress Log


- [x] 2026-05-25 03:53 UTC: Read `docs/20260525_overall_cleanup_review.md` and treated it as the input review for this plan.
- [x] 2026-05-25 03:53 UTC: Read `docs/20260525_responsive_layout_structural_plan.md`; prior responsive `R1` through `R8` work is a regression gate, not duplicate scope.
- [x] 2026-05-25 03:53 UTC: Read `better-code` and Lenslet skill guidance; the plan requires browser-first evidence and surgical implementation.
- [x] 2026-05-25 03:53 UTC: Delegated read-only codepath scans for browse/grid/hover/menu and viewport/viewer/dialog/export surfaces; incorporated de-scope recommendations.
- [x] 2026-05-25 03:53 UTC: Ran the required adversarial plan review subagent and incorporated feedback by collapsing to five sprints, making browser evidence incremental, tightening export/adaptive/hover/menu/modal contracts, and moving bundle work last.
- [x] 2026-05-25 04:26 UTC: Sprint 1 implementation completed for `OCR-1` and `OCR-2`. Added `scripts/overall_cleanup_browser.py`; replaced comparison export's `unibox` runtime dependency with local Pillow annotation, flattening, stitching, PNG, and GIF paths; removed `unibox_missing` as a normal export failure mode; added focused tests for Pillow-only operation, import-time no-`unibox`, annotation wrapping, and alpha/transparency flattening.
- [x] 2026-05-25 04:26 UTC: Sprint 1 validation passed: `python -m ruff check src/lenslet/web/comparison_export.py tests/test_compare_export_endpoint.py scripts/overall_cleanup_browser.py`; `pytest -q tests/test_compare_export_endpoint.py` with 24 passed; `python scripts/overall_cleanup_browser.py --output-json /tmp/lenslet-overall-cleanup-sprint1.json`; `python scripts/lint_repo.py`.
- [x] 2026-05-25 04:26 UTC: Sprint 1 cleanup and review completed. The code-simplifier pass found and applied only Tier 1 cleanup. Code review found alpha, label, import-guard, and browser-evidence gaps; fixes landed and the final review reported no remaining actionable issues.
- [x] 2026-05-25 04:40 UTC: Sprint 2 implementation slice added `OCR-3` adaptive row geometry tests, hardened `computeAdaptiveRows` for bounded justified rows and contained panorama/tall outliers, threaded a narrow `fit="contain"` thumbnail hint, renamed visible `Masonry` copy to `Justified rows` while preserving the internal `adaptive` and `layout:masonry` values, and extended `scripts/overall_cleanup_browser.py` with Sprint 2 adaptive geometry evidence.
- [x] 2026-05-25 04:40 UTC: Sprint 2 focused validation passed: the new adaptive tests first failed against the old greedy implementation (`10:1` row collapsed to `76px`, tall outlier mixed into a normal row, wide leftover overfilled a row), then passed after the row-breaker change; `cd frontend && npm run test -- src/features/browse/model/__tests__/adaptive.test.ts src/shared/ui/toolbar/__tests__/Toolbar.test.tsx src/shared/ui/toolbar/__tests__/ToolbarMobileDrawer.test.tsx`; `cd frontend && npm run test`; `cd frontend && npm run build`; packaged frontend assets synced into `src/lenslet/frontend/`; `python scripts/overall_cleanup_browser.py --output-json /tmp/lenslet-overall-cleanup-sprint2.json`; `python -m ruff check scripts/overall_cleanup_browser.py scripts/gui_jitter_probe.py`; `python scripts/lint_repo.py`; `git diff --check`.
- [x] 2026-05-25 04:42 UTC: User approved generating or restoring `data/fixtures/large_tree_40k` and running the primary Sprint 2 large-tree gate.
- [x] 2026-05-25 04:52 UTC: Sprint 2 primary scale gate passed after approval. The generated/restored ignored fixture at `data/fixtures/large_tree_40k` matched the 40k/10k manifest, and `python scripts/playwright_large_tree_smoke.py --dataset-dir data/fixtures/large_tree_40k --output-json /tmp/lenslet-large-tree-overall-cleanup.json` passed with first grid `4.34s`, hotpath `3974ms`, first thumbnail `4052ms`, max frame gap `350.1ms`, and zero `/file` requests.
- [x] 2026-05-25 04:52 UTC: Sprint 2 cleanup and review completed. The conservative code-simplifier pass applied only formatting cleanup in `scripts/overall_cleanup_browser.py` and reran focused tests, ruff, `git diff --check`, and the Sprint 2 browser script. The fresh code-review pass reported no actionable findings; residual notes were randomized aspect-ratio/property coverage and the browser script's default-target-height assumption.
- [x] Sprint 2 implementation handoff completed.
- [x] 2026-05-25 05:08 UTC: Sprint 3 implementation completed for `OCR-6`, `OCR-7`, and `OCR-8`. Added visual viewport bounds for fixed menu/preview surfaces; changed selection dropdown options to `listbox`/`option` semantics while keeping context/theme command menus on `menu` roles; moved toolbar filter placement to the shared clamped fixed-position path; and replaced hover preview full-file fetching with an abortable direct `/thumb` request lifecycle that rejects stale responses and owns object URL cleanup.
- [x] 2026-05-25 05:08 UTC: Sprint 3 validation passed before cleanup/review: focused tests for menu bounds, theme positioning, hover preview lifecycle, and preview API; `pytest -q tests/test_playwright_large_tree_smoke.py`; `python -m ruff check scripts/overall_cleanup_browser.py scripts/playwright_large_tree_smoke.py`; `cd frontend && npm run test`; `cd frontend && npm run build`; packaged frontend assets synced into `src/lenslet/frontend/`; `python scripts/overall_cleanup_browser.py --output-json /tmp/lenslet-overall-cleanup-sprint3.json`; `python scripts/lint_repo.py`; and `git diff --check`.
- [x] 2026-05-25 05:15 UTC: Sprint 3 cleanup and review completed. The code-simplifier pass made no edits and reran focused tests, py_compile, ruff, and diff checks. The fresh code-review pass found two lifecycle gaps: visual viewport event listeners while menus are open, and hover preview cancellation on scroll. Both fixes landed, the reviewer confirmed no remaining actionable findings, and final gates passed again: focused tests, `pytest -q tests/test_playwright_large_tree_smoke.py`, `cd frontend && npm run build`, packaged frontend sync, `python scripts/overall_cleanup_browser.py --output-json /tmp/lenslet-overall-cleanup-sprint3.json`, `cd frontend && npm run test`, `python scripts/lint_repo.py`, and `git diff --check`.
- [x] Sprint 3 implementation handoff completed.
- [ ] Sprint 4 implementation handoff pending.
- [ ] Sprint 5 implementation handoff pending.


## Artifacts and Handoff


Input reviews:

1. `docs/20260525_overall_cleanup_review.md`
2. `docs/20260525_responsive_layout_structural_plan.md`
3. `docs/20260524_resizing_interactions_review.md`

Subagent discovery notes incorporated:

1. Browse/grid/hover/menu scan recommended testing adaptive geometry first, extracting hover preview narrowly, hardening local menu primitives before any dependency, and avoiding broad AppShell/VirtualGrid/styles splitting.
2. Viewport/viewer/dialog/export scan recommended a tiny visible-viewport helper, pure transform math before hook migration, a focused modal primitive only for viewer/compare first, and resolving export by making Pillow primary.
3. Plan review recommended five sprints, incremental browser assertions, explicit removal of `unibox_missing`, concrete adaptive bounds, a direct abortable `/thumb` hover path, large-tree validation after adaptive changes, and measured bundle splitting last.

Implementation handoff notes:

1. Sprint 1 closed `OCR-1` and `OCR-2`. Browser evidence lives at `scripts/overall_cleanup_browser.py` and the latest Sprint 1 output path was `/tmp/lenslet-overall-cleanup-sprint1.json`.
2. Comparison export now uses Pillow-only helpers for annotation, RGB/alpha flattening, horizontal PNG stitching, and GIF frame preparation. `unibox_missing` is no longer part of the normal export contract.
3. Sprint 1 did not touch frontend source or packaged frontend assets, so `src/lenslet/frontend/` was not regenerated.
4. Sprint 2 should start with `OCR-3`, then `OCR-4`, then `OCR-5`: define the adaptive row geometry tests before changing row behavior, harden row math, and rename the visible mode label to `Justified rows`.
5. Keep `adaptive` as the internal persisted value unless implementation proves a hard cutover is simpler; change only the user-facing label in Sprint 2.
6. Keep full-file fetches for explicit viewer/compare paths only. Hover preview should use thumbnail or preview media in Sprint 3.
7. Do not add a dependency for grid, menu, dialog, or gesture behavior without sign-off and a package decision note.
8. Regenerate `src/lenslet/frontend/` after UI bundle changes and state that regeneration in sprint handoff.
9. Sprint 2 closed `OCR-3`, `OCR-4`, and `OCR-5`. Adaptive row geometry now has focused tests for missing dimensions, panorama and tall outliers, one-image rows, mixed screenshots, and last-row leftovers. `computeAdaptiveRows` keeps rows bounded, contains panorama/tall outliers, and threads a narrow `fit="contain"` hint into rendered thumbnail cards. The visible layout label is now `Justified rows` while preserving the internal `adaptive` and `layout:masonry` values.
10. Sprint 2 evidence paths: `/tmp/lenslet-overall-cleanup-sprint2.json`, `/tmp/lenslet-overall-cleanup-sprint2-cleanup.json`, and `/tmp/lenslet-large-tree-overall-cleanup.json`. The ignored generated fixture remains at `data/fixtures/large_tree_40k` for repeat primary-gate runs unless cleaned locally.
11. Sprint 2 regenerated packaged frontend assets under `src/lenslet/frontend/` after the UI label and adaptive rendering changes.
12. Sprint 3 closed `OCR-6`, `OCR-7`, and `OCR-8`. Fixed surfaces now use `getVisibleViewportBounds()` and shared clamping against visual viewport offsets, and open surfaces subscribe to both window and visual viewport resize/scroll events. Sort/layout dropdowns expose `listbox`/`option` roles, while context and theme settings menus remain command menus. Hover preview now renders a bounded fixed preview surface from direct abortable `/thumb` requests, with stale-response guards, object URL cleanup, and scroll-start cancellation.
13. Sprint 3 evidence path: `/tmp/lenslet-overall-cleanup-sprint3.json`. The latest run recorded sort/filter/theme/context surfaces within visible bounds, sort dropdown `optionCount=5` and `menuItemCount=0`, hover preview `thumb_request_count=1` with `file_request_count=0`, and `scroll_cancel_preview_count=0`.
14. Sprint 3 regenerated packaged frontend assets under `src/lenslet/frontend/` after UI behavior changes.

Current planning transcript:

1. `git status --short` at Sprint 1 start showed this new plan and `docs/20260525_overall_cleanup_review.md` as untracked documentation files.
2. Sprint 1 implementation files: `src/lenslet/web/comparison_export.py`, `tests/test_compare_export_endpoint.py`, and `scripts/overall_cleanup_browser.py`.
3. Sprint 1 plan-loop files updated: `docs/20260525_overall_cleanup_execution_plan.md` and `docs/ralph/20260525_overall_cleanup_execution_plan/progress.txt`.

Revision note:

This plan incorporates the required plan-writer review by replacing the oversized eight-phase draft with five browser-verifiable sprints, limiting visual viewport work to visible bounds, making the comparison export contract explicit, defining adaptive layout acceptance more concretely, requiring a direct abortable hover-preview path, and moving bundle splitting behind behavior fixes.
