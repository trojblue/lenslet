# Ranking Mode Interaction and Layout Iteration Plan


## Outcome + Scope Lock


After this iteration, ranking mode supports a top-first workflow where unranked images are large and fast to triage, while rank buckets sit below for drop placement and tie grouping. Keyboard flow is optimized for speed: a user can assign with number keys continuously without re-clicking each image, navigate instances with `q` and `e`, open or close focused fullscreen with `Enter` and `Escape`, and navigate images inside fullscreen with `a` and `d` while still assigning ranks.

Goals for this iteration are to implement the requested layout inversion (unranked top, ranks bottom), add focus-preserving keyboard behavior, remove `RANK` text prefixes, add fullscreen entry points on image cards with pan/zoom parity, add draggable vertical resize for the unranked region, and add small stable color dots per image for quick visual identity.

Non-goals are backend contract changes, dataset format changes, autosave/persistence protocol changes, multi-user features, and browse-mode UX refactors.

Explicit approvals in scope are all behavior changes listed in the user request, including remapping navigation hotkeys from `Enter` and `Backspace` to `q` and `e` for instance navigation, and enabling rank assignment while fullscreen is open. Items requiring sign-off are any change to save payload schema, `/rank/*` endpoint signatures, or browse-mode viewer behavior.

Deferred or out-of-scope items are advanced per-user keybinding customization, configurable color palettes, persistent splitter height preferences, and rank-column reordering semantics beyond the current tie-group model.


## Context


No `PLANS.md` exists in this repository; this document is the execution source of truth and follows the required plan-writer format.

Current ranking implementation lives primarily in `frontend/src/features/ranking/RankingApp.tsx` and `frontend/src/features/ranking/ranking.css`. It uses a column-first board with `Unranked` as the first column, selected-image key assignment (`1-9`), `Enter` for next instance, and `Backspace` for previous instance. There is already a mature pan/zoom viewer stack in browse mode (`frontend/src/features/viewer/Viewer.tsx` and `frontend/src/features/viewer/hooks/useZoomPan.ts`) that should be reused through a ranking-local adapter so ranking can operate on its existing URL-based image payloads without broad browse coupling.

Keyboard contract for this iteration is locked as follows: after numeric assignment the focus moves to the next image in initial instance order that is not yet assigned, and when all are assigned it stays on the moved image; reranking an already-ranked image keeps focus on that image unless explicit left or right navigation is used; when fullscreen closes, focus returns to the same image card in board mode; `q/e` navigate instances only in board mode and do nothing while fullscreen is open; `Enter` in board mode opens fullscreen on the focused image and never advances instance; `Backspace` no longer performs previous-instance navigation.


## Plan of Work


Implementation proceeds in three sprints so each sprint is independently demoable and testable, with strict containment to ranking frontend files plus targeted tests and smoke updates.

Test strategy lock for this plan is to keep Vitest in its current Node-mode usage for pure helpers and deterministic logic, and route viewport, pointer, and end-user interaction assertions through Playwright smoke coverage instead of introducing new frontend test infrastructure in this iteration.

### Sprint Plan


1. Sprint 1: Interaction model and keyboard flow redesign.
   Sprint goal: convert ranking from click-heavy selection flow to continuous keyboard-first assignment with explicit mode-aware shortcuts.
   Demo outcome: user can press rank keys repeatedly without reselecting each image; `q/e` change instances; `Enter/Escape` open/close focused fullscreen; `a/d` navigate images in fullscreen.
   Tasks:
   1. T1: Update ranking board state helpers to support deterministic next-focus-after-assign behavior rooted in initial image order and current placement.
      Validation: extend `frontend/src/features/ranking/model/__tests__/board.test.ts` for focus advancement, edge cases at tail image, rerank behavior, and no-unranked terminal behavior.
   2. T2: Refactor `RankingApp` keyboard handler into mode-aware shortcuts and migrate instance navigation to `q/e` in board mode only.
      Validation: add tests for shortcut routing, editable-target guards, and explicit assertion that `Enter` does not advance instance and `Backspace` does not navigate previous.
   3. T3a: Implement ranking fullscreen modal lifecycle and focus restoration (`Enter` opens, `Escape` closes, return focus to same image).
      Validation: add interaction tests for modal open/close and focus restoration semantics.
   4. T3b: Add fullscreen keyboard routing (`a/d` image navigation, `1..N` rank assignment) while preserving autosave ordering and stale-response safety.
      Validation: add tests for fullscreen key routing and save-sequence invariants under repeated assignments.
   5. T4: Remove `Rank` label prefix in headers so columns display numeric labels only.
      Validation: include UI assertion in ranking smoke and ranking component checks.

2. Sprint 2: Layout and visual clarity upgrade.
   Sprint goal: make unranked triage area visually dominant and adjustable, while retaining bottom rank drop zones for placement and ties.
   Demo outcome: unranked region is on top with larger previews, bottom rank strip remains usable, drag handle resizes split, each card has fullscreen trigger, and color dots are visible but non-obstructive.
   Tasks:
   1. T5: Rework ranking layout and CSS into vertical split sections (`unranked` top, `ranks` bottom) with responsive fallback for narrow screens.
      Validation: Playwright assertions verify desktop and mobile breakpoints render without overflow regressions.
   2. T6: Add draggable splitter for unranked height with clamped min/max behavior and no persistence.
      Validation: unit tests for clamp math plus Playwright assertion that splitter drag changes visible split height.
   3. T7: Add per-card top-right fullscreen button and connect it to ranking fullscreen modal while preserving drag-and-drop behavior on card body.
      Validation: Playwright asserts button opens modal and drag start still works from non-button card region.
   4. T8: Add stable, small bottom-left color dots based on initial image order using a curated palette.
      Validation: tests verify deterministic mapping and consistent color identity across rank moves.
   5. T9: Add a regression test for pointer-gesture separation so splitter drag and card drag-and-drop do not steal each other’s events.
      Validation: Playwright scenario drags splitter then drags cards and confirms both paths remain functional.

3. Sprint 3: Hardening, regression gates, and operator docs.
   Sprint goal: prove the upgraded workflow is fast, stable, and isolated from browse behavior.
   Demo outcome: smoke path exercises keyboard-only assignment, fullscreen interactions, splitter drag, and export path while existing browse isolation checks stay green.
   Tasks:
   1. T10: Update `scripts/playwright_ranking_smoke.py` to cover the new primary operator path (`1-5` assignment cadence, `q/e`, fullscreen `Enter/Escape`, fullscreen `a/d`, splitter drag, deprecated-key checks).
       Validation: update `tests/test_playwright_ranking_smoke.py` contracts and run ranking smoke end-to-end.
   2. T11: Add or refresh ranking frontend tests for layout semantics, key remap, fullscreen controls, and color-dot determinism.
       Validation: targeted Vitest run for touched ranking suites plus `tsc --noEmit`.
   3. T12: Update ranking usage docs and in-app hotkey hints to match the new workflow.
       Validation: docs sanity check against rendered UI text and smoke script expectations.

### Scope Budget and Guardrails


Scope budget is 3 sprints and 12 tasks, matching the default maximum. File touch budget is limited to ranking frontend modules and styles, ranking model tests, ranking smoke scripts and tests, and ranking docs/help text, plus either reuse touch in `frontend/src/features/viewer/hooks/useZoomPan.ts` or a ranking-local viewer adapter component if that is cleaner.

Quality floor: keyboard flow must never drop selection unexpectedly, fullscreen interactions must preserve rank assignment correctness, and drag/drop plus autosave behavior must remain stable.

Maintainability floor: prefer extracting small ranking-local helpers/components over expanding `RankingApp.tsx` monolithically, and reuse existing zoom/pan primitives where possible through narrow interfaces.

Complexity ceiling: no backend API changes, no app-mode router redesign, and no new frontend test framework introduction.

Debloat/removal list for this iteration is to delete obsolete `Enter-next` and `Backspace-prev` ranking shortcuts, remove redundant click-to-select dependency in the main keyboard path, and remove `Rank ` text prefix rendering.

### Execution Instructions


While implementing each sprint, update this plan continuously, especially the Progress Log and Validation sections. After each sprint is complete, add concise handoff notes describing shipped behavior, commands run, and remaining open items.

For minor script-level uncertainties such as exact helper file placement or naming, proceed according to this approved plan to maintain momentum. After each sprint, request clarification if needed and apply follow-up adjustments.

### Gate Routine (applies to every task T1-T12)


0. Plan gate (fast): restate task goal, acceptance criteria, and exact files to touch before implementation.
1. Implement gate (correctness-first): implement the smallest coherent slice that satisfies the task and run minimal targeted verification.
2. Cleanup gate (reduce noise before review): after each sprint, run a conservative cleanup pass before formal review.
3. Review gate (review the ship diff): run independent review on post-cleanup diff, fix findings, and rerun review as needed.

### code-simplifier routine


After each complete sprint, spawn a subagent and instruct it to use the `code-simplifier` skill to scan current sprint changes. Start with non-semantic cleanup first: formatting/lint autofixes, obvious dead code removal, small readability edits that do not change behavior, and doc/comments that reflect already-true behavior. Keep the pass conservative and do not expand into semantic refactors unless explicitly approved.

### review routine


After each complete sprint and after the cleanup subagent finishes, spawn a fresh agent and request a code review using the `code-review` skill. Review the post-cleanup diff, apply fixes, then rerun review when needed to confirm resolution.


## Validation and Acceptance


Validation hierarchy uses primary real-path checks first and secondary fast gates second.

Primary acceptance gates are:
1. Sprint 1 primary gate: with a real ranking fixture, assign all images for one instance using keyboard-only flow without additional clicks after first focus; confirm automatic focus progression and `q/e` instance navigation.
2. Sprint 2 primary gate: verify top and bottom layout with larger unranked cards, drag splitter to change unranked height, and open fullscreen from card button for pan/zoom inspection and rank assignment.
3. Sprint 3 primary gate: run the full browser smoke covering keyboard cadence, fullscreen controls, splitter drag, deprecated-key non-behavior, reload resume, and completed export collapse behavior.

Secondary acceptance gates are:
1. Ranking helper and unit tests for focus advancement, split-size clamps, and color mapping determinism.
2. Ranking keyboard and modal tests for key routing, modal lifecycle, and numeric-only rank labels.
3. Type/lint and existing ranking backend smoke contracts to ensure no mode-boot regressions.

Planned command checks are:

    cd frontend && npm run test -- src/features/ranking/model/__tests__/board.test.ts src/features/ranking/model/__tests__/session.test.ts
    cd frontend && npm run test -- src/features/ranking/model src/features/ranking
    cd frontend && npx tsc --noEmit
    pytest tests/test_playwright_ranking_smoke.py -q
    python scripts/playwright_ranking_smoke.py --output-json data/fixtures/ranking_smoke_result.json
    cd frontend && npm run build && cd ..
    rsync -a --delete frontend/dist/ src/lenslet/frontend/
    python scripts/check_frontend_packaging_sync.py
    pytest tests/test_browse_canary_ranking_isolation.py tests/test_frontend_packaging_sync.py -q
    python scripts/lint_repo.py

Overall acceptance criteria are:
1. The user can complete an instance in a continuous `rank-key -> rank-key` cadence without re-clicking each card.
2. The user can inspect any card in fullscreen with pan/zoom and continue ranking from that mode.
3. The user can resize the unranked region interactively and still drag images into rank columns.
4. Deprecated ranking navigation keys are removed as intended (`Enter` does not advance; `Backspace` does not go previous).
5. UI labels, hints, and smoke automation all reflect the new keymap and layout.


## Risks and Recovery


Primary risks are shortcut collisions after key remap, drag-resize interference with drag/drop gestures, and fullscreen focus traps causing stale keyboard routing.

Recovery path is to keep interaction logic behind ranking-local handlers and small pure helpers so regressions can be rolled back per sprint without touching backend contracts. If fullscreen integration destabilizes delivery, fallback is to ship modal lifecycle and rank-assignment support first, then stage additional viewer polish behind explicit follow-up approval.

Idempotent retry strategy remains the existing save-sequence approach; this iteration must not alter save ordering semantics. Any transient UI error in modal or splitter state must be recoverable by reload without corrupting persisted ranking entries.


## Progress Log


- [x] 2026-02-28 06:23:15Z Investigated current ranking implementation, smoke tests, and existing viewer primitives.
- [x] 2026-02-28 06:23:15Z Locked scope from requested behavior deltas and documented implementation assumptions.
- [x] 2026-02-28 06:26:54Z Mandatory subagent review completed and feedback incorporated to tighten contracts and de-scope non-essential persistence.
- [ ] 2026-02-28T00:00:00Z Sprint 1 implementation started.
- [ ] 2026-02-28T00:00:00Z Sprint 1 cleanup and review gates completed.
- [ ] 2026-02-28T00:00:00Z Sprint 2 implementation started.
- [ ] 2026-02-28T00:00:00Z Sprint 2 cleanup and review gates completed.
- [ ] 2026-02-28T00:00:00Z Sprint 3 implementation started.
- [ ] 2026-02-28T00:00:00Z Sprint 3 cleanup and review gates completed.
- [ ] 2026-02-28T00:00:00Z Final validation and handoff notes completed.


## Artifacts and Handoff


Primary artifact is this plan at `docs/20260228_ranking_mode_interaction_layout_iteration_plan.md`.

Expected implementation touch points are:
1. `frontend/src/features/ranking/RankingApp.tsx`
2. `frontend/src/features/ranking/ranking.css`
3. `frontend/src/features/ranking/model/board.ts`
4. ranking frontend tests under `frontend/src/features/ranking/**/__tests__`
5. `scripts/playwright_ranking_smoke.py` and `tests/test_playwright_ranking_smoke.py`
6. ranking usage notes in docs and README where hotkeys and layout are documented
7. optional ranking-local viewer adapter or scoped zoom-pan reuse module

Initial operator command transcript template is:

    git status --short
    cd frontend && npm run test -- src/features/ranking/model/__tests__/board.test.ts src/features/ranking/model/__tests__/session.test.ts
    python scripts/playwright_ranking_smoke.py --output-json data/fixtures/ranking_smoke_result.json

Handoff notes for the next operator should include the exact keymap implemented, fullscreen focus-restore rule, splitter clamp values, and palette mapping rule.

Revision note: this version incorporates mandatory subagent review by adding explicit keyboard edge contracts, locking test strategy to existing tooling, splitting oversized fullscreen work into smaller tasks, adding real packaging-sync gates, adding deprecated-key removal acceptance, and de-scoping splitter persistence to keep scope tight.
