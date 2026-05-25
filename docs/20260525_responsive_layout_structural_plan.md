# 2026-05-25 Responsive Layout Structural Plan


## Outcome + Scope Lock


After implementation, Lenslet should stay usable when the browser is resized narrower, wider, shorter, zoomed in, or zoomed out. Top-level controls must not overlap or leave the viewport, mobile search must reserve real space, viewer and compare must stay usable, and side panels must never collapse into unusable slivers.

This plan fixes the structural causes behind `R1` through `R8` in `docs/20260524_resizing_interactions_review.md`. It treats the problem as layout authority: one policy computes effective layout from viewport, persisted preferences, overlay state, and toolbar state, then AppShell, toolbar, viewer, compare, and inspector consume that model.

Goals:

1. Define one typed responsive layout policy for AppShell, sidebars, shell reserves, grid insets, and overlay insets.
2. Preserve user sidebar preferences while suppressing sidebars non-destructively when the current viewport cannot support them.
3. Repair narrow toolbar, mobile search, and mobile drawer reachability without adding a UI framework.
4. Split grid insets from overlay insets so viewer and compare are not squeezed by sidebar reservations.
5. Prevent persistent inspector rendering below its usable width and fix the known inspector internals that overflow.
6. Add live-browser responsive geometry validation that reproduces the user-reported resize and zoom-equivalent failure paths.

Non-goals:

1. Do not replace Lenslet's visual design system or add a large component framework.
2. Do not rewrite browse/grid virtualization or change TanStack Query behavior.
3. Do not change backend APIs, storage APIs, dataset formats, CLI behavior, or workspace persistence formats beyond existing frontend localStorage keys.
4. Do not perform a broad accessibility audit beyond overlay focus isolation and controls touched by this plan.
5. Do not remediate unrelated npm audit findings as part of this resize plan.
6. Do not polish all inspector metadata rendering or metrics sidebar content beyond the controls named in `R7` and `R8`.

Pre-approved behavior changes:

1. On phone, narrow, short-height, and overlay-active states, persisted sidebars may be suppressed for effective layout without mutating the persisted `leftOpen` or `rightOpen` user preference.
2. Persisted sidebar widths may be clamped for effective layout without overwriting the user's preferred stored widths.
3. Viewer and compare may use full overlay insets on phone, narrow, short-height, and overlay-owned states.
4. Lower-priority toolbar controls may move into drawer or overflow placement; unavailable controls should be removed from that layout row or `display: none`, not opacity-hidden while still occupying collision-causing slots.
5. Inspector controls may wrap, stack, or switch to compact local layouts below container thresholds.
6. Background regions may be made `inert` or explicitly non-focusable/non-interactable while viewer or compare is active.

Requires sign-off before implementation:

1. Adding or upgrading npm, pip, or other packages. Any proposed dependency requires an online compromise/vulnerability check before installation.
2. Replacing the sidebar system with `react-resizable-panels` or another panel library.
3. Building a new mobile inspector sheet/drawer instead of suppressing persistent right inspector below its usable threshold.
4. Changing keyboard shortcuts, removing existing commands, or changing backend data contracts.
5. Downgrading the required live-browser validation to unit tests only.

Deferred or out of scope:

1. `R9` filter menu/status-banner overlap is deferred unless it becomes a primary acceptance failure: off-viewport controls, blocking toolbar/status overlap, background interactivity under overlays, or document horizontal overflow.
2. `R10` metrics sidebar cramped summary is deferred unless it becomes a primary acceptance failure under the required responsive geometry script.
3. Replacing custom menus with `@floating-ui/react` is deferred.
4. Broad dependency upgrade remediation is deferred to a separate security/tooling task.


## Context


The resize audit found ten issues. This plan directly covers `R1` through `R8` and defines explicit deferral rules for `R9` and `R10`.

The first issue group is toolbar and mobile command placement. At `320px` through `390px`, toolbar controls overlap because fixed slots and hidden controls can still reserve space. Mobile search can render over status/grid content because the toolbar's actual height and AppShell's reserved height are not governed by one owner. The mobile drawer can hide later commands behind horizontal scrolling without a clear affordance.

The second issue group is invalid sidebar geometry. AppShell currently persists `leftOpen` and `rightOpen`, reads persisted sidebar widths, constrains widths, and also has a narrow-media effect that auto-closes both panels. That conflates user preference with current viewport feasibility. A temporary phone-width resize can erase a desktop preference, while independently persisted widths can still be too large for the current viewport.

The third issue group is overlay and inspector geometry. `Viewer.tsx` and `CompareViewer.tsx` use `left-[var(--left)] right-[var(--right)]`, so full-screen tools inherit grid sidebar reservations. The inspector has fixed-width pieces such as the preview, star row, and action rows that do not adapt to the real panel container width.

The current frontend stack is React 18, TypeScript, Vite, Tailwind-style utility classes, shared CSS in `frontend/src/styles.css`, `@tanstack/react-query` for server state, `@tanstack/react-virtual` for browse virtualization, `@dnd-kit/*` for drag behavior, and `lucide-react` for icons. The grid and virtualization stack is not the root cause. No new dependency is required for the primary plan.

Relevant current code paths:

1. `frontend/src/lib/breakpoints.ts`
2. `frontend/src/app/AppShell.tsx`
3. `frontend/src/app/layout/useSidebars.ts`
4. `frontend/src/app/layout/sidebarLayout.ts`
5. `frontend/src/shared/ui/Toolbar.tsx`
6. `frontend/src/shared/ui/toolbar/ToolbarMobileDrawer.tsx`
7. `frontend/src/features/viewer/Viewer.tsx`
8. `frontend/src/features/compare/CompareViewer.tsx`
9. `frontend/src/features/inspector/Inspector.tsx`
10. `frontend/src/features/inspector/sections/BasicsSection.tsx`
11. `frontend/src/styles.css`

The root cause is distributed layout authority. `breakpoints.ts` clamps widths, `AppShell.tsx` creates CSS variables and persists preferences, `Toolbar.tsx` owns mobile search state, CSS changes toolbar layout through media queries, and viewer/compare/inspector independently consume the resulting geometry. The structural fix is to make invalid states unrepresentable in the effective layout model and to keep persisted preferences separate from effective visibility.

Scope lock decisions from review feedback:

1. Suppression is non-destructive. Only explicit user actions mutate persisted sidebar open preferences.
2. RSP-1 must produce a typed policy API, not only threshold constants.
3. Impossible constraints must suppress a sidebar rather than shrinking it below a declared usable minimum.
4. Grid and overlay insets must be separate variables.
5. AppShell should own mobile search state and toolbar reserved height inputs. Toolbar should render from controlled state instead of privately changing height in a way AppShell discovers later.
6. Process instructions belong in the implementation protocol section, while the main tasks stay focused on product behavior and code boundaries.


## Interfaces and Dependencies


No backend interface changes are allowed. The material frontend interface change is a new local layout policy module consumed by AppShell and passed down as props/CSS variables where needed. The policy should own only shared layout facts: mode, effective sidebar visibility and widths, suppression reasons, grid/overlay insets, inspector persistent eligibility, and declared shell reserves. Toolbar command arrangement and inspector internals remain local component/CSS concerns.

Create a policy module shaped like this, with exact names allowed to change only if the implemented names are clearer and the same contract remains:

    // frontend/src/app/layout/responsiveLayoutPolicy.ts

    export type LayoutMode = 'phone' | 'narrow' | 'tablet' | 'desktop'
    export type OverlayMode = 'none' | 'viewer' | 'compare'
    export type SidebarSuppressionReason =
      | 'viewport-too-narrow'
      | 'inspector-too-narrow'
      | 'overlay-active'
      | 'short-height'
      | 'insufficient-center-space'

    export interface ResponsiveLayoutInput {
      viewportWidth: number
      viewportHeight: number
      userLeftOpen: boolean
      userRightOpen: boolean
      leftPreferredWidth: number
      rightPreferredWidth: number
      overlay: OverlayMode
      mobileSearchOpen: boolean
    }

    export interface ResponsiveLayoutModel {
      mode: LayoutMode
      shortHeight: boolean
      centerMinWidth: number

      effectiveLeftOpen: boolean
      effectiveRightOpen: boolean
      leftRailVisible: boolean
      leftWidth: number
      rightWidth: number
      leftSuppressionReason?: SidebarSuppressionReason
      rightSuppressionReason?: SidebarSuppressionReason

      gridInsets: { left: number; right: number }
      overlayInsets: { left: number; right: number }

      inspector: {
        persistentAllowed: boolean
        minUsableWidth: number
        suppressionReason?: SidebarSuppressionReason
      }

      shellReserves: {
        toolbarHeightPx: number
        mobileDrawerHeightPx: number
      }
    }

    export interface SidebarDragConstraintInput {
      viewportWidth: number
      activeSide: 'left' | 'right'
      userLeftOpen: boolean
      userRightOpen: boolean
      leftPreferredWidth: number
      rightPreferredWidth: number
    }

Initial policy constants should be explicit in the module and covered by unit tests:

1. `phone`: viewport width `<= 480`.
2. `narrow`: viewport width `481` through `900`.
3. `tablet`: viewport width `901` through `1180`.
4. `desktop`: viewport width `> 1180`.
5. `shortHeight`: viewport height `< 560`.
6. `leftContentMinWidth`: `200`.
7. `leftRailWidth`: existing `48`.
8. `rightInspectorMinUsableWidth`: `280`.
9. `centerMinWidth`: `320` for phone, `360` for narrow, `420` for tablet, and `520` for desktop, with phone/narrow sidebars suppressed when the viewport cannot fit center plus usable sidebars.
10. Shell reserve constants for base toolbar height, mobile search row height, and mobile drawer height should be declared in one place and reflected in `--toolbar-h`/drawer spacing.

Impossible-constraint priority is part of the interface contract. In overlay mode, viewer/compare own the interaction surface: overlay insets are `0/0`, background sidebars are suppressed or inert, and grid insets do not constrain the overlay. In browse mode, center grid usability wins first; right inspector may remain only if it can fit at `rightInspectorMinUsableWidth`; left content may remain only after center and right constraints are satisfied; left rail may remain only if it does not create horizontal overflow. Effective widths are clamped, but preferred widths in localStorage are not overwritten.

AppShell should expose debug attributes on the shell or a stable child so Playwright can record the model without importing frontend code:

    data-layout-mode
    data-short-height
    data-left-suppression-reason
    data-right-suppression-reason
    data-inspector-suppression-reason
    data-overlay-mode
    data-effective-left-width
    data-effective-right-width

The responsive script should read numeric inset values from CSS variables and suppression reasons/effective widths from these data attributes.

CSS variables should split grid and overlay ownership:

    --grid-left
    --grid-right
    --overlay-left
    --overlay-right
    --toolbar-h

The old `--left` and `--right` variables may remain temporarily during the migration, but viewer/compare must not read grid sidebar offsets directly after RSP-7.

No dependency is part of the approved implementation. If a package is proposed later, pause for sign-off and write a package decision note with package name, version, license, dependency count, integrity source, online compromise/malware checks, known vulnerability advisories, and why native CSS/React is insufficient.


## Plan of Work


The plan uses four sprints and nine implementation tickets. Each sprint must produce a runnable browser state and update this document continuously, especially Progress Log and handoff notes. After each sprint, add a short handoff note before starting the next sprint.

For minor script-level uncertainties, such as exact evidence-output path or fixture filename, proceed according to this approved plan to maintain momentum. After the sprint, ask for clarification and apply follow-up adjustments if the user wants a different placement.

### Scope Budget and Guardrails


Scope budget is four sprints, nine tickets, and a narrow file set: frontend layout policy, AppShell integration, sidebar width/effective state handling, toolbar/mobile drawer, viewer/compare overlay offsets, known inspector responsive internals, CSS, and one focused Playwright geometry script introduced early and expanded incrementally.

Debloat and removal targets:

1. Remove destructive narrow auto-close behavior that mutates `leftOpen`/`rightOpen` on media query changes.
2. Replace duplicated sidebar constraint logic with calls into the responsive policy, including drag-time constraints in `useSidebars.ts`.
3. Remove viewer/compare dependence on `--left` and `--right`.
4. Remove hidden toolbar/mobile drawer controls that still occupy collision-causing layout slots, while preserving existing command handlers, labels, and availability rules.
5. Avoid adding dependencies or parallel layout systems. Track net change with `git diff --stat` and `rg` checks for old variables and duplicated breakpoint logic.

Quality guardrails:

1. Use the smallest robust implementation that makes the invalid layout states unrepresentable in effective layout.
2. Do not hide failures by clipping overflow, raising z-index, or making controls opacity-hidden while still occupying space.
3. Prefer native CSS container queries and layout primitives before new JavaScript abstractions.
4. Keep each ticket surgical. Touch only files tied to the ticket, required invariants, or verification.
5. For every non-trivial code ticket, use the `better-code` skill before and during implementation to state assumptions, invariants, smallest robust approach, and verification evidence.
6. Apply Karpathy-style execution guardrails for substantive code: state material assumptions before coding, avoid speculative features, preserve unrelated code, remove only unused code introduced by the change, and attach a concrete verification check to each step.
7. Delegate subagents early when they can find real codepaths/files faster. Let subagents run long enough to produce useful results; if any are still running after 10 minutes, ask for a progress update and why more time is needed rather than terminating them to return faster.

### Sprint Plan


Sprint 1 goal: establish the responsive layout authority.

Demo outcome: AppShell derives one non-destructive layout model for phone, narrow, tablet, desktop, short-height, and overlay states. Resizing down and back up does not erase persisted sidebar preferences. A minimal browser geometry harness can load the app, set viewports, read layout debug data, and report overflow.

Tasks:

1. `RSP-1`: Define `responsiveLayoutPolicy.ts`.
   Implement the typed policy API, constants, impossible-constraint priority, effective sidebar visibility, effective widths, grid insets, overlay insets, inspector eligibility, shell reserves, and a policy-owned drag constraint helper. Validation: model tests cover ordinary and impossible inputs, and no output exists unless AppShell or validation consumes it.
2. `RSP-2`: Route AppShell through the policy.
   Replace destructive narrow auto-close with non-destructive effective layout. Persist only `userLeftOpen`, `userRightOpen`, and preferred widths from explicit user actions. Add debug data attributes and split CSS variables into grid/overlay variables. Update `useSidebars.ts` so drag-time width limits use the same policy helper and cannot preview or persist impossible widths. Validation: resizing down and back up restores preferred sidebars when they can fit, and dragging cannot produce a persisted width that violates policy minima.
3. `RSP-3`: Cover persistence, absurd widths, and seed the geometry harness.
   Add tests for `rightPreferredWidth = 900` at `1024`, `leftPreferredWidth = 760` at `900`, both widths oversized after reload, both sidebars preferred open, right inspector open before resize-down, and resize-down/resize-up without rewriting persisted open preferences. Add the minimal responsive Playwright harness with viewport setup, localStorage reset/persistence modes, DOM debug snapshot, scrollWidth/clientWidth check, and screenshot-on-failure plumbing. Validation: the harness runs at least one desktop and one phone scenario and writes JSON evidence even before later assertions are added.

Sprint 2 goal: repair toolbar, mobile search, and mobile drawer layout.

Demo outcome: at phone widths, the top row contains only valid compact commands, mobile search reserves declared height immediately, and drawer commands are reachable without hidden-scrollbar guesswork.

Tasks:

4. `RSP-4`: Define narrow toolbar command placement.
   Phone top row contains app identity/back or folder context, search toggle, viewer nav only when viewer is active, and one drawer/overflow affordance. Drawer/overflow contains existing sort, layout mode, select mode, upload, theme/settings, metadata/autoload, and compare order controls. This is placement and reachability work only: preserve existing handlers, labels, disabled states, and primitives unless a collision cannot be fixed otherwise. Hidden or unavailable controls must not occupy top-row slots unless the slot is intentionally reserved. Validation: the harness reports no visible-control overlap at `320x700`, `360x700`, and `390x700`.
5. `RSP-5`: Move mobile search ownership to AppShell.
   AppShell owns `mobileSearchOpen`, passes it to Toolbar, and passes the state into the layout policy so toolbar reserved height is declared rather than discovered after a ResizeObserver delay. Keep ResizeObserver only as a defensive measurement check if needed, not as the authority. Include status/banner-visible cases. Validation: opening mobile search updates `--toolbar-h`/shell reserve immediately enough that the status banner and grid do not overlap at `320x700` and `640x760`.
6. `RSP-6`: Fix mobile drawer reachability.
   Replace horizontal-scroll-only hidden controls with a wrapped, segmented, or explicit overflow-affordance structure using existing drawer/menu primitives where practical. `R8` is in scope because hidden drawer commands are command reachability failures. Validation: every existing drawer command is reachable by pointer and keyboard at `320px` width with a visible affordance, without introducing document horizontal overflow.

Sprint 3 goal: make overlays and inspector mode-aware.

Demo outcome: viewer and compare are full and focused on narrow/short screens, background sidebars/drawer controls are not visible as slivers or focusable/interactable, and inspector controls stay inside their allowed panel.

Tasks:

7. `RSP-7`: Replace overlay sidebar offsets.
   Update viewer, compare, and drag/drop overlay paths to use `--overlay-left` and `--overlay-right`. Isolate only the browse shell behind viewer/compare, not unrelated modal implementations such as similarity or move dialogs. Validate that overlay-active state suppresses or inerts background toolbar/sidebar/drawer regions for pointer and keyboard focus, not only z-index. Validation: `Tab` cannot reach toolbar or sidebars while viewer/compare is active, `Escape` closes the active overlay, focus returns sanely, and overlay stage rectangles are not squeezed by grid insets.
8. `RSP-8`: Fix known inspector internals only.
   Add `container-type: inline-size` to the inspector container as needed. Make preview `max-width: 100%` with `min-width: 0` and contained object fitting. Make the star row wrap or switch to compact segmented layout. Ensure action rows have `min-width: 0`, wrap/stack below container thresholds, and long paths/metadata use `overflow-wrap: anywhere` or truncation with title. Do not expand this ticket into general metadata polish. Validation: when persistent inspector is allowed, preview, star row, primary action rows, and long source/path text remain inside the panel at `480x760`, `760x430`, and `1024x480`.

Sprint 4 goal: finalize live-browser regression evidence.

Demo outcome: the focused responsive Playwright script fails on the resize bug classes found in the audit and writes useful evidence for future debugging.

Tasks:

9. `RSP-9`: Finalize responsive geometry validation.
   Expand the Sprint 1 harness into a complete Python Playwright script using a temporary fixture dataset, consistent with `scripts/gui_smoke_acceptance.py`. It must test representative viewport and state combinations, emit evidence JSON, and save screenshots for failed scenarios. Include the `760px` metrics-left, both-sidebars-preferred-open, selected-items scenario so `R10` remains explicitly observed even if not dedicated fix work. Validation: all geometry assertions pass, evidence includes the required fields, and `R1` through `R8` cannot recur under tested scenarios.

### Task Gate Routine


Every ticket must use this gate routine.

0. Plan gate.
   The implementing agent briefly restates the ticket goal, acceptance criteria, material assumptions or ambiguities, and files expected to change. If an ambiguity would change behavior, stop and ask. For substantive code work, invoke `better-code` first and state the key invariants, smallest robust approach, and verification evidence.
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


Primary acceptance checks are live-browser checks because the failures are visual and interaction-specific. Secondary checks are fast unit, build, and lint gates that catch regressions but cannot replace browser validation.

Primary per-sprint checks:

1. Sprint 1.
   Run frontend model tests for `320`, `360`, `390`, `480`, `760`, `900`, `1024`, `1180`, and `1440` widths, short-height cases, overlay modes, both sidebars preferred open, absurd preferred widths, drag constraints, and resize persistence. Run the minimal responsive harness for one phone and one desktop case. Expected: persisted preferences are not rewritten by responsive suppression; no effective sidebar is below its usable minimum; impossible layouts suppress sidebars in the documented priority order; grid and overlay insets are independent in the model; browser evidence JSON is emitted.
2. Sprint 2.
   Run live browser checks at `320x700`, `360x700`, `390x700`, and `640x760`, including scan-stable/status banner visible and mobile search open. Expected: toolbar visible controls have no bounding-box overlap; search row does not overlap status/grid; hidden controls are not interactable; drawer or overflow commands are reachable with a visible affordance.
3. Sprint 3.
   Run live browser checks at `390x520`, `480x760`, `760x430`, and `1024x480` with item selected, right inspector previously open, viewer opened while inspector is preferred open, compare opened while mobile drawer would otherwise be active, and both sidebars preferred open. Expected: viewer/compare use overlay insets rather than grid insets; no sidebar or drawer sliver is visible or pointer/keyboard-interactable under overlays; inspector controls stay inside the panel only when persistent inspector is allowed.
4. Sprint 4.
   Run the finalized responsive Playwright script, including the `760px` left-metrics/both-sidebars-preferred-open scenario. Expected: all geometry assertions pass and failed cases, if any, include screenshot and JSON evidence. Metrics summary cramping remains deferred only if it creates no overlap, off-viewport controls, background interactivity leak, or horizontal overflow.

Required script evidence from `RSP-3`/`RSP-9`:

1. Viewport size and tested state.
2. Layout model snapshot from DOM debug attributes and CSS variables.
3. `documentElement.scrollWidth` versus `clientWidth`.
4. Toolbar visible and interactable control rectangles.
5. Overlay rectangle and stage rectangle.
6. Sidebar rectangles and suppression reasons.
7. Mobile drawer reachability evidence.
8. Screenshot per failed scenario.

Primary final gates:

1. Run the existing browser smoke:

       python scripts/gui_smoke_acceptance.py

2. Run the responsive geometry script introduced by `RSP-3` and finalized by `RSP-9`.
3. Manually check browser behavior at `100%`, zoom in, and zoom out for `320px` through `390px` equivalent widths and one short-height desktop slice.

Secondary fast gates:

1. Run frontend tests:

       cd frontend && npm run test

2. Run frontend build:

       cd frontend && npm run build

3. Run repo lint:

       python scripts/lint_repo.py

Dependency security gate:

Run dependency checks only if `package.json`, `package-lock.json`, `pyproject.toml`, or another package manifest changes. If dependencies change, perform fresh online compromise and vulnerability checks before installation, then run the relevant audit command and capture a package decision note. For npm changes, include:

    npm audit --omit=dev
    npm audit signatures

Final acceptance criteria:

1. At required tested widths, there is no document horizontal overflow.
2. Toolbar visible/interactable controls have no bounding-box overlap.
3. Mobile search increases declared toolbar reserved space or otherwise keeps grid/status content below it.
4. Responsive suppression does not erase persisted user sidebar preferences; resizing down and back up restores sidebars when they can fit.
5. No impossible layout is solved by making a sidebar smaller than its declared usable minimum; the policy suppresses instead.
6. Overlay insets are independent from grid insets; viewer and compare do not read grid sidebar offsets directly.
7. Background controls are not pointer- or keyboard-interactable under viewer/compare overlays.
8. Inspector controls do not leave the viewport when persistent inspector is allowed.
9. All controls moved into drawer/overflow remain reachable with a visible affordance.
10. `R1` through `R8` do not recur under the required scenarios. `R9` and `R10` do not block acceptance unless they produce one of the primary acceptance failures listed in this section.


## Risks and Recovery


Hidden dependencies:

1. Current localStorage keys store sidebar open preferences and widths; mixing preference and effective state would recreate the original bug.
2. Browser zoom often behaves like a smaller CSS-pixel viewport but not identically, so final browser checks must include actual zoom changes.
3. Toolbar currently uses ResizeObserver-derived `--toolbar-h`; if AppShell does not own the mobile search state, height races can return.
4. Viewer and compare zoom/pan hooks assume stable container dimensions; overlay inset changes must trigger fit/center behavior normally.
5. `aria-modal` does not by itself guarantee background pointer/focus isolation; overlay validation must check focus and interactability.
6. Responsive geometry assertions can become noisy if they include hidden-but-mounted nodes; only truly visible and interactable controls should count for overlap checks.

Recovery:

1. Keep each sprint committable and reviewable.
2. If a sprint regresses core browsing, revert only that sprint's touched files and preserve any tests or screenshots that exposed the issue.
3. Do not revert unrelated user changes in the worktree.
4. Generated fixture datasets and Playwright evidence should live under `/tmp` or an ignored artifact path unless the user approves committed fixtures.
5. Responsive checks should reset localStorage between scenarios except for tests specifically validating persisted preferences.
6. If a proposed package fails security review, do not install it. Use native CSS/React for the sprint or split dependency adoption into a separate approval ticket.
7. If RSP-1's policy API becomes larger than needed, stop and remove outputs not consumed by RSP-2 through RSP-9 before proceeding.


## Progress Log


- [x] 2026-05-24: Browser resize audit completed and documented in `docs/20260524_resizing_interactions_review.md`.
- [x] 2026-05-24: Initial structural direction identified: central layout policy first, no new dependency by default, browser geometry validation required.
- [x] 2026-05-24: First plan review subagent feedback incorporated into the earlier draft.
- [x] 2026-05-25: External reviewer comments received; required changes identified: non-destructive sidebar suppression, typed policy API, impossible-constraint priority, split grid/overlay insets, AppShell-owned mobile search state, persistence tests, overlay background interactivity checks, and tighter RSP-8 scope.
- [x] 2026-05-25: Plan-writer review subagent completed; feedback incorporated by narrowing the policy API, routing drag constraints through policy, exposing stronger debug evidence, seeding the browser harness earlier, adding per-ticket validation, constraining toolbar scope, tightening overlay isolation, and explicitly observing the `R10` metrics scenario.
- [x] 2026-05-25: Runtime execution request treated as approval of revised behavior boundaries and sprint order.
- [x] 2026-05-25: Sprint 1 implemented. `RSP-1` added `responsiveLayoutPolicy.ts` with typed model, constants, suppression reasons, grid/overlay inset outputs, shell reserves, and drag constraints. `RSP-2` routed AppShell and sidebar drag through the policy, removed destructive narrow auto-close, exposed debug data attributes, and split grid/overlay CSS variables. `RSP-3` added policy/drag persistence coverage and seeded `scripts/responsive_geometry_harness.py`.
- [x] 2026-05-25: Sprint 1 validation passed: focused layout Vitest suite, `npx tsc --noEmit`, full `npm run test`, `npm run build`, packaged frontend regeneration, `python scripts/responsive_geometry_harness.py --output-json /tmp/lenslet-responsive-geometry-sprint1.json`, `python scripts/gui_smoke_acceptance.py --output-json /tmp/lenslet-gui-smoke-sprint1.json`, and `python scripts/lint_repo.py`.
- [x] 2026-05-25: Sprint 1 cleanup/review gates completed. Cleanup made no code changes; review findings were addressed by adding generated assets to the commit set, aligning rendered and drag-time right-sidebar max width at oversized desktop preferences, and preserving mobile drawer safe-area reserve in `--mobile-drawer-h`.
- [x] 2026-05-25: Sprint 1 implementation handoff. Effective layout is now policy-owned and non-destructive; AppShell still passes `mobileSearchOpen: false` until `RSP-5`, and viewer/compare/drop overlays still read temporary `--left`/`--right` aliases until `RSP-7`.
- [ ] Pending: Sprint 2 implementation handoff.
- [ ] Pending: Sprint 3 implementation handoff.
- [ ] Pending: Sprint 4 implementation handoff.


## Artifacts and Handoff


Input audit:

1. `docs/20260524_resizing_interactions_review.md`

Revised execution plan:

1. `docs/20260525_responsive_layout_structural_plan.md`

Implementation handoff notes:

1. Start with `RSP-1`; do not begin toolbar, overlay, or inspector patches until the policy outputs and tests are explicit.
2. Treat `userLeftOpen` and `userRightOpen` as preferences. Treat `effectiveLeftOpen` and `effectiveRightOpen` as current layout facts.
3. Do not mutate persisted sidebar preferences during responsive suppression.
4. Use `--grid-left`/`--grid-right` for grid reservations and `--overlay-left`/`--overlay-right` for viewer/compare/drop overlays.
5. Use AppShell-owned mobile search state for toolbar reserved height ownership.
6. Do not add `@floating-ui/react`, `react-resizable-panels`, or any other dependency unless explicitly approved after fresh online package checks.
7. Treat `R8` as in scope because hidden drawer controls are reachability failures.
8. Treat `R9` and `R10` as deferred unless they produce a primary acceptance failure.
9. Sprint 1 shipped `scripts/responsive_geometry_harness.py` as the responsive evidence seed. It currently covers desktop/phone oversized-sidebar states, scroll-width overflow, DOM debug attributes, CSS variables, toolbar control rectangles, and resize-down/resize-up persistence preservation.
10. Sprint 2 should connect AppShell-owned `mobileSearchOpen` into the policy instead of relying on Toolbar-local state; this was intentionally left as `false` in Sprint 1 to avoid jumping ahead.
11. Sprint 3 should migrate viewer/compare/drop overlay paths from the temporary `--left`/`--right` aliases to `--overlay-left`/`--overlay-right`.

Revision note:

This revision incorporates external and plan-review feedback by replacing destructive sidebar language with non-destructive effective layout, narrowing the policy API to shared layout facts, defining impossible-constraint behavior, splitting grid and overlay insets, assigning toolbar reserve ownership to AppShell, adding persistence and absurd-width tests, moving the browser harness earlier, tightening toolbar/overlay/inspector scope, clarifying `R9`/`R10` acceptance impact, and moving agent/process rules into an implementation protocol inside the plan.
