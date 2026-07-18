# Lenslet Frontend UI Stability Execution Plan


## Outcome + Scope Lock


After this plan, Lenslet keeps one coherent settled presentation through query and resource transitions, transient status does not insert surprise layout rows, and fast work completes without painting false empty, idle, zero, or loading states. The reported categorical filter, histogram footer, Derived `Missing`, and Inspector Metadata paths are direct acceptance cases.

This plan implements the confirmed and evidence-gated findings in `docs/20260718_frontend_ui_instability_observations.md` on top of commit `6a42fde`. It preserves the shipped full-population histogram, decoded Ctrl/Meta-wheel thumbnail reuse, 340-pixel default left rail, and 800-millisecond browse grace. It supersedes the older grid-only boundary in `docs/20260718_browser_interaction_continuity_plan.md` only where the audit proved that grid membership, totals, rating aggregates, and metric-rail readiness must commit together. It does not reopen completed predecessor work or inherit that plan's unavailable Windows Edge gate.

The user approved execution of the full remediation program after requesting the Plan Writer format and Ralph launch. The following behavior locks are part of that approval: remove redundant `Active:` text; preserve useful card-local Clear in a permanently reserved slot; keep histogram range/cursor information in one invariant slot; retain selection through search debounce/pending and clear it only when a settled target excludes the item; use a permanently reserved one-line top rail; replace the three native operator/missing selects while preserving freeform categorical entry; and remove opacity-zero entrance motion from shared utility dropdowns. Browse presentation retains the existing 800-millisecond grace. Inspector Metadata alone uses the user's explicit 1,000-millisecond delayed-copy guidance; other fast fallback suppression keeps the existing 800-millisecond token unless live evidence justifies a user-approved change.

No backend API, storage schema, routing contract, runtime dependency, state library, generic presentation store, skeleton framework, popover manager, screenshot-diff framework, or compatibility path is in scope. Native date inputs remain native unless a reproduced instability survives the select cutover. UI-05, UI-18, UI-24, UI-26, and UI-27 receive behavior code only after their ticket reproduces the finding; a valid non-reproduction closes the code portion with evidence. New visible tokens, changed delay values, altered filter semantics, dependencies, backend work, or interactive stale browse content require further sign-off.


## Context


The audit measured a 61.94-pixel categorical card shift, an 11.57-pixel histogram shift, and a false Inspector Metadata idle frame between approximately 39 and 56 milliseconds. The native Derived `Missing` control did not remount or move, making browser/OS popup compositing the likely flash source. The systemic causes are conditional diagnostics in normal flow, consumers reading an unsettled query independently, pending/absent conflation, effect-time restoration, opacity-zero utility mounts, native/app control mixing, variable async shells, and decoded resources that are not atomically associated with labels.

This is rendering- and latency-sensitive work with high overengineering risk. The invariants are: pending is never presented as absent/empty/zero/failed; query membership and query-owned aggregates share one settled identity; same-identity live annotations remain current during retained presentation; transient copy replaces reserved content or overlays it; decoded pixels and visible labels share one identity; and frequent controls are fully painted on their first visible frame. Fixes must preserve keyboard/ARIA behavior, accessible full text for truncated content, reduced motion, full-population histogram shape, and bounded decoded-resource lifetime.

Three audit agents rechecked metrics, browse/Inspector, and shared/responsive codepaths. A mandatory adversarial review then corrected the execution order, narrowed the browse bundle, kept local Clear without geometry insertion, separated metadata idle semantics from source-absence greps, replaced a proposed all-purpose stability framework with focused probe extensions, and split multi-owner tickets.


## Interfaces and Dependencies


The only new cross-component interface is a minimal `PresentedBrowseSnapshot` evolved from the existing `useGridPresentation` owner. It contains target key, presentation epoch, ordered membership/window, query-owned total and rating aggregate inputs, metric-rail readiness, and only the facet readiness proven necessary by a failing trace. It does not snapshot mutable item objects, optimistic star/notes/tags/metric overrides, presence, or collaboration state; those remain live-derived by path against the presented membership.

The snapshot retains the prior settled identity for the existing 800-millisecond grace and makes its browse actions inert/`aria-busy`. A terminal success/empty/error commits atomically. Source, table, workspace/session, or incompatible scope reset invalidates retention immediately. Latest-target guards prevent A-to-B-to-C completion from presenting A or B after C. Filter-free population facets remain outside this bundle so the overall histogram never becomes target-filtered.


## Plan of Work


### Sprint Plan


1. **Sprint 1 — Close the directly reported geometry and metadata failures.** Demo: categorical selection and histogram pointer activity keep their card anchors fixed, and changing the inspected image never paints the autoload-off metadata fallback.

   1. [x] **S1-T1 — Write the canonical continuity contract.** Create `docs/DESIGN_SYSTEM.md` containing the R1-R8 state/geometry/media rules, the approved 800/1,000-millisecond delays, stable slot and utility-motion contracts, decoded identity, reduced-motion/accessibility requirements, and explicit references to evidence-gated findings. Reuse current tokens; do not invent a general visual design system.

   2. [x] **S1-T2 — Add the focused metrics frame trace.** Extend the existing `gui_jitter` probe with a small metrics scenario over the 1,585-row/two-value fixture at 1440x920. Capture only named card/next-control anchors and visible footer/header states for categorical selection and histogram drag/pointer-up/leave. A 390x844 structural overflow/accessibility check is secondary. Do not prebuild instrumentation for later surfaces.

   3. [x] **S1-T3 — Remove redundant metric rows and stabilize the footer.** Delete `Active:` derivations/markup. Keep card-local Clear in an always-present fixed action slot, disabled or visually quiet when inactive. Replace the histogram's range-plus-Cursor second line with one fixed-height no-wrap information slot or non-flow SVG label; accessible full text must remain available. Preserve filter toggling, range clearing, and the top Filters rail.

   4. [x] **S1-T4 — Give Inspector Metadata truthful target semantics.** With autoload on and a target path present, synchronously project target-owned pending while preserving current request/context guards and reserved geometry. Keep `PNG metadata not loaded yet` and `Load meta` only for autoload-off idle. Fast loads swap directly; neutral loading copy may appear only after 1,000 milliseconds. Extend the existing Inspector painted-frame trace with this exact forbidden autoload-on state.

2. **Sprint 2 — Establish atomic browse ownership before count fixes.** Demo: fast/slow filter and sort transitions keep membership, totals, ratings, and metric-rail readiness coherent while live annotations still update.

   1. [x] **S2-T1 — Extract the minimal presented browse snapshot.** Evolve `useGridPresentation`; do not add a second store. Implement the interface and reset boundaries above with pure tests for target epochs, grace expiry, terminal empty/error, and A-to-B-to-C latest-target ownership.

   2. [x] **S2-T2 — Wire query-owned consumers and live entity overlays.** Feed grid membership/window, toolbar totals, rating aggregate inputs, and metric-rail readiness from the snapshot. Keep optimistic annotations/presence live-derived by path and retain browse actions as inert during grace. Include facets only when a focused trace proves a blanking consumer.

   3. [x] **S2-T3 — Make metrics completeness consume settled identity.** Replace `items.length >= filteredCount` as a standalone completeness test with current presentation identity plus terminal query state. Pending must not manufacture `Filtered: 0`; true settled zero remains visible. Keep filter-free population facets outside the snapshot.

   4. [x] **S2-T4 — Prove transitions, mutations, and resets.** Extend the existing grid probe, not a new framework, with sub-800ms/over-800ms filter/sort responses, A-to-B-to-C, optimistic rating during grace, terminal empty/error, and source/scope reset. No frame may mix prior membership with target totals or freeze same-identity annotation changes.

3. **Sprint 3 — Stabilize Derived Score, facets, native selects, and metric shells.** Demo: unsaved Derived edits survive ordinary responses; uncached fields keep target-correct fixed shells; app-owned controls open without card movement or opacity flash.

   1. [x] **S3-T1 — Reset Derived drafts only on semantic change.** Replace referential key-array effect dependencies with a semantic spec/schema token. Equal fresh arrays preserve name/weight/missing/formula drafts; actual spec/schema changes intentionally rehydrate. Add failure-path coverage for invalid saved specs.

   2. [x] **S3-T2 — Keep uncached facet identity and control role stable.** Same-key refetch may retain settled facets; a new uncached field must immediately own its loading shell and never show the previous field's label/data. Prohibit cross-field `keepPreviousData`. Preserve freeform categorical bonus entry with one fixed app-owned combobox-shaped control rather than input-to-Dropdown swapping. Pending, empty, error, and ready remain distinct inside the same outer rectangle.

   3. [x] **S3-T3 — Hard-cut native operator/missing selects and shared dropdown fade.** Replace Derived `Missing` plus Width/Height operator selects with the existing app-owned Dropdown, preserving models, keyboard behavior, and fixed trigger geometry. Remove the shared `.dropdown-panel` opacity/translation entrance; keep `slideDown` while SyncIndicator or another proven consumer still needs it. Evidence-gate SyncIndicator's separate animation.

   4. [x] **S3-T4 — Give metric cards and selection invariant regions.** Make pending/empty/ready plot/list regions share one shell. Move Selected counts/values into reserved headers and existing SVG overlays rather than inserted rows/cards. Prefer invariant virtual-card heights; add scroll-anchor compensation only if the focused trace proves shells insufficient.

   5. [x] **S3-T5 — Stabilize Derived preview and diagnostics without hiding content.** Give mini-histogram, score preview, and diagnostic regions fixed bounded bodies. Preserve all copy through accessible internal scrolling or an existing disclosure pattern; do not invent truncation-only semantics. Validate long formula/error content and the semantic reset path.

4. **Sprint 4 — Make first-paint and top-stack truth deterministic.** Demo: saved settings/responsive structure are correct on the first frame, and filter/search/status changes do not move the gallery.

   1. [x] **S4-T1 — Initialize persisted settings before paint.** Read one validated local-storage snapshot before AppShell state initialization, preserve URL/shared-view precedence, and reduce `usePersistedAppShellSettings` to deferred writes/lifecycle. Remove the late restore effect, ready flag, setter fan-out, and obsolete persistence plumbing only after precedence tests pass.

   2. [x] **S4-T2 — Make responsive truth synchronous.** Replace effect-late `useMediaQuery` state with a `useSyncExternalStore` matchMedia snapshot and deterministic non-browser fallback. Toolbar and AppShell must agree at 390x844, 820x900, and 1440x920 on the first commit.

   3. [x] **S4-T3 — Give GridTopStack real fixed geometry.** Replace zero-height reserves/wrapping transient bands with one reserved single-line horizontally scrollable filter/context rail. Keep chip content keyboard reachable. Put indexing, zoom, off-view activity, and action feedback into its reserved status location or an existing overlay; internal horizontal scrolling is intentional and gallery top/height must not change.

   4. [x] **S4-T4 — Reconcile search selection only on settled membership.** Remove debounce-time clearing. Retain selection/Inspector through debounce and pending, then clear once only when the settled target excludes the path. Attempt UI-05 Compare auto-close through a supported external/programmatic route; add no branch if it cannot be reproduced.

5. **Sprint 5 — Stabilize utility surfaces and persistent layout slots.** Demo: frequent menus are positioned and opaque on their first frame; async status, settings, folders, dialogs, and overflow do not move their primary anchors.

   1. [x] **S5-T1 — Lock Dropdown and ContextMenu geometry.** Reserve Dropdown's trailing check column and above/below placement for one open lifetime. Give ContextMenu a bounded width or measured resize reclamp, chosen from the long-label edge trace. Reuse existing placement functions and add no positioning dependency.

   2. [x] **S5-T2 — Fix Theme Settings first-frame positioning.** Move initial measurement to layout timing, observe panel size as async sections change, add bounded vertical scrolling, and remove the redundant second RAF. Validate every viewport edge.

   3. [x] **S5-T3 — Reserve toolbar, Sync, and status footprints.** Keep item totals and typing/copy feedback in fixed tabular/truncated slots with accessible full text. Evidence-gate removal of SyncIndicator's separate entrance motion. Ranking save status remains in the ranking ticket.

   4. [x] **S5-T4 — Stabilize FolderTree rows and persistent gutters.** Always reserve folder count/action columns and replace one explicit pending child row with terminal children/error. Apply `scrollbar-gutter: stable` only to proven persistent Inspector, FolderTree, and ranking panes; do not alter dropdown/gallery sizing or add JS scrollbar measurement.

   5. [x] **S5-T5 — Bound Similarity dialog growth.** Prepare mode before open, keep fixed header/footer, use a bounded scroll body, and reserve query/status regions. Existing copy and keyboard access remain intact; modal body scroll is intentional motion, while the dialog's outer anchors stay fixed.

6. **Sprint 6 — Close ranking/media and first-use discontinuities with evidence.** Demo: reproduced Compare/ranking/cold-media/boot transitions never put blank or old pixels under new labels and do not show short-lived loading copy.

   1. [x] **S6-T1 — Bind Compare resources and labels to pair identity.** Reproduce with delayed decode and distinct fixtures. If confirmed, atomically swap decoded resources and labels, or retain both old media and labels under an explicit transitioning identity. No speculative query auto-close branch.

   2. [x] **S6-T2 — Stabilize ranking resource and layout ownership.** Reproduce fullscreen navigation and restored tray/save failure. Bind decoded pixels/labels to one target, clamp tray height before paint, and reserve save status. Keep cache/object URL bounds explicit.

   3. [x] **S6-T3 — Fix cold thumbnail reveal only if reproduced.** Filmstrip cold fast scroll first. If harmful pop-in is confirmed, use the smallest per-card neutral shell and decode-before-reveal; do not add cohort batching or gallery-wide preload without new approval and measurements.

   4. [x] **S6-T4 — Unify cold app/ranking boot presentation.** Trace health boot plus ranking module resolution. Fast boot paints no loading copy; slow boot keeps one stable background/shell and may show copy only after 800 milliseconds, rather than boot-loader-to-ranking-loader replacement.

   5. [x] **S6-T5 — Stabilize first Inspector/Compare lazy opens.** Trace cold chunks independently. Idle-prefetch only cheap known chunks and retain one surface-sized shell; fast loads paint no fallback and slow loads reveal copy after 800 milliseconds. Do not create a generic Suspense framework.

### Scope Budget and Guardrails


The approved budget is six sprints and twenty-seven atomic tickets across design/evidence, metrics, browse ownership, Inspector, Derived/facets, first paint/top stack, utility layout, and decoded media/lazy loading. It exceeds the moderate four-sprint heuristic because the user explicitly requested execution of the full 28-finding frontend program; six independently demoable increments are the smallest honest grouping after adversarial review split multi-owner tickets. Each sprint stays at five tickets or fewer. No new package is permitted.

Debloat targets are redundant Active derivations/rows, conditional Clear insertion, the histogram second line, effect-time persisted restoration plumbing, referential draft reset, native operator/missing selects and unused CSS, shared dropdown opacity animation, zero-height reserves, debounce-time selection clear, redundant Theme RAF work, and keyframes proven unused. Stable shells may add markup, but no generic framework may be introduced. Track production additions/deletions with `git diff --stat`.

Every substantive ticket must invoke `better-code` before and during implementation. The code agent states material assumptions/ambiguities, core invariants, smallest robust approach, files, and evidence; touches only lines tied to the request/invariants/verification; avoids speculative features and unrelated cleanup; removes only code made unused by the ticket; and attaches a concrete check to each step. These Karpathy-style guardrails are mandatory.

Update this plan continuously during implementation, especially Progress Log and impacted scope/risk/validation text. After each sprint, add a handoff with files, evidence, residual risks, and next ticket. For minor script-level uncertainty, follow the approved plan, record the choice, ask after the sprint, and apply requested adjustments.

Delegate bounded codepath discovery early when useful. If a subagent is still working after ten minutes, request a progress update and reason; before forty minutes, wait rather than substitute self-review. Manual fallback requires forty minutes without a usable response or explicit user approval. Cleanup/review agents are blocking once launched.

### Gate routine


0. **Plan gate (fast).** Restate goal, acceptance, assumptions/ambiguities, and files before each ticket. Stop if ambiguity changes behavior. For code, invoke `better-code` and restate invariants, smallest robust approach, and evidence.

1. **Implement gate (correctness-first).** Implement the smallest coherent slice without speculative features, one-off abstractions, unrelated cleanup, or broad refactors. Run its focused test or reproduction.

2. **Cleanup gate.** After a sprint's implementation and primary checks pass, run the blocking routine below.

3. **Review gate.** After cleanup, review the post-cleanup ship diff, resolve findings, rerun affected evidence, and only then write the sprint handoff.

### code-simplifier routine


After each sprint, spawn a subagent instructed to use `code-simplifier` on that sprint's changes. Start with formatting/lint, obvious dead code, non-semantic readability edits, and truthful docs/comments. Do not expand into semantic refactors without approval. Do not interrupt or repurpose it; after ten minutes request progress and wait up to forty minutes before documented manual fallback. If unavailable or failed, stop and ask the user for an alternative path.

### review routine


After cleanup, spawn a fresh best-available subagent with medium reasoning effort and instruct it to use `code-review` on the post-cleanup ship diff. It must adversarially inspect correctness, stale identity, layout evidence, resource lifetime, scope creep, weak validation, and removable complexity. Do not interrupt, repurpose, self-review, or proceed while it runs; request progress after ten minutes and wait up to forty minutes. Fix findings and rerun review as needed. If unavailable, failed, or unresolved, stop and ask the user.


## Validation and Acceptance


### Primary acceptance


1. **Sprint 1:** run the focused metrics and Inspector probes. On the 1,585-row fixture, named card/next-control anchors move at most one CSS pixel; no `Active:` row paints; Clear occupies one fixed slot; histogram footer remains one line. With metadata autoload on, fast navigation paints neither idle nor loading copy, and slow navigation paints neutral loading only after 1,000 milliseconds.

       python -m scripts.browser.gui_jitter.probe --scenario metrics --output-json /tmp/lenslet-ui-stability-s1-metrics.json
       python -m scripts.browser.gui_jitter.probe --scenario inspector --output-json /tmp/lenslet-ui-stability-s1-inspector.json

2. **Sprint 2:** the grid probe covers sub/over-grace filter/sort, terminal empty/error, A-to-B-to-C, optimistic rating during grace, and source/scope reset. No frame mixes membership/aggregates, freezes live annotations, or retains across an incompatible reset.

       python -m scripts.browser.gui_jitter.probe --scenario grid --output-json /tmp/lenslet-ui-stability-s2.json

3. **Sprint 3:** the metrics probe covers equal-key draft rerender, semantic schema change, uncached field success/empty/error, native-select cutover, selection, long diagnostics, and virtual scrolling. Target labels/data and control roles remain correct; named card anchors move at most one pixel; accessible full content remains reachable.

       python -m scripts.browser.gui_jitter.probe --scenario metrics --output-json /tmp/lenslet-ui-stability-s3.json

4. **Sprint 4:** focused toolbar/grid cases start cold at 390x844, 820x900, and 1440x920 with saved settings, then exercise first/last filters, long chips, similarity/status, matching/excluding search, and the supported Compare reproduction. First-frame truth is correct; gallery anchors stay within one pixel; chip horizontal scroll is the intentional exception.

       python -m scripts.browser.gui_jitter.probe --scenario toolbar --output-json /tmp/lenslet-ui-stability-s4-toolbar.json
       python -m scripts.browser.gui_jitter.probe --scenario grid --output-json /tmp/lenslet-ui-stability-s4-grid.json

5. **Sprint 5:** focused toolbar and surface cases repeatedly open edge-positioned menus/settings/modal, grow async content, change totals/typing/copy, hydrate folders, and cross overflow thresholds. First visible utility frames are opaque and clamped; named outer anchors move at most one pixel. Intentional modal-body, child-block, and filter-chip internal scrolling is excluded.

       python -m scripts.browser.gui_jitter.probe --scenario toolbar --output-json /tmp/lenslet-ui-stability-s5-toolbar.json
       python -m scripts.browser.gui_smoke.acceptance

6. **Sprint 6:** visibly distinct delayed resources cover Compare, ranking, cold scroll, cold boot, and first lazy opens. Every label matches decoded resource identity; no blank frame or pre-delay loading copy paints. Evidence-gated non-reproductions are recorded explicitly and receive no behavior code.

       python -m scripts.browser.gui_jitter.probe --scenario grid --output-json /tmp/lenslet-ui-stability-s6-grid.json
       python -m scripts.browser.gui_jitter.probe --scenario inspector --output-json /tmp/lenslet-ui-stability-s6-inspector.json

7. **Overall:** run every independently runnable focused probe plus default GUI acceptance. Do not replace painted-frame evidence with final-DOM assertions or combine all paths into one long shared-state scenario.

### Completed evidence

- **Sprint 1 (2026-07-18):** the 1,585-row/two-value metrics trace recorded 0-pixel categorical-card, histogram-card, and next-control deltas; no `Active:` frame; one invariant Clear slot through apply/clear; and a 16-pixel no-wrap histogram footer through drag, pointer-up/leave, and range clear. The 390x844 secondary structure had zero document overflow and retained an accessible mobile-drawer trigger.
- **Sprint 1 Metadata:** 22 painted target transitions, including all fast paths and slow-request supersession, recorded zero autoload-on idle/loading-copy violations and 0-pixel Inspector anchor movement. The final deliberate 1,250-millisecond response first painted neutral copy at 1,013.7 milliseconds and then settled target-correct content.
- **Sprint 6 (2026-07-18):** distinct delayed media recorded zero mixed-identity and zero mixed-pixel Compare/ranking frames. Compare retained its prior pair for 99 of 107 frames, including 74 frames after a corrupt superseded response; ranking retained decoded image `1` under an explicit target-`2` decode error. The cold thumbnail stayed at zero opacity in an invariant 301-by-256.66-pixel shell until decode. Fast ranking boot painted zero loading-copy frames, slow boot first exposed copy at approximately 800 milliseconds, first-frame restored tray geometry was clamped, and save failure moved no named header control. Independent Inspector/Compare cold chunks retained surface shells, exposed delayed copy at approximately 800 milliseconds, and raised zero page errors.
- **Sprint 1 supporting gates:** 592 frontend tests, TypeScript, 56 painted-frame/browser-helper tests, the default GUI acceptance, repository lint, and `git diff --check` passed. Shipped assets were regenerated from `frontend/dist` into `src/lenslet/frontend/`.
- **Sprint 2 primary evidence (2026-07-18):** the grid trace covered 350-450-millisecond and 1,100-millisecond sort/filter responses, A-to-B-to-C supersession, an optimistic five-star mutation during retained grace, terminal empty/error, an incompatible scope reset, and a delayed same-query source-column generation reset with zero continuity violations. Retained membership, target identity, epoch, toolbar totals, rating aggregates, and metric-rail inertness stayed atomic; pending/error never manufactured zero counts. The live rating aggregate moved from five-star `1` to `0` when the settled Unrated filter excluded that path.
- **Sprint 2 supporting gates:** 601 frontend tests across 110 files, TypeScript, 59 painted-frame/browser-helper tests, the default GUI acceptance, repository lint, and `git diff --check` passed. The final source-reset trace recorded 27 target-owned loading frames and zero grace frames; shipped assets were regenerated and synchronized.
- **Sprint 3 primary evidence (2026-07-18):** `/tmp/lenslet-ui-stability-s3.json` passed over 1,585 rows with 0-pixel named-anchor movement. Uncached categorical success, omitted empty, explicit empty, and terminal error stayed target-owned; incomplete local values did not mask pending/error. A delayed metric changed from histogram to category content while retaining one outer host and exact 384-pixel virtual cards. Selection stayed in reserved headers/SVG overlays, with no inserted summary card.
- **Sprint 3 control/Derived evidence:** Width, Height, and Missing reported zero native selects and first-visible opacity `1`, transform `none`, and animation `none`. The editable value control retained freeform input, closed after pointer selection, and exposed a live `aria-activedescendant`. Equal-schema responses preserved unsaved name/weight/missing/formula state; semantic clear rehydrated; long preview/diagnostic copy remained internally scrollable with 0-pixel outer deltas.
- **Sprint 3 supporting gates:** 617 frontend tests across 111 files, TypeScript, 61 painted-frame/browser-helper tests, the default GUI acceptance, repository lint, and `git diff --check` passed. Mandatory Tier 1 cleanup made formatting-only edits; repeated adversarial review findings were resolved and the final review was clean. Shipped assets were regenerated and synchronized.
- **Sprint 4 primary evidence (2026-07-18):** `/tmp/lenslet-ui-stability-s4-toolbar.json` and `/tmp/lenslet-ui-stability-s4-grid.json` passed with 0-pixel toolbar, top-stack, grid-width, and gallery-anchor deltas. Cold first frames at 390x844, 820x900, and 1440x920 used validated personal settings while URL query/sort state kept precedence, and Toolbar/AppShell responsive structure agreed immediately.
- **Sprint 4 search/top-rail evidence:** matching search retained selection and Inspector through debounce, grace, and loading before settling on the selected path; excluding search cleared only after terminal complete membership. The supported UI-05 route reproduced Compare opened before debounced search: a matching pair stayed open through a 1,100-millisecond response, while an excluding pair stayed open only while pending and closed at definitive empty membership. At 390 pixels the one-line rail stayed 45 pixels high, exposed a keyboard-focusable region, scrolled off-screen Clear all from `0` to `1402` pixels, reset to `0` for a newly introduced zoom status, and brought newly mounted action feedback and similarity context visibly into view at `540` and `568` pixels without moving `gridBodyTop`.
- **Sprint 4 supporting gates:** 624 frontend tests across 111 files, TypeScript, 62 painted-frame/browser-helper tests, the default GUI acceptance, repository lint/file-size guardrails, hard-cut/dependency searches, and `git diff --check` passed. Mandatory Tier 1 cleanup reduced the slice by eight lines; repeated adversarial review closed immutable/mutable entity ownership, commit-phase Compare retention, explicit-clear behavior, context visibility, and decisive matching/excluding evidence before a final clean review. Shipped assets were regenerated and synchronized.
- **Sprint 5 utility-surface evidence (2026-07-18):** `/tmp/lenslet-ui-stability-s5-toolbar.json` passed with 0-pixel maximum named-anchor movement and zero first-visible opacity, transform, animation, or clamping violations. Dropdown reserved all 14-pixel check columns, chose the roomier side, and grew above its trigger from 186 to 322.78 pixels with zero overlap. Theme Settings retained its anchored edges through async growth and internal scrolling. ContextMenu held 8-pixel margins at both a 160-pixel layout viewport and a zoomed 200-by-230 visual viewport.
- **Sprint 5 slot/dialog evidence:** the exact toolbar transition was `18 items` → `1 / 18 items` → `18 items`; toolbar sort, Sync typing/copy, folder parent rows, and ContextMenu busy copy all stayed at 0-pixel deltas. A delayed stale Similarity search neither closed a reopened dialog nor replaced its selected target; its fixed shell/header/footer remained invariant across path, vector, and error states.
- **Sprint 5 Inspector/supporting gates:** after the scoped Inspector gutter exposed a 17.391-pixel Quick View wrap, the fixed one-line accessible value rows restored 0-pixel section deltas across default GUI acceptance and delayed metadata. 635 frontend tests across 114 files, TypeScript, 62 painted-frame/browser-helper tests, the default GUI acceptance, final build/sync, repository lint/file-size guardrails, dependency/hard-cut checks, and `git diff --check` passed. Mandatory Tier 1 cleanup was formatting-only; repeated adversarial findings were resolved and the closure review reported no actionable findings.

### Secondary acceptance


1. Run focused tests per owner, then the full frontend suite and typecheck.

       cd frontend
       npm test
       npx tsc --noEmit

2. Run painted-frame and browser-helper tests.

       python -m pytest -q tests/scripts/test_painted_frames.py tests/browser/test_browser_probe_helpers.py tests/browser/test_browser_harness_helpers.py

3. Build and synchronize shipped assets only after green tests/typecheck, then run hygiene checks.

       cd frontend
       npm run build
       cd ..
       rsync -a --delete frontend/dist/ src/lenslet/frontend/
       python scripts/lint_repo.py
       git diff --check

4. Confirm hard cuts and complexity ceiling with scoped searches. The metadata idle copy is intentionally allowed in autoload-off source and is forbidden only by the autoload-on painted trace.

       rg -n 'Active:' frontend/src/features/metrics/components/CategoricalCard.tsx frontend/src/features/metrics/components/MetricCategoryCard.tsx
       rg -n '<select' frontend/src/features/metrics/components/AttributesPanel.tsx frontend/src/features/metrics/components/DerivedScoreCard.tsx
       rg -n 'persistedSettingsReady' frontend/src/app
       git diff --stat
       git diff -- frontend/package.json frontend/package-lock.json pyproject.toml

Primary browser evidence is authoritative. Unit tests, computed styles, headless final screenshots, and lint cannot replace a failing painted-frame path. Named primary anchors/card shells—not internal glyph rectangles—use the one-pixel contract. For classic-scrollbar behavior, use headed Chromium classic mode when supported; if unavailable, leave that evidence-gated finding open without blocking unrelated confirmed tickets.


## Risks and Recovery


The main correctness risk is stale interaction under retained browse content. Recovery is one observable presentation epoch, inert/`aria-busy` retained membership, live path-based entity overlays, explicit reset boundaries, and latest-target guards. Do not add parallel target/presentation stores or present old data as current.

Stable shells can hide or overflow content if implemented as clipping. Full copy must remain available through accessible internal scrolling, title/description, or an existing disclosure. Named outer anchors are stable; intentional internal scrolling and FolderTree child insertion are not treated as jitter.

Media retention can leak object URLs or show old pixels under new labels. Promotion requires target identity, successful decode, latest-request guards, failure retirement, and cache bounds. A failed/superseded target may not strand prior pixels under current labels.

Sprint 2 resolved the pending `Filtered: 0` semantic frame through nullable target-owned snapshot counts, not local text suppression. Recovery remains the path-based presentation snapshot plus explicit reset identity; do not reintroduce count derivation from a pending target.

Sprint 3 resolved pending/empty/error facet conflation with explicit per-field query ownership plus `absent`/`empty`/`ready` data-source state. Rapid A-to-B-to-C facet completion is not directly raced by the browser probe; query keys and per-field ownership guard the path, and a future failure should extend the existing metrics scenario rather than add another state store.

Sprint 4 resolved first-paint personal-setting and responsive mismatches before commit, and selection/Compare now use committed presentation bases with only mutable live overlays. Refs promote in layout effects; explicit clears intersect retained projections immediately; definitive complete membership owns auto-close. New rail context identities are scrolled into view before paint while the outer 45-pixel geometry remains invariant.

Sprint 5 resolved utility placement against one visible-viewport owner, locks Dropdown side per open lifetime, and observes natural panel growth without trigger overlap. Similarity promotes selection restoration only after current-request acceptance and invalidates pending work on close. Classic-scrollbar gutter rendering remains environment-dependent; DropdownMenu shares the reviewed observer path but its growth is not separately painted. The focused toolbar probe is 1,287 lines and warn-only above the 1,200-line guideline, so Sprint 6 evidence must remain in its planned grid/Inspector owners rather than enlarge it.

Sprint 6 resolves Compare promotion with at most four current decoded identities, connected-element/current-candidate success guards, resource-bound failures, current-path retry gating, and synchronous unsupported ownership. Ranking decodes only the active fullscreen target, retains the last decoded identity on failure, keeps next-instance preload network-only, and clamps restored geometry in the first ready layout effect. The same-origin fixture canvas trace now checks painted RGB values rather than trusting presentation attributes alone. Residual risk is limited to browser/platform decoding outside the covered image fixtures; recovery is to extend `sprint6_evidence.py` with a distinct failing fixture, not add a second media store or unbounded preload.

Shared Dropdown and persistence edits have broad reach. Keep selectors local, preserve URL/shared-view precedence, and revert the individual ticket commit if keyboard behavior, clamping, or persisted ownership regresses. Do not add dependencies as recovery.

Each ticket/sprint is independently committable. Retry is idempotent: recreate the fixture, rerun the focused trace, apply the narrow fix, rerun primary/secondary gates, then regenerate shipped assets. Never copy a failed build. Preserve unrelated changes and avoid destructive resets.


## Progress Log


- [x] 2026-07-18 UTC — Re-read the complete audit and predecessor continuity/latency context; confirmed base `6a42fde` and no product edits in planning.
- [x] 2026-07-18 UTC — Read Ralph Codex, Plan Writer, Better Code, and frontend performance guidance.
- [x] 2026-07-18 UTC — Reused three audit agents for metrics, browse/Inspector, and shared/responsive grouping.
- [x] 2026-07-18 UTC — Drafted the Plan Writer execution document.
- [x] 2026-07-18 UTC — Completed mandatory adversarial review and incorporated sequencing, ownership, atomicity, scope, and validation corrections.
- [x] 2026-07-18 UTC — User explicitly approved execution through Ralph using this Plan Writer format.
- [x] 2026-07-18 UTC — Bootstrapped `docs/ralph/20260718_frontend_ui_stability/` in Codex plan mode with the explicit plan path, shared prompts, ten iterations, and a six-task cap.
- [x] 2026-07-18 UTC — Ralph entered plan iteration 1 with Sprint 1 as the first actionable slice.
- [x] 2026-07-18 UTC — S1-T1 added the narrow R1-R8 continuity, timing, stable-slot, decoded-identity, reduced-motion, accessibility, and painted-frame contract in `docs/DESIGN_SYSTEM.md`.
- [x] 2026-07-18 UTC — S1-T2 added the focused 1,585-row/two-value metrics painted-frame scenario plus the secondary 390x844 structural check.
- [x] 2026-07-18 UTC — S1-T3 removed redundant categorical/metric-class `Active:` rows, reserved Clear action slots, and collapsed histogram range/cursor information into one accessible no-wrap slot while preserving apply/clear behavior.
- [x] 2026-07-18 UTC — S1-T4 made autoload-enabled Metadata synchronously target-pending, delayed visible loading copy by 1,000 milliseconds, preserved autoload-off idle, and extended fast/slow/superseded painted-frame evidence.
- [x] 2026-07-18 UTC — Sprint 1 focused probes, full frontend tests/typecheck, browser-helper tests, default GUI acceptance, build/sync, lint, and diff hygiene passed.
- [x] 2026-07-18 UTC — Mandatory code-simplifier cleanup removed one dead derivation and one duplicate calculation; adversarial review findings were resolved by strengthening fast/superseded timing, range-clear, structural-scope, finding-map, and handoff evidence.
- [x] 2026-07-18 UTC — Ralph iteration 2 entered Sprint 2. The plan gate fixed the implementation boundary at one path-based `PresentedBrowseSnapshot` inside `useGridPresentation`, explicit scope/session/source resets, live entity overlays, nullable pending counts, and the existing 800-millisecond grace; no facets, store, or state framework will be added without failing trace evidence.
- [x] 2026-07-18 UTC — S2-T1 added pure target/reset/epoch resolution around one path-based snapshot, with grace expiry, terminal empty/error, incompatible reset, and A-to-B-to-C latest-target coverage.
- [x] 2026-07-18 UTC — S2-T2 moved grid membership, toolbar totals, ratings, selection projections, and metric-rail readiness onto the presented identity while keeping entity changes live by path and retained interactions inert.
- [x] 2026-07-18 UTC — S2-T3 made metric completeness require a settled current browse target and exposed nullable pending totals, eliminating manufactured `Filtered: 0` and loading `0 items` while preserving truthful terminal empty.
- [x] 2026-07-18 UTC — S2-T4 extended the existing grid scenario with fast/slow sort and filter, optimistic annotation, A-to-B-to-C, terminal empty/error, and scope-reset frame traces; `/tmp/lenslet-ui-stability-s2.json` passed with zero violations.
- [x] 2026-07-18 UTC — Mandatory Tier 1 cleanup made only local formatting changes. Repeated adversarial review closed retained similarity hydration, mutable-only live overlays, presence/population ownership, generation-keyed browse/facet resets, synchronous similarity ownership, stale async selection guards, and stronger ordered frame assertions; the final review reported no actionable findings.
- [x] 2026-07-18 UTC — Sprint 2 final primary trace, 601-test frontend suite, TypeScript, 59 helper tests, default GUI acceptance, build/sync, repository lint, and diff hygiene passed.
- [x] 2026-07-18 UTC — Ralph iteration 3 entered Sprint 3. The plan gate fixed the slice at one semantic Derived draft reset token, explicit existing-query facet states, app-owned fixed-role controls, invariant metric/selection/preview shells, and the existing metrics painted-frame probe; no dependency, presentation store, generic shell framework, or cross-sprint utility work will be added.
- [x] 2026-07-18 UTC — S3-T1 keyed the Derived editor by canonical spec/schema identity, reset all draft surfaces atomically on semantic changes, and preserved malformed saved definitions through backend-none evaluation.
- [x] 2026-07-18 UTC — S3-T2 exposed per-batch field states from the existing facet query, kept settled same-field data during refetch, projected new fields pending immediately, and replaced categorical input/Dropdown swapping with one freeform app-owned combobox.
- [x] 2026-07-18 UTC — S3-T3 hard-cut the three native missing/operator selects, restored trigger-side keyboard selection, and removed only shared Dropdown's opacity/translation entrance while retaining the separately evidence-gated SyncIndicator animation.
- [x] 2026-07-18 UTC — S3-T4 removed the inserted Selected metrics card and per-row selection lines, reserved selection headers/SVG overlays, and fixed metric/card virtual frames at 384 pixels without scroll compensation.
- [x] 2026-07-18 UTC — S3-T5 reserved fixed mini-histogram, score-preview, status, formula-preview, and diagnostic bodies with keyboard-reachable internal scrolling and full text retained.
- [x] 2026-07-18 UTC — Mandatory Tier 1 cleanup made formatting-only JSX edits. Repeated adversarial review closed omitted-empty facet semantics, canonical invalid-definition identity, stable metric hosts and owner-keyed bodies, editable pointer/ARIA behavior, and complete-versus-partial Derived local fallback; the final review reported no actionable findings.
- [x] 2026-07-18 UTC — Sprint 3 final metrics trace, 617-test frontend suite, TypeScript, 61 helper tests, default GUI acceptance, build/sync, repository lint, hard-cut searches, and diff hygiene passed.
- [x] 2026-07-18 UTC — Ralph iteration 4 entered Sprint 4. The plan gate fixed the slice at synchronous validated persisted/responsive snapshots, one invariant horizontally scrollable top rail, and settled-membership selection reconciliation; URL/shared-view precedence, the existing 800-millisecond browse grace, keyboard access, and evidence-gated Compare behavior remain locked. No dependency, presentation store, generic layout framework, or speculative Compare branch will be added.
- [x] 2026-07-18 UTC — S4-T1 now initializes AppShell personal settings from one validated synchronous storage snapshot, leaves URL/shared query state authoritative, and reduces the persistence hook to deferred writes plus lifecycle flushes.
- [x] 2026-07-18 UTC — S4-T2 moved media-query observation to `useSyncExternalStore`; cold-frame evidence proved immediate phone, narrow, and desktop agreement without an effect-late structure swap.
- [x] 2026-07-18 UTC — S4-T3 hard-cut the three conditional top bands to one invariant, accessible, horizontally scrollable rail; long filters, status, and similarity produced zero gallery-top movement.
- [x] 2026-07-18 UTC — S4-T4 removed debounce-time clearing, reconciles only definitive complete membership, keeps selected entities live-owned during retention, and closes or preserves Compare from settled membership. The supported pre-debounce Compare route reproduced UI-05 and passed after the fix.
- [x] 2026-07-18 UTC — Mandatory Tier 1 cleanup simplified the persistence flush/imports and hoisted invariant cold-frame expectations. Repeated adversarial reviews closed presentation-owned immutable selection/Compare data, render-phase ref mutation, explicit pending clears, status/action/similarity visibility after horizontal scrolling, and excluding Compare coverage; the final review reported no actionable findings.
- [x] 2026-07-18 UTC — Sprint 4 final toolbar/grid probes, 624-test frontend suite, TypeScript, 62 helper tests, default GUI acceptance, regenerated assets, repository lint/file-size guardrails, hard cuts, dependency scope, and diff hygiene passed.
- [x] 2026-07-18 UTC — Ralph iteration 5 entered Sprint 5. The plan gate fixed the slice at open-lifetime Dropdown placement, bounded ContextMenu and Theme Settings surfaces, reserved toolbar/Sync/folder slots, scoped persistent gutters, and one fixed-shell Similarity dialog; the existing toolbar probe remains the evidence owner. No dependency, positioning framework, JS scrollbar measurement, browse/top-rail reopening, or ranking behavior beyond persistent gutters will be added.
- [x] 2026-07-18 UTC — S5-T1 reserved every Dropdown check column, retained the initially selected vertical side while constraining internal height to available space, and fixed ContextMenu to a viewport-bounded 280-pixel shell with full labels retained through title/text; focused positioning, Dropdown, context-menu, and TypeScript checks passed.
- [x] 2026-07-18 UTC — S5-T2 moved Theme Settings measurement to layout timing, observes its open panel for async resizing, caps it to the visible viewport with internal scrolling, and removed the redundant RAF; focused placement edges and TypeScript passed.
- [x] 2026-07-18 UTC — S5-T4 permanently reserved FolderTree count/action columns, projected one query-owned pending/error child row until terminal children arrive, and scoped stable scrollbar gutters to FolderTree, Inspector, and ranking's two persistent vertical card panes; focused folder/API tests and TypeScript passed.
- [x] 2026-07-18 UTC — S5-T5 conditionally mounts Similarity with path/vector state prepared from the opening selection, fixes its viewport-bounded outer shell/header/footer, and reserves internally scrolling query/status regions; focused path/vector first-render tests and TypeScript passed.
- [x] 2026-07-18 UTC — S5-T3 reserved the desktop toolbar count, Sync typing/card line, and copied/time slots with full accessible text. The pre-fix painted trace confirmed Sync's separate `slideDown` at opacity 0 and a 2.335-pixel copy shift; the narrow fix removed that entrance and fixed the card/time widths, after which all related deltas and first-paint violations were zero.
- [x] 2026-07-18 UTC — Sprint 5 primary toolbar/surface evidence passed at `/tmp/lenslet-ui-stability-s5-toolbar.json`: Dropdown, Theme Settings, Sync, ContextMenu, and Similarity opened fully opaque/clamped with no entrance transform or animation, while async growth, total/typing/copy changes, folder hydration, long busy labels, and Similarity mode/error changes produced 0-pixel named-anchor deltas.
- [x] 2026-07-18 UTC — Default GUI acceptance exposed a 17.391-pixel Inspector interaction after the scoped stable gutter narrowed Quick View. Quick View labels/values now retain one row with full text in the DOM, title, and copy action; the repeated Inspector selection and delayed-metadata paths recorded 0-pixel section deltas.
- [x] 2026-07-18 UTC — Mandatory Sprint 5 Tier 1 cleanup made one indentation-only Similarity edit. The first adversarial review then found stale Similarity lifetime ownership, constrained Dropdown side choice, ultra-narrow ContextMenu minimum width, and a false-green count wait; all four were resolved without new dependencies or cross-sprint behavior.
- [x] 2026-07-18 UTC — Strengthened post-review evidence records the exact `18 items` → `1 / 18 items` → `18 items` transition, selects the roomier Dropdown side when neither fits, clamps ContextMenu to 144 pixels with 8-pixel margins in a 160-pixel viewport, and proves a delayed stale Similarity completion neither closes the reopened dialog nor clears its selected target. The final toolbar trace and default GUI acceptance pass with 0-pixel named-anchor deltas.
- [x] 2026-07-18 UTC — Repeated adversarial review then closed visual-viewport ContextMenu width/offset ownership, StrictMode-safe Similarity lifetime teardown, accepted-only selection restoration, and constrained-above Dropdown growth. The final trace clamps a 184-pixel menu inside a 200-by-230 zoomed visual viewport and grows an above-side Dropdown from 186 to 322.78 pixels with zero overlap.
- [x] 2026-07-18 UTC — Sprint 5 closure gates passed: 635 frontend tests across 114 files, TypeScript, 62 painted-frame/browser-helper tests, final toolbar evidence, default GUI acceptance with 0-pixel Inspector deltas, regenerated assets, repository lint/file-size guardrails, dependency/hard-cut checks, and diff hygiene. The mandatory closure review reported no actionable findings.
- [x] 2026-07-18 UTC — Ralph iteration 6 entered Sprint 6. The plan gate fixed the slice at target-bound Compare/ranking decoded presentation, pre-paint ranking geometry, evidence-gated cold thumbnail reveal, and one delayed 800-millisecond boot/lazy shell; no dependency, generic Suspense/media framework, preload cohort, cache expansion, or speculative non-reproduced behavior will be added.
- [x] 2026-07-18 UTC — S6-T1 reproduced delayed Compare resource arrival with distinct fixtures and now promotes decoded thumbnail/full resources together with their pair labels; the final grid trace retained the prior pair while pending and recorded zero mixed-label/resource frames.
- [x] 2026-07-18 UTC — S6-T2 keeps next-instance preload network-only, decodes the active fullscreen target, binds fullscreen pixels/meta to one presented image, clamps persisted tray height in first-ready layout timing, and permanently reserves save status; the final trace retained 80 frames with zero mixed identity/pixels, kept decoded image `1` under target-`2` failure, and moved no header controls on save failure.
- [x] 2026-07-18 UTC — S6-T3 reproduced cold-scroll pop-in and added a per-card decode-before-reveal boundary only; the delayed card remained invisible in an invariant neutral shell and revealed at full opacity after decode without gallery-wide preload or batching.
- [x] 2026-07-18 UTC — S6-T4 replaced chained health/ranking loaders with one boot shell and one start time. Fast ranking boot painted zero loading copy; the deliberate slow path retained the shell and first exposed copy at approximately 800 milliseconds.
- [x] 2026-07-18 UTC — S6-T5 added surface-sized delayed fallbacks for Inspector/Compare and idle-prefetches only those two known chunks. Independent cold contexts painted no early copy and exposed slow-path copy at approximately 800 milliseconds.
- [x] 2026-07-18 UTC — Sprint 6 primary grid and Inspector probes passed with zero violations. The added browser init scripts were extracted to `sprint6_evidence.py`, keeping the grid evidence owner below the 2,000-line hard guardrail without introducing a general DSL.
- [x] 2026-07-18 UTC — Mandatory Tier 1 cleanup removed eight lines by making ThumbCard decode dependencies explicit and deleting Compare pass-through callbacks. Repeated adversarial review then closed target-bound error/retry/unsupported ownership, failed ranking decode promotion, unbounded decode preload, first-frame tray clamping, stale-success readiness, pixel-level evidence, rejected prefetch observation, slow-success/corrupt-supersession coverage, and evidence file-size headroom; the final reviewer reported no actionable findings.
- [x] 2026-07-18 UTC — Sprint 6 closure passed 647 frontend tests across 119 files, TypeScript, 62 painted-frame/browser-helper tests, final grid and Inspector probes, independently rerun metrics/toolbar probes, default GUI acceptance, regenerated assets, repository lint/file-size guardrails, dependency/hard-cut checks, and diff hygiene. Component-local Compare CSS kept global `styles.css` at 1,999 lines and the final review remained clean.
- [x] Implementation — Executed Sprints 1-6 with per-sprint cleanup, review, validation, asset regeneration, and handoff evidence.


## Artifacts and Handoff


The source audit is `docs/20260718_frontend_ui_instability_observations.md`. This plan is `docs/20260718_frontend_ui_stability_execution_plan.md`. The predecessor is `docs/20260718_browser_interaction_continuity_plan.md`; preserve its shipped 340-pixel width, 800-millisecond browse grace, decoded Ctrl/Meta-wheel cache, and full-population histogram.

Primary owners are `frontend/src/app/AppShell.tsx`, `frontend/src/app/hooks/useAppDataScope.ts`, the existing grid presentation hook/model, `usePersistedAppShellSettings.ts`, `useMediaQuery.ts`, `GridTopStack.tsx`, metrics components/hooks, Inspector metadata hooks/sections, shared Dropdown/Toolbar/Sync/Theme Settings, FolderTree, Similarity, Compare, ranking, ThumbCard/VirtualGrid, `frontend/src/styles.css`, and `scripts/browser/gui_jitter/`.

Start Ralph with Sprint 1 only. Before each ticket, read the audit/plan and current diff, run the plan gate, and protect unrelated user work. Do not launch the older blocked workspace as a substitute. Later tickets may add their smallest focused probe extension, but must not grow a general stability DSL.

Revision note: the adversarial review moved browse ownership ahead of count retention, specified live annotations/reset boundaries, preserved local Clear in a stable slot, split multi-owner work into six sprints, narrowed browser evidence to existing focused probes, scoped source greps correctly, and made platform/media fixes reproduce-first. The user's follow-up then authorized Ralph execution of the full program.

### Sprint 1 handoff — 2026-07-18

Completed S1-T1 through S1-T4. Product owners changed were the categorical and metric-category cards, histogram footer/action slot, Inspector single-metadata hook and section, and their focused tests. Evidence owners changed were `scripts/browser/gui_jitter/{fixtures,metrics,inspector,probe}.py`; the shipped frontend bundle was regenerated and synchronized.

Primary evidence is `/tmp/lenslet-ui-stability-s1-metrics.json` and `/tmp/lenslet-ui-stability-s1-inspector.json`: all named geometry deltas were 0 pixels, fast and superseded metadata transitions painted no idle/loading copy, and the final deliberate slow transition first painted loading copy at 1,013.7 milliseconds. Full frontend, helper, GUI acceptance, lint, and hygiene gates passed.

At the Sprint 1 handoff, the pending `Filtered: 0` semantic frame remained deliberately unresolved for Sprint 2's atomic browse identity; Sprint 2 has now closed it without local text suppression.

### Sprint 2 handoff — 2026-07-18

Completed S2-T1 through S2-T4. Product owners changed were the browse/facet query generation keys, `AppShell`, the presented browse hook, similarity workflow ownership, the existing entity store, VirtualGrid pending copy, metric-rail inert styling, and focused tests. Evidence owners changed were `scripts/browser/gui_jitter/{fixtures,grid,grid_dom}.py` plus browser-helper tests; the shipped frontend bundle was regenerated and synchronized.

Primary evidence is `/tmp/lenslet-ui-stability-s2.json`: fast filter/sort responses painted no loading, slow responses crossed from inert grace into target-owned loading, A-to-B-to-C settled only C, optimistic rating remained live, empty/error retired membership truthfully, and scope/source resets retained nothing incompatible. Requested/presented identity, epoch, visible membership, totals, ratings, and metric-rail inertness produced zero violations. Full frontend, helper, GUI acceptance, lint, and hygiene gates passed.

Residual risk is the known 45-pixel filter-band top-stack delta, explicitly deferred to Sprint 4's invariant top-stack ticket; Sprint 2 preserved zero grid-width delta and did not claim that geometry fix. Next ticket is S3-T1, resetting Derived Score drafts only on semantic spec/schema changes.

### Sprint 3 handoff — 2026-07-18

Completed S3-T1 through S3-T5. Product owners changed were the existing facet query hook and new focused facet presentation model; `AppShell`, `LeftSidebar`, Metrics/Derived panels; metric, categorical, Derived, Attributes, and shared Dropdown components; focused model/component tests; and `frontend/src/styles.css`. Evidence owners changed were `scripts/browser/gui_jitter/{fixtures,metrics}.py`, responsive geometry evidence, and browser-helper tests. The shipped frontend bundle was regenerated and synchronized.

Primary evidence is `/tmp/lenslet-ui-stability-s3.json`: all named anchors stayed at 0 pixels; omitted and explicit empty facets, terminal errors, partial local data, histogram-to-category hydration, 384-pixel virtualization, selection overlays, app-owned first paint, semantic Derived retention/reset, freeform pointer/keyboard access, and bounded long content produced zero violations. Full frontend, helper, GUI acceptance, lint, hard-cut, and hygiene gates passed.

Residual risk is a deliberate browser-level A-to-B-to-C facet race not yet captured; the reviewed query-key and per-field ownership path has no known defect. Sprint 4 begins with S4-T1, synchronous persisted-setting initialization, and retains the known 45-pixel top-stack finding for S4-T3.

### Sprint 4 handoff — 2026-07-18

Completed S4-T1 through S4-T4. Product owners changed were `AppShell`, persisted settings and media-query hooks, selection/viewer/Compare ownership, `GridTopStack`/`StatusBar`, Inspector evidence attributes, focused tests, and `frontend/src/styles.css`. Evidence owners changed were `scripts/browser/gui_jitter/{toolbar,grid,grid_dom}.py`, responsive geometry evidence, and browser-helper tests. The shipped frontend bundle was regenerated and synchronized.

Primary evidence is `/tmp/lenslet-ui-stability-s4-toolbar.json` and `/tmp/lenslet-ui-stability-s4-grid.json`: cold phone/narrow/desktop frames had correct persisted, URL-precedence, and responsive truth; toolbar, top-stack, grid-width, and gallery-anchor deltas were 0 pixels. Matching/excluding selection and Compare crossed grace/loading with correct ownership, and the 390-pixel rail kept its 45-pixel footprint while keyboard overflow plus newly introduced status, action, and similarity contexts stayed reachable and visible. Full frontend, helper, GUI acceptance, lint, hard-cut, dependency, and hygiene gates passed; the final mandatory review was clean.

No Sprint 4 blocker remains. Sprint 5 begins with S5-T1, locking Dropdown and ContextMenu geometry; it must preserve this sprint's one-rail contract and must not reopen persistence, responsive, or browse ownership without new failing evidence.

### Sprint 5 handoff — 2026-07-18

Completed S5-T1 through S5-T5. Product owners changed were shared Dropdown, Theme Settings, Toolbar, and Sync; ContextMenu and its visual-viewport positioning; FolderTree, Inspector Quick View, ranking gutters, Similarity dialog/workflow ownership, focused tests, and the extracted `frontend/src/utilitySurfaces.css`. Evidence owner `scripts/browser/gui_jitter/toolbar.py` was extended in place, and the shipped frontend bundle was regenerated and synchronized.

Primary evidence is `/tmp/lenslet-ui-stability-s5-toolbar.json`: all frequent surfaces opened opaque, unanimated, and clamped; exact count, typing, copy, folder, async growth, ultra-narrow/zoomed viewport, constrained-above Dropdown, and stale Similarity lifetime paths produced zero violations and 0-pixel maximum named-anchor movement. Default GUI acceptance also passed with 0-pixel Inspector continuity after the Quick View/gutter interaction fix. Full frontend, helper, TypeScript, build/sync, lint, dependency, and hygiene gates passed; mandatory cleanup and the final adversarial review were clean.

Residual non-blocking gaps are environment-dependent classic scrollbar rendering, mirrored-but-not-separately-painted DropdownMenu growth, and the toolbar evidence file's warn-only 1,287-line size. Sprint 6 begins with S6-T1, reproducing Compare resource/label identity with delayed distinct fixtures; it must keep new evidence in the planned grid/Inspector scenarios and leave Sprint 5's utility contracts closed.

### Sprint 6 handoff — 2026-07-18

Completed S6-T1 through S6-T5. Product owners changed were `AppModeRouter`/`AppShell`, the shared delayed-visibility hook and boot shell, ThumbCard's decode-before-reveal boundary, Compare's target/presented resource model plus component-local CSS, ranking fullscreen/layout/status ownership, and focused tests. Evidence owners changed were distinct fixture colors, `scripts/browser/gui_jitter/{grid,inspector,sprint6_evidence}.py`, and regenerated `src/lenslet/frontend/` assets. No dependency or generic Suspense/media framework was added.

Primary evidence is `/tmp/lenslet-ui-stability-s6-grid-final.json` and `/tmp/lenslet-ui-stability-s6-inspector-final-css.json`. Compare retained its prior decoded pair for 99 frames through a 1,800-millisecond success and observed a corrupt superseded delivery for 74 frames with zero mixed identity or RGB pixels. Ranking's first 517.06-pixel tray frame was already clamped inside the 765-pixel workspace; fullscreen retained decoded image `1` under target-`2` failure with zero mixed identity/pixels; fast boot painted no copy and slow copy appeared at approximately 796 milliseconds. Cold thumbnails preserved geometry through decode, Inspector/Compare lazy copy appeared at approximately 799/805 milliseconds, and both cold contexts raised zero page errors.

All independent probes, the 647-test frontend suite, TypeScript, 62 helper tests, default GUI acceptance, build/sync, lint/file-size guardrails, dependency/hard-cut checks, and diff hygiene passed. Mandatory Tier 1 cleanup reduced the slice by eight lines; repeated adversarial review closed every finding and its final post-CSS pass reported no actionable issues. All six planned sprints and all twenty-seven tickets are complete; no blocker or deferred Sprint 6 behavior remains.
