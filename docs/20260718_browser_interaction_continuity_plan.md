# Browser Interaction and Visual Continuity Plan


## Outcome + Scope Lock


After implementation, Lenslet’s browse workspace has one stable left-panel width across Folders, Metrics, and Derived Score; Metric dropdowns use the Lenslet scrollbar in Edge on Windows; Ctrl/Cmd+wheel over the gallery changes thumbnail size without invoking browser zoom; successful inspector and Viewer image changes hand off between decoded images without a blank frame while failed replacements show an explicit target error; and browse-query changes avoid fast empty flashes without leaving stale content on screen during slower work.

This document is a focused follow-up to the completed [table query and annotation latency execution plan](./20260717_table_query_annotation_latency_execution_plan.md). The repository has no `PLANS.md`; this plan follows the repository `AGENTS.md`, the active `docs/` scope rules, and the Plan Writer execution-document format. Historical material under `docs/agents_archive/` is not a source of truth.

### Goals


The goals are to make layout and input behavior consistent, make decoded-media replacement atomic from the user’s perspective, and introduce a bounded browse-presentation transition that responds to actual request latency. The initial tunable threshold is 200 milliseconds: a target that is already cached or resolves within that grace window replaces the current gallery directly. While an unresolved target is inside the grace window, the previous gallery remains visible but inert. If the target is still unresolved at expiry, Lenslet retires the previous gallery and shows an explicit current-scope loading surface until success, empty success, or failure. Baseline and post-change painted-frame traces must confirm that the value hides fast flashes without making navigation feel stalled; changing the one named constant after evidence is a tuning edit, not an invitation to add source classifiers or latency prediction.

### Non-goals


This work does not change backend APIs, query semantics, storage, virtualization algorithms, ranking mode, hover-preview cancellation, Compare’s existing thumbnail fallback, or collaboration/persistence behavior. It does not add a global state library, a generic animation framework, a source-type latency predictor, cross-fades throughout the product, or compatibility handling for the three retired sidebar widths.

### Approved behavior


The user approved a 360-pixel preferred left width, one fresh persisted shared-width key, deletion of unused historical width values, and gallery-only modifier-wheel capture. Both Control and Meta modified wheel input over the gallery are approved to change the existing thumbnail-size control; ordinary wheel input and Viewer/Compare wheel behavior must remain unchanged.

The user also approved temporary retention of the previous gallery, provided it does not feel stuck. The proposed balance is the staged policy above: immediate replacement for cached/fast results, an initial grace ceiling of 200 milliseconds of inert prior content, then an explicit loading surface rather than an indefinite stale gallery or a raw blank page. The exact threshold remains evidence-tunable. Inspector continuity and the related Viewer decode handoff are in scope.

Metric dropdown styling is approved for the two shared `Dropdown` panel render paths, which cover the reported Edge/Windows Metric dropdown and intentionally make only consumers of that shared component consistent. Other `.dropdown-panel` owners are not implicitly in scope. A global scrollbar rewrite is not approved.

### Requires further sign-off


Sign-off is required before retaining prior gallery content beyond the bounded grace window, making retained content interactive, changing the 80–500 thumbnail-size range or 10-pixel step, capturing modifier-wheel outside the gallery, adding source-specific timing heuristics, changing backend/cache contracts, or creating a shared media subsystem broader than the smallest inspector/Viewer handoff needed by the evidence.

### Deferred


Compare, hover preview, ranking, mobile-only motion polish, and unrelated unstyled overflow owners are deferred unless a new failing painted-frame reproduction shows that one of them violates the same accepted continuity invariant. General UI animation or skeleton redesign is also deferred.


## Context


The worktree was clean when discovery began. Read-only codepath discovery and a live Chromium inspector probe were completed; no product files were changed. The current probe passes, which demonstrates a coverage gap rather than absence of the reported problem.

The Metric “Show all” virtual list already has `scrollbar-thin` in `frontend/src/features/metrics/components/VirtualFieldList.tsx`, and the shipped CSS applies it in Chromium. The reported Edge/Windows issue instead matches the shared `.dropdown-panel`, whose overflow owner in `frontend/src/styles.css` has no Lenslet scrollbar class. The fix should therefore style the actual shared dropdown owner and add a live computed-style assertion against a 300-metric dropdown.

`frontend/src/app/layout/useSidebars.ts` currently owns three preferred widths and three storage keys: 240 pixels for Folders, 320 for Metrics, and 520 for Derived Score. At a 1440-pixel live viewport with the inspector open, the effective left widths measured 240, 320, and 420 pixels, and the gallery changed width on every tab switch. The responsive policy is already the correct owner of effective clamping; only the preferred left-width ownership needs to become singular.

`frontend/src/app/hooks/useGridPinchResize.ts` handles touch pinch but has no modifier-wheel path. The existing `scripts/browser/overall_cleanup/mobile.py` check explicitly requires Ctrl+wheel not to change thumbnail size, so implementation must reverse that obsolete contract and validate browser-zoom suppression. The actual gallery scroll element, not the surrounding app shell, is the approved event boundary.

The inspector preview in `frontend/src/features/inspector/Inspector.tsx` keys its thumbnail component by path. Every selection therefore unmounts the old image, revokes its object URL, and renders no image until the next blob resolves. Existing inspector painted-frame evidence tracks the preview card but not whether an `<img>` is decoded and painted. Viewer keeps its previous resource during network fetch, but can still hide it when the next blob URL is bound before the new image decodes. Both paths need a latest-request-wins decoded-image promotion invariant, with explicit failure handling and bounded object-URL cleanup.

Browse navigation creates a new infinite-query key for folder, Smart Folder, search, filter, sort, randomization, projection, and derived-rank changes. Until the new response arrives, `useAppDataScope` derives an empty item list, so `VirtualGrid` paints no cells. The existing loading-state copy says it is showing the previous window, but that state is unreachable on these key changes. Cross-folder cleanup also clears selection in a passive effect after the new scope render, allowing a new-scope/old-selection frame. Query truth, metrics, facets, counts, selection, and actions must remain target-owned; only the inert grid presentation may temporarily retain the previous snapshot.

The scope-lock decisions are: Edge on Windows is the scrollbar environment; the affected owner is the individual Metric dropdown; the shared preferred width is 360 pixels and obsolete values should be removed; modifier-wheel applies only over the gallery; and slow transitions must graduate from brief inert retention to an explicit loading state. No additional product questions remain before implementation.


## Plan of Work


### Scope Budget and Guardrails


The budget is three demoable sprints and twelve atomic tickets, with no backend or schema work and no new dependency. Expected production ownership is limited to the shared Dropdown/style primitive, sidebar layout state, the existing grid gesture hook, inspector/Viewer media presentation, AppShell/data-scope presentation wiring, and the smallest supporting model helpers. Test and browser-harness edits may touch the existing sidebar, overall-cleanup, jitter/painted-frame, responsive-geometry, viewer-probe, annotation-latency, and GUI-smoke areas.

The debloat target is one left-width state and one persisted key in place of three states, setters, defaults, and keys; removal of obsolete per-tool width selection/persistence helpers; deletion of historical width values during one normal startup; and replacement of the old “Ctrl+wheel does nothing” assertion. Use `rg` to prove the retired keys and resolver are gone, and use `git diff --stat` plus dependency manifests to prove no new framework or compatibility layer was added.

The quality floor is path-correct, latest-request-wins behavior; explicit empty/error/loading states; decoded-pixel continuity; object-URL cleanup; accessible busy/inert semantics; responsive clamping; automated Chromium interaction evidence; and a real Windows Edge visual gate for the platform-specific scrollbar report. The maintainability floor is one clear owner for each invariant, focused pure tests where state transitions are subtle, and live browser evidence for painted behavior. The complexity ceiling forbids source classifiers, moving latency averages, speculative shared media architecture, global scrollbar selectors, or query-cache redesign unless the approved primary scenario cannot pass without one and the user signs off.

While implementing every sprint, update this document continuously, especially the Progress Log, affected-file notes, decisions, validation results, and risks. After each completed sprint, add a concise handoff in Artifacts and Handoff. For minor script-level uncertainties such as exact helper placement, follow the approved behavior and existing ownership to maintain momentum; record the choice, finish the sprint, then ask for clarification and apply any requested follow-up adjustment.

Every substantive ticket must use the `better-code` skill before and during implementation. The implementing agent must restate acceptance criteria, core invariants, the smallest robust approach, and the evidence that will prove the ticket. Apply Karpathy-style execution guardrails to every substantive code ticket: state material assumptions and ambiguous interpretations before coding; stop if an ambiguity changes behavior; prefer the smallest non-speculative change; touch only lines tied to the request, invariants, or verification; remove only unused code introduced or made obsolete by this change; and attach a concrete verification check to each edit.

Delegate bounded codepath or validation discovery early when it reduces context load. Let the subagent finish useful work. If it is still running after ten minutes, request a brief progress update and the reason more time is needed, then keep waiting. Before forty minutes have elapsed, do not replace the subagent with assumptions or manual review. A documented manual fallback is allowed only after forty minutes without a usable response or with explicit user approval. Cleanup and review gates below are always blocking.

### Gate routine for every ticket


0. Plan gate (fast). Restate the ticket goal, observable acceptance criteria, material assumptions/ambiguities, and intended files. If the ticket is substantive, invoke `better-code` and name the core invariants, smallest robust approach, and required evidence. Stop and ask if an ambiguity would change approved behavior.

1. Implement gate (correctness-first). Implement one coherent slice, avoiding speculative features, one-off abstractions, unrelated cleanup, and broad refactors. Run the ticket’s focused unit/type/browser check and inspect the diff before declaring the slice complete.

2. Cleanup gate. After the complete sprint passes its focused primary scenario, run the blocking code-simplifier routine below against only that sprint’s diff.

3. Review gate. After cleanup finishes, run the blocking review routine below against the post-cleanup ship diff, resolve findings, and rerun affected evidence and review as required.

### code-simplifier routine


After each complete sprint, spawn a subagent and instruct it to use the `code-simplifier` skill on the current sprint diff. Start with non-semantic cleanup only: formatting/lint autofixes, obvious dead code introduced or exposed by the sprint, small readability edits that preserve behavior, and comments/docstrings that state what is already true. Semantic timing, media ownership, query identity, selection, cache, or event changes require explicit approval and revalidation.

Do not interrupt, repurpose, or terminate the cleanup agent to save time. If it is still running after ten minutes, request a brief progress update and continue waiting. Use manual cleanup only after forty minutes without a usable response or with explicit user approval. If the cleanup agent is unavailable or cannot launch, stop and ask the user for an alternative cleanup/review path.

### review routine


After cleanup, spawn a fresh agent and request a `code-review` review of the post-cleanup ship diff using the best available model with `reasoning_effort` set to `medium`. Instruct it to be constructively adversarial: actively look for failure paths, weak validation, scope creep, stale-path content, event-listener leaks, object-URL leaks, inaccessible transitional content, layout/anchor movement, and code that should be removed or simplified.

Do not interrupt, repurpose, or terminate the review agent. Treat review as blocking. If it is still running after ten minutes, request a brief progress update and keep waiting. Before forty minutes have elapsed, do not substitute self-review, guess findings, make fixes based on imagined feedback, or close the gate without explicit user approval. Manual review is a fallback only after forty minutes without usable output or with explicit approval. If review cannot launch, stop and ask for another review path. Resolve every red flag with a fix and evidence, rerun review when needed, or ask the user rather than overriding the concern optimistically.

### Sprint Plan


1. Sprint 1 — Stable controls and layout. Goal: eliminate left-panel geometry changes, style the confirmed dropdown owner, and make gallery modifier-wheel drive the existing Size control. Demo: Folders, Metrics, and Derived Score keep the same width and grid geometry before and after one resize/reload; the 300-metric dropdown has the Lenslet scrollbar in Windows Edge; Ctrl/Meta+wheel over the gallery changes Size while ordinary wheel still scrolls.

   1. **S1-T1: Style the shared dropdown overflow owner.** Add the existing Lenslet scrollbar primitive to both shared `Dropdown` panel render paths rather than creating Metric-only CSS or a global rule. This intentionally covers only consumers of the shared component; do not alter other `.dropdown-panel` owners. Make the primitive theme-correct if the Windows Edge visual check exposes a contrast defect, but do not redesign unrelated scrollbar dimensions. Validation: a focused component check proves both panel render paths receive the class; the 300-metric Chromium fixture asserts computed thin width, custom thumb/track styling, and visible overflow on the actual Metric dropdown as a proxy; and a Windows Edge screenshot/visual check confirms the rendered scrollbar in every supported Lenslet theme.

   2. **S1-T2: Hard-cut sidebar width ownership to one preference.** Replace the three left states, defaults, storage keys, and active-tool mutation branches with one lazily initialized 360-pixel preferred width and one fresh key such as `leftW.shared`; keep the existing responsive policy as the only effective clamp. On successful storage access, remove `leftW.folders`, `leftW.metrics`, `leftW.derived`, and any unused historical `leftW` value. Do not migrate them. Validation: helper tests cover valid/invalid shared reads, pruning, persistence, and right-width isolation; `rg` finds no retired production key/resolver use.

   3. **S1-T3: Unify gallery resize gestures.** Extend and rename the existing pinch-resize hook as needed so the actual gallery scroll owner captures non-passive Ctrl/Meta+wheel, calls `preventDefault()` synchronously, and routes accumulated wheel deltas through the existing AppShell `handleGridItemSizeChange` callback used by the toolbar slider, including its anchor/context restoration and persistence behavior. Wheel-up increases thumbnail size and wheel-down decreases it. Reuse one exported 80/500/10 size contract, flush a wheel burst at most once per animation frame without dropping sub-step deltas, and keep the handler disabled for Viewer/Compare. Validation: pure tests cover modifier detection, direction, accumulation, bounds, coalescing, and unmodified events; focused hook tests prove listener cleanup and gallery-only targeting; reload and top-visible-path checks prove persistence and anchor stability.

   4. **S1-T4: Lock live geometry, scrollbar, and wheel behavior.** Update the responsive/overall-cleanup browser helpers and invert the obsolete Ctrl+wheel assertion. In one live desktop scenario, switch all three tabs, resize from one tab, switch again, reload, and assert left/center widths and top-visible path are stable within one CSS pixel. Hold Control while issuing a real Playwright wheel over the gallery, assert Size changes while viewport zoom/geometry does not, then prove ordinary wheel scrolling and Viewer/Compare wheel behavior are unchanged. Record the required Windows 11 Edge visual result separately; Chromium computed CSS cannot by itself prove the native scrollbar rendering. Validation: the focused live scenario and Windows Edge visual gate pass in addition to Sprint 1 secondary gates.

2. Sprint 2 — Atomic decoded-media handoff. Goal: ensure successful image selection/navigation never paints a no-image interval and failed navigation replaces old media atomically with an explicit target error. Demo: delayed and rapid inspector/Viewer navigation displays a decoded previous-or-target image during successful replacement, promotes only the latest target, and ends in an explicit current-path ready or error state.

   1. **S2-T1: Make painted-frame evidence observe decoded media.** Extend the existing generic frame capture only enough to record visible image presence, `complete`, `naturalWidth`, current source, declared path identity, and explicit target error. Encode the exact invariant: after decoded A, every intermediate frame of a successful A→B replacement visibly presents decoded A or decoded B and the sequence ends on decoded B; on definitive B failure, A may disappear only in the same frame that an explicit B error appears, and the final frame must not retain A. Initial loading with no prior decoded image is excluded. Add failing pure-summary fixtures for each violation, stale final identity, and replacement with no post-action frame. Keep textual stale-path checks strict outside the media surface. Validation: the new fixtures fail under the pre-fix inspector behavior and all existing painted-frame tests remain meaningful.

   2. **S2-T2: Implement the inspector thumbnail handoff.** Remove the keyed blanking lifecycle and give the inspector preview a local, stable, identity-aware handoff owner that keeps the last decoded thumbnail until the latest target decodes, atomically promotes the target, ignores superseded responses, and revokes replaced URLs only after promotion. A definitive current-target error must atomically retire misleading old media and show a bounded explicit error/retry state. Do not change the shared `useBlobUrl`/resource revocation contract used by ThumbCard or Compare unless a proven dependency requires it and those consumers are added to validation with user sign-off. Validation: focused resource/state tests cover A→B, A→B→C, cached B, rejected B, unmount cleanup, and URL revocation; the inspector frame probe satisfies the success and failure invariants from S2-T1.

   3. **S2-T3: Close Viewer’s decode-stage gap without broad media refactoring.** Use the same invariant with narrow Viewer-local URL leasing/promotion; share only a small presentation helper if doing so demonstrably removes duplicated state logic without changing the shared ThumbCard/Compare resource semantics or coupling Viewer transforms/direct URLs to inspector thumbnails. Keep the previously decoded Viewer resource visible while the target URL fetches and decodes; bind target identity separately, then promote without a zero-opacity/no-old-image gap. Preserve zoom reset, direct-to-proxy fallback, navigation, and error behavior. Validation: component tests cover network-pending, decode-pending, definitive error, and supersession phases; the Viewer browser probe permits a declared previous resource only during transition, requires decoded final target identity on success, and requires explicit target error with no old media on failure.

   4. **S2-T4: Promote decoded-media continuity into normal GUI acceptance.** Extend the existing inspector selection loop with delayed thumbnail responses and add a bounded Viewer navigation phase. For successful replacement, assert each intermediate frame visibly presents decoded previous or target media and the final frame is decoded target media. For definitive target failure, assert old media disappears only with the explicit target error and is absent from the final frame. Also assert rapid navigation settles on the latest path and request counts/object URLs remain bounded. Validation: the standalone jitter probe and default GUI acceptance consume the same structured result and pass without a close/reopen workaround.

3. Sprint 3 — Bounded browse-presentation continuity. Goal: make all semantic gallery changes steady when fast and explicitly busy when slow, without letting prior results act as target truth. Demo: representative folder and same-scope query changes never paint a fast empty flash; focused wiring tests cover every semantic trigger; prior cells are inert only for the configured grace; slow and terminal targets show their correct states; and rapid A→B→C navigation can settle only on C.

   1. **S3-T1: Add one grid-only presentation state machine.** Define the smallest pure model/hook with `steady`, `grace`, and `loading` phases keyed by the canonical target browse identity. It may retain a last successful grid snapshot for at most the named 200-millisecond grace, but must never feed old items into target counts, metrics, facets, selection, inspector, Viewer navigation, actions, or query cache. Cached/resolved targets commit immediately; empty success and failure are terminal target states; timers and rapid supersession are latest-target-wins. Validation: fake-clock tests cover fast, boundary, slow, empty, error, A→B→C, unmount, and no-minimum-display-delay behavior.

   2. **S3-T2: Repair the proven scope-reset ordering without a navigation abstraction.** First add a failing frame/state reproduction for the statically identified new-scope/old-selection interval. Then move the existing scope-owned selection/viewer/compare/context reset before target-scope commit only in the handlers proven by that reproduction, preserving explicit deep-linked Viewer targets and current history semantics. Do not consolidate navigation behind a new action or rewrite the router. Validation: the focused reproduction passes, direct and history navigation retain parity, explicit Viewer preservation remains covered, and `git diff` shows no new routing layer.

   3. **S3-T3: Wire all semantic browse changes through the presentation boundary.** Provide the canonical request identity and target query status from the existing data-scope owner, pass only presentation items/status to `VirtualGrid`, and mark grace content inert and `aria-busy`. Disable selection, context menu, hover preview, load-more, metric-rail jumping, and viewer opening for retained cells. At grace expiry replace them with the existing Lenslet loading surface rather than raw whitespace; on target success, empty, unsupported, or error, commit that state atomically. Validation: focused AppShell/data-scope tests prove query truth remains target-owned and retained cells cannot trigger actions.

   4. **S3-T4: Add a representative navigation/query painted-frame gate.** Extend the GUI fixture with populated sibling folders and controllable query delay. Exercise one folder scope change below grace and above grace, one same-scope query mutation, one rapid A→B→C sequence, and one terminal empty-or-error target; cover the other terminal branch in focused state tests. Assert no zero-cell frame before grace expiry, explicit loading after expiry, inert retained content, correct terminal retirement, latest-target settlement, stable gallery shell geometry, and no stale inspector/Viewer activation. Use focused identity/wiring tests—not a combinatorial live matrix—to cover parent/back/hash, Smart Folder, search, filter, sort, randomization, projection, and derived-rank triggers. Validation: default GUI acceptance passes this structured scenario and the full Sprint 3 hierarchy below.


## Validation and Acceptance


Primary gates exercise the user-reported path in a live browser. Secondary gates are faster proxies and cannot close a sprint by themselves.

### Primary acceptance


1. Sprint 1 primary has two required parts. On Windows 11 Edge, open the actual 300-metric dropdown in every supported Lenslet theme and record a screenshot/visual check showing the Lenslet scrollbar rather than the Windows default. Separately run the automated Chromium fixture and updated responsive/overall-cleanup scenario: computed dropdown styling must be present; tab switching and shared resize/reload must not change effective left/center geometry by more than one CSS pixel; real Ctrl+wheel over the gallery must change Size without changing viewport zoom; Meta-modified synthetic coverage must match; ordinary scrolling and overlay zoom must still work. The Chromium computed-style check is a proxy and cannot close the platform-specific visual gate.

       python -m scripts.browser.annotation_latency.acceptance --rows 2000 --metrics 300 --rated 300
       python -m scripts.browser.gui_smoke.acceptance

2. Sprint 2 primary: run the inspector jitter probe with delayed/rapid selections and the Viewer phase promoted into default smoke. For successful A→B replacement after decoded A, every intermediate frame must visibly present decoded A or B and the sequence must end on decoded B. On definitive B failure, A may disappear only in the same frame that explicit B error appears and must not survive the final frame. Initial loading without prior media is excluded. There must be no object-URL/request growth across the bounded loop.

       python -m scripts.browser.gui_jitter.probe --scenario inspector --browser-timeout-ms 12000
       python -m scripts.browser.gui_smoke.acceptance

3. Sprint 3 primary: run the representative delayed folder/query scenario through default GUI acceptance. Cached and sub-grace results must swap without an empty frame; over-grace work must show an explicit loading state; retained cells must be inert; the selected terminal target and A→B→C sequence must settle correctly. Focused tests cover the other terminal branch and every remaining semantic trigger.

       python -m scripts.browser.gui_smoke.acceptance

4. Overall primary: on the standard fixture at a 1440-pixel viewport, perform Folders → Metrics → Derived → resize → Folders, Ctrl+wheel and ordinary wheel, image 1 → image 2 in Inspector and Viewer, one sub-grace folder change, one over-grace folder change, one same-scope query change, and rapid A→B→C. The flow must satisfy geometry, decoded-media, inertness, timing-phase, and latest-target assertions without manual waits that hide intermediate frames. Terminal empty/error behavior remains covered by the Sprint 2/3 targeted primary cases and focused tests rather than duplicating every branch here.

### Secondary acceptance


1. Run focused frontend tests for sidebar persistence/layout, gesture policy, media presentation/resources, loading/presentation state, routing/selection, and AppShell data ownership.

       cd frontend
       npm test -- src/app/layout/__tests__/useSidebars.test.ts src/app/layout/__tests__/responsiveLayoutPolicy.test.ts
       npm test -- src/features/viewer/__tests__/viewerPresentation.test.ts src/features/media/__tests__/originalImageResource.test.ts
       npm test -- src/app/model/__tests__/loadingState.test.ts src/app/hooks/__tests__/useAppDataScope.test.ts

   Include a shared-Dropdown render-path test and Chromium computed-style assertion for the overflowed Metric dropdown. These are secondary evidence for Windows rendering, not a replacement for the Edge visual gate.

2. Run painted-frame and browser-helper unit suites, including malformed/failure fixtures.

       python -m pytest -q tests/scripts/test_painted_frames.py tests/browser/test_browser_probe_helpers.py tests/browser/test_browser_harness_helpers.py

3. Run the full frontend suite, TypeScript/build, synchronize the shipped bundle, repository lint, and diff hygiene after each sprint. Do not copy failed build output.

       cd frontend
       npm test
       npx tsc --noEmit
       npm run build
       cd ..
       rsync -a --delete frontend/dist/ src/lenslet/frontend/
       python scripts/lint_repo.py
       git diff --check

4. Confirm the hard cut and scope ceiling mechanically.

       rg -n "leftW\.(folders|metrics|derived)|getLeftSidebarStorageKey" frontend/src scripts tests
       git diff --stat
       git diff -- frontend/package.json frontend/package-lock.json pyproject.toml

Sprint completion is honest only when its primary browser scenario passes. A passing unit suite, settled-DOM snapshot, or final-path assertion cannot substitute for painted-frame evidence in the reported interactions.

### Sprint 1 iteration 1 evidence


The automated Chromium portion passes. The 300-metric dropdown computed `scrollbar-width: thin`, a non-auto thumb/track color, a styled thumb, and real overflow (`418px` client height versus `10506px` scroll height). The focused stable-controls scenario held left/center geometry at `360/800px` across Folders, Metrics, and Derived, then at `405/755px` after resize across both tab switches and reload. The top-visible identity stayed fixed, only `leftW.shared=405` remained, Ctrl+wheel changed Size `220→230`, Meta+wheel changed it `230→220`, ordinary wheel scrolled to `480px`, and visual viewport scale/app geometry remained unchanged.

The default GUI acceptance passed. Full secondary evidence also passed: 574 frontend tests, TypeScript, the production build, 83 focused Python/browser-helper tests, and repository lint. `src/lenslet/frontend/` was regenerated only after a successful build. The broader responsive-geometry run reached a pre-existing mobile Theme Settings menu timeout, and the legacy overall-cleanup `--only-sprint1` bundle reached a pre-existing Viewer focused-control navigation failure after the new stable-controls phase had passed; the new targeted continuity command isolates and passes this sprint’s evidence.

The native Windows 11 Edge visual check has not run in this Linux workspace. Because Chromium computed styles are only a proxy, Sprint 1 and S1-T4 remain open; cleanup and review gates have not started.


## Risks and Recovery


The highest media risk is showing a prior image under current-path text forever after a failed or superseded load. Recovery is explicit identity tracking, target-error retirement, latest-request guards, and a final-path painted assertion. Object URLs are recoverable only through disciplined promotion/revocation tests; do not solve flicker by disabling cleanup.

The highest browse risk is letting retained items contaminate query truth or remain interactive. Keep the presentation snapshot downstream of data scope and upstream only of `VirtualGrid`; target counts/facets/metrics and all actions remain authoritative. A data attribute and inert/aria-busy state make the transition observable. If the state machine cannot be kept grid-only, stop and request approval before broadening ownership.

The 200-millisecond grace may need small evidence-based adjustment for Edge/Windows scheduling. Recovery is changing one named constant after comparing painted-frame traces; do not add adaptive source/history heuristics. The accepted invariant is bounded prior content followed by explicit loading, not the exact initial number.

Modifier-wheel listeners can accidentally become passive, leak, double-apply, or suppress normal scrolling. Keep one listener owner, synchronous prevention only for Ctrl/Meta, cleanup tests, and a live ordinary-wheel check. If real Playwright modifier-wheel cannot prove browser-zoom suppression in the environment, retain the synthetic cancelability assertion and document one manual Edge/Windows confirmation; do not claim automated proof that was not observed.

Shared Dropdown styling can affect menus beyond Metrics. The rollback is a single class removal from the two shared panel nodes; do not introduce global pseudo-element selectors. Shared-width rollback is similarly localized, but the three old values are intentionally deleted and not recoverable through Lenslet after the hard cut.

The remaining Sprint 1 blocker is environmental rather than an automated-code failure: the required native scrollbar visual must be recorded on Windows 11 Edge in Original, Teal, and Charcoal. Do not close the sprint from the passing Chromium computed-style proxy.

Iteration 2 reconfirmed that the execution host is Linux and has no Microsoft Edge executable. The unblock remains a Windows 11 Edge run against the actual 300-metric dropdown in all three themes, with screenshots or an equivalent recorded visual result attached to the sprint evidence. After that result passes, resume at the Sprint 1 cleanup gate; do not substitute another Chromium run or begin Sprint 2 first.

Iteration 3 repeated the capability check with the same result: this Linux host has no Edge executable or Windows environment, so there is still no plan-compliant local action that can close S1-T4. Sprint 2 remains dependency-blocked, and rerunning Chromium would add no acceptance evidence beyond the already passing proxy.

Iteration 4 found no newly attached native-browser evidence and reconfirmed the same host limitation: Linux is the only available environment, with no Edge executable under the checked command paths, `/opt`, or `/usr/bin`. S1-T4 therefore remains externally blocked; product code, cleanup/review gates, and Sprint 2 remain untouched in dependency order.

Each sprint is independently revertible by its ticket commits. Retry is idempotent: rebuild fixtures and frontend assets, rerun the focused failure, then rerun the sprint’s primary gate. Never copy a failed build into `src/lenslet/frontend/`. Preserve unrelated worktree changes and do not use destructive resets.


## Progress Log


- [x] 2026-07-18 UTC — Read Plan Writer, Lenslet, Better Code, and frontend performance guidance; classified this as latency-sensitive rendering with overengineering risk.
- [x] 2026-07-18 UTC — Completed read-only primary and delegated codepath discovery; confirmed separate width ownership, missing gallery modifier-wheel behavior, inspector keyed thumbnail blanking, browse-query empty presentation, and the existing frame-test blind spots.
- [x] 2026-07-18 UTC — Ran the current inspector jitter probe; it passed while omitting decoded `<img>` evidence, confirming the validation gap.
- [x] 2026-07-18 UTC — Locked user decisions: Edge/Windows Metric dropdown, shared 360-pixel width with obsolete-key pruning, gallery-only modifier-wheel, and bounded fast-retain/slow-loading behavior including Viewer.
- [x] 2026-07-18 UTC — Drafted the three-sprint, twelve-ticket execution plan.
- [x] 2026-07-18 UTC — Completed the mandatory constructively adversarial review; incorporated the Windows Edge visual gate, exact success/failure media invariant, local media ownership boundary, accumulated wheel-delta path, evidence-tunable grace, narrow scope-reset repair, and reduced live navigation matrix.
- [x] 2026-07-18 UTC — Started Ralph iteration 1 on Sprint 1 only (S1-T1 through S1-T4). Plan gates lock the change to the two shared Dropdown panels, one 360-pixel shared sidebar preference with hard-cut key pruning, gallery-only modifier-wheel delivery through the existing resize callback and 80/500/10 contract, and focused/live Chromium evidence. The Windows 11 Edge visual gate remains required and will be reported separately if unavailable in this Linux workspace.
- [x] 2026-07-18 UTC — Implemented S1-T1’s shared panel class path: both `Dropdown` listbox and `DropdownMenu` menu panels now use the existing `scrollbar-thin` primitive; focused render/helper tests pass.
- [x] 2026-07-18 UTC — Implemented S1-T2’s hard cut: one lazy `leftW.shared` preference defaults to 360 pixels, the four obsolete left keys are pruned without migration, right-width persistence remains isolated, and the existing responsive clamp is unchanged; focused sidebar tests pass.
- [x] 2026-07-18 UTC — Implemented S1-T3’s production gesture path: the real gallery scroll owner now binds pinch plus non-passive Ctrl/Meta wheel, uses one exported 80/500/10 contract, retains sub-step deltas, coalesces to one update per animation frame, and calls the existing anchor-restoring size callback. Focused policy/binding/cleanup tests and `npx tsc --noEmit` pass.
- [x] 2026-07-18 UTC — Implemented S1-T4’s automated harness slice and regenerated the shipped frontend. Targeted stable-controls Chromium, the 2000-row/300-metric acceptance, default GUI acceptance, full frontend tests/build/typecheck, focused Python helpers, and repository lint pass.
- [x] 2026-07-18 UTC — Committed the validated Sprint 1 implementation/automated slice as `1f66ad0` (`feat: stabilize browse controls and layout`).
- [x] 2026-07-18 UTC — Ralph iteration 2 re-read the canonical plan and found no additional actionable Sprint 1 code task: the host is Linux with no Edge executable, so the required Windows 11 Edge three-theme visual cannot run here. No product files changed, Sprint 1 remains open, and Sprint 2 was not started out of dependency order.
- [x] 2026-07-18 UTC — Ralph iteration 3 reconfirmed the same external gate: this host cannot produce the required native Windows 11 Edge visual evidence. No product or test files changed, Chromium evidence was not redundantly rerun, and later sprints remain untouched.
- [x] 2026-07-18 UTC — Ralph iteration 4 found no attached Windows Edge evidence and reconfirmed the Linux-only host limitation. No product or test files changed, the already-green Chromium proxy was not rerun, and Sprint 1 remains open at S1-T4.
- [ ] S1-T4 — Record the required Windows 11 Edge Metric dropdown visual in Original, Teal, and Charcoal; Chromium computed evidence is green but cannot close this gate.
- [ ] Implementation — Close Sprint 1 only after the Edge visual, then run the blocking code-simplifier and code-review routines and add the sprint handoff.
- [ ] Implementation — Execute Sprint 2 and record focused, primary, cleanup, review, and handoff evidence.
- [ ] Implementation — Execute Sprint 3 and record focused, primary, cleanup, review, and handoff evidence.


## Artifacts and Handoff


The plan document is `docs/20260718_browser_interaction_continuity_plan.md`. The completed predecessor plan is `docs/20260717_table_query_annotation_latency_execution_plan.md`. Discovery identified these primary production owners: `frontend/src/styles.css`, `frontend/src/shared/ui/Dropdown.tsx`, `frontend/src/app/layout/useSidebars.ts`, `frontend/src/app/hooks/useGridPinchResize.ts`, `frontend/src/app/AppShell.tsx`, `frontend/src/app/hooks/useAppDataScope.ts`, `frontend/src/features/inspector/Inspector.tsx`, `frontend/src/shared/hooks/useBlobUrl.ts`, and `frontend/src/features/viewer/Viewer.tsx`.

Baseline evidence before implementation:

    Current preferred left widths: folders=240, metrics=320, derived=520 (420 effective at the measured 1440px layout).
    Current inspector frame probe: passed, 0 reported blank frames, but no decoded image surface was captured.
    Current Metric Show-all virtual scroller: Lenslet-styled in Chromium.
    Current shared Metric dropdown overflow owner: no scrollbar-thin class.
    Current overall-cleanup contract: fails if Ctrl+wheel changes thumbnail size; this assertion is obsolete by approval.

Iteration 1 implementation commit is `1f66ad0`. It owns `frontend/src/shared/ui/Dropdown.tsx`, `frontend/src/app/layout/useSidebars.ts`, `frontend/src/lib/gridItemSize.ts`, `frontend/src/app/hooks/useGridResizeGestures.ts`, the narrow AppShell/Toolbar/persistence wiring, focused tests, and the annotation/overall-cleanup/responsive/viewer browser helpers. The shipped bundle was regenerated from a passing Vite build; current entry asset is `assets/index-BZ3U0WR-.js`. Automated evidence is saved at `/tmp/lenslet-browser-continuity-sprint1.json`, `/tmp/lenslet-browser-continuity-annotation.json`, and `/tmp/lenslet-browser-continuity-gui-smoke.json`.

Next, run Windows 11 Edge against the actual 300-metric dropdown in Original, Teal, and Charcoal and attach the visual result. Once that required primary gate passes, run the blocking code-simplifier routine, then the blocking code-review routine, resolve any findings, rerun affected evidence, and close Sprint 1. The broader responsive run’s mobile Theme Settings timeout is recorded in `/tmp/lenslet-browser-continuity-responsive.json`; the legacy overall-cleanup focused-control failure is unrelated to this slice and must not be relabeled as passing. Do not treat the Sprint 3 200-millisecond value as a performance promise; tune it only from the real painted-frame scenario.

Iteration 4 handoff is unchanged because the blocker is external: attach the three-theme native Windows 11 Edge result before starting cleanup, review, or any Sprint 2 work.

Revision note: 2026-07-18 initial draft incorporates the user’s post-investigation scope decisions and replaces speculative source-aware loading prediction with a minimal actual-latency grace/loading state machine. Adversarial review then narrowed shared-media and routing work, distinguished Chromium proxies from the required Windows Edge visual check, made failure-frame semantics explicit, and reduced combinatorial browser coverage to representative live paths plus focused wiring tests.
