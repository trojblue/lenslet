# Ranking Mode Interaction + Mini-App Slimming Plan


## Outcome + Scope Lock


After this iteration, ranking mode supports the requested top-first workflow: unranked images are shown larger on top, rank buckets sit at the bottom, and assignment can be done in a rapid keyboard cadence without repeated re-clicks. Fullscreen inspection supports pan and zoom, rank assignment, and image-to-image navigation.

Goals for this plan are:
1. Implement the layout and interaction changes from the user request, including `q/e` instance navigation, `Enter/Escape` fullscreen open and close, `a/d` navigation in fullscreen, and numeric rank assignment in both board and fullscreen contexts.
2. Keep the mini-app implementation fast and portable by minimizing coupling to browse-only components and avoiding heavyweight framework additions.
3. Keep ranking backend contracts stable (`/rank/*`, JSONL append-only persistence, resume/export semantics).
4. Update validation gates so every command in this plan is valid against the current repository state after commit `c64ac3b`.

Non-goals are introducing a mini-app registry framework, changing ranking save payload schema or backend route signatures, adding new runtime dependencies, and broad browse-shell refactors.

Pre-approved behavior changes are the layout inversion, keymap updates, fullscreen button per card, drag-resizable split, small color identity dots, and removal of `Rank ` label prefixes. Changes requiring sign-off are modifications to backend APIs, CLI shape, or browse mode interaction contracts.

Out-of-scope and deferred items are persisted splitter position, custom keybinding configuration UI, and generalized cross-mini-app component extraction beyond what is needed for this ranking iteration.


## Context


No `PLANS.md` exists in this repository, so this document is the execution source of truth and follows the required plan-writer format.

Current ranking UI remains in a column-first layout with `Unranked` as the first horizontal column and legacy keybindings (`Enter` next, `Backspace` previous) in `frontend/src/features/ranking/RankingApp.tsx`. Current ranking model tests are focused on pure state contracts in `frontend/src/features/ranking/model/__tests__/board.test.ts` and `session.test.ts` with Vitest running in Node mode.

Repository cleanup in commit `c64ac3b` removed prior ranking smoke and packaging-sync scripts/tests (`scripts/playwright_ranking_smoke.py`, `scripts/check_frontend_packaging_sync.py`, and associated pytest files), so validation steps must not reference them.

Layout reference for this implementation is the user-provided sketch committed at `docs/msedge_cPDvMjjYTr.png`. The plan uses this image as design intent for "unranked on top, ranks at bottom, larger preview area, and control placement."

Keyboard and focus contract is locked as follows. Initial order means the order of `instance.images` in dataset payload and is not recomputed from current board positions. Numeric rank assignment moves focus to the next unranked image in that initial order; if no unranked image remains, focus stays on the moved image. Reranking a ranked image keeps focus on that image unless explicit left/right navigation is requested. `q/e` navigate previous/next instance only in board mode and are ignored in fullscreen mode. `a/d` in fullscreen traverses in initial order. `Enter` opens fullscreen on focused image, `Escape` closes fullscreen and restores focus to the same image card in board mode. `Backspace` no longer performs previous-instance navigation.

Touch contract for this iteration is locked as: splitter drag is desktop-pointer only and is disabled on coarse-pointer/touch breakpoints to avoid drag gesture conflicts.


## Plan of Work


Implementation is split into three sprints so each sprint is demoable and testable, while preserving a strict complexity ceiling for mini-app portability.

Test strategy lock: keep Node-mode Vitest for ranking helper/state logic and use manual browser acceptance for UI gesture paths in this iteration. Do not introduce jsdom/RTL or new browser automation infrastructure as part of this change.

### Sprint Plan


1. Sprint 1 delivers keyboard-first interaction and lightweight fullscreen behavior.
   Sprint goal: remove click-heavy ranking cadence and implement mode-aware key handling.
   Demo outcome: user can rank quickly with repeated number keys, navigate instances with `q/e`, and inspect/rank in fullscreen using `Enter/Escape/a/d`.
   Sprint 1 status (2026-02-28): Completed in iteration `1/7` with `T1`-`T4` shipped.
   Tasks:
   1. T1: Update ranking board helpers to support deterministic auto-advance targeting next unranked image in `instance.images` order.
      Validation: extend `frontend/src/features/ranking/model/__tests__/board.test.ts` with auto-advance, rerank, unrank, and hydrated-session edge cases.
   2. T2: Refactor ranking keyboard routing in `RankingApp` to separate board-mode and fullscreen-mode keymaps and remove legacy `Backspace` previous behavior.
      Validation: add ranking key-routing helper tests and update in-app hotkey text assertions.
   3. T3: Add a ranking-local fullscreen overlay that supports URL-based image rendering with pan/zoom and does not depend on browse-only file-path APIs.
      Validation: manual acceptance verifies fullscreen open/close, pan/zoom, `a/d` traversal, and numeric rank assignment while fullscreen is open.
   4. T4: Add per-card fullscreen trigger control and remove `Rank ` prefix from rank headers (display `1`, `2`, `3`, ...).
      Validation: visual/manual check plus targeted ranking test assertions.

2. Sprint 2 delivers layout inversion, resizable split, and visual identity aids.
   Sprint goal: make unranked triage area dominant while preserving rank-drop usability and tie grouping.
   Demo outcome: unranked area appears at top with larger cards, bottom ranks remain actionable, split height can be dragged on desktop pointers, and each card has stable non-obtrusive color dot.
   Sprint 2 status (2026-02-28 07:16:31Z): Closed in iteration `2/7` with `T5`-`T8` shipped; cleanup/review gates completed, while manual ranking browser acceptance and GUI smoke blocker follow-up are carried into Sprint 3 release-gate work.
   Tasks:
   1. T5: Rework ranking layout/CSS to vertical sections (`unranked` top, `ranks` bottom) with responsive behavior for narrow screens.
      Validation: manual desktop/mobile viewport pass and targeted style checks.
   2. T6: Add draggable splitter with explicit min/max clamps between top and bottom sections for desktop pointers only.
      Validation: add pure clamp utility tests and manual drag verification on desktop pointers.
   3. T7: Add deterministic color-dot mapping based on initial image order using a small curated palette.
      Validation: add deterministic mapping tests in ranking model scope.
   4. T8: Harden pointer interaction boundaries so splitter drag and card drag-drop do not conflict.
      Validation: manual regression scenario drags splitter then cards in same session without breakage.

3. Sprint 3 delivers release-gate hardening and documentation alignment.
   Sprint goal: finish with a lean implementation that is easy to ship and maintain inside the mini-app model.
   Demo outcome: ranking changes pass current tests, compile/build cleanly, and docs match shipped behavior.
   Sprint 3 status (2026-02-28 07:29:34Z): In progress in iteration `3/7`; `T9` and `T10` are complete, while `T11` is blocked by a persistent `python scripts/gui_smoke_acceptance.py` timeout waiting for the browse `Compare images` dialog.
   Tasks:
   1. T9: Enforce portability boundary as a concrete done-check: ranking feature imports are limited to ranking-local modules plus approved shared primitives (`api/base`, `lib/fetcher`) and do not pull browse-heavy viewer/file-path APIs.
      Validation: import diff review and targeted cleanup commit if any violations are found.
   2. T10: Update README and ranking docs with the new keymap/layout behavior.
       Validation: doc text matches runtime UI labels and key behavior.
   3. T11: Run repository-valid command gates and capture evidence in this plan’s progress log.
       Validation: all listed commands execute successfully in the current repository state.

### Scope Budget and Guardrails


Scope budget is 3 sprints and 11 tasks, within the default cap.

Quality floor: ranking assignment correctness, autosave stability, deterministic focus behavior, and consistent fullscreen/board key routing must be preserved.

Maintainability floor: keep ranking changes within ranking feature modules and small helpers; avoid pushing ranking-specific complexity into global app shell structures.

Complexity ceiling: no new libraries, no new generic mini-app framework layer, and no replacement of current app-mode handshake.

Debloat and portability targets are:
1. Remove legacy key paths that contradict new UX (`Enter` as next and `Backspace` as previous).
2. Avoid coupling ranking fullscreen to browse-specific file-path APIs.
3. Keep validation lean by using existing test suites and deterministic manual acceptance rather than reintroducing removed heavy scripts.
4. Keep frontend changes constrained to ranking feature files and minimal shared helpers only when unavoidable.

### Execution Instructions


While implementing each sprint, update this plan continuously, especially Progress Log and Validation sections. After each sprint, add concise handoff notes with what shipped, what was verified, and what remains.

For minor script-level uncertainties such as helper file placement or naming, proceed according to this approved plan to maintain momentum. After each sprint, request clarification if needed and apply follow-up adjustments.

### Gate Routine (applies to every task T1-T11)


0. Plan gate (fast): restate goal, acceptance criteria, and exact files to touch before implementation.
1. Implement gate (correctness-first): implement the smallest coherent slice satisfying the ticket and run targeted checks.
2. Cleanup gate (reduce noise before review): after each sprint, run conservative cleanup of lint/style/dead-code noise without semantic expansion.
3. Review gate (review the ship diff): run independent review of the post-cleanup sprint diff, fix findings, and rerun when needed.

### code-simplifier routine


After each complete sprint, spawn a subagent and instruct it to use the `code-simplifier` skill to scan current sprint changes. Start with non-semantic cleanup first: formatting/lint autofixes, obvious dead code removal, small readability edits that do not change behavior, and doc/comments that reflect already-true behavior. Keep this pass conservative and do not expand into semantic refactors unless explicitly approved.

### review routine


After each complete sprint and after the cleanup subagent finishes, spawn a fresh agent and request a code review using the `code-review` skill. Review the post-cleanup diff, apply fixes, then rerun review when needed to confirm resolution.


## Validation and Acceptance


Validation hierarchy distinguishes primary real-user gates from secondary fast proxy gates.

Primary acceptance gates are:
1. Keyboard-first ranking gate: launch ranking mode on fixture dataset and complete one instance using only keyboard assignments after initial focus, with no per-image re-click requirement.
2. Fullscreen workflow gate: open fullscreen from a card, verify pan/zoom plus `a/d` navigation, assign ranks in fullscreen, and close with `Escape` while preserving focused image context.
3. Layout gate: verify unranked-top layout, drag splitter on desktop pointer to resize top region, rank-drop remains functional, and color dots remain stable while cards move.

Deterministic manual acceptance script is:
1. Start server with fixture: `lenslet rank data/fixtures/ranking_demo_picsum_20260228/ranking_dataset.json --port 7071`.
2. Click first unranked card once to seed focus.
3. Press `1`, then `2`, then `3`; expected: each key moves previously focused image to that rank and focus advances to next unranked image in dataset order.
4. Press `Enter`; expected: fullscreen opens for focused image.
5. Press `d`; expected: fullscreen target advances to next dataset-order image.
6. Press `1`; expected: current fullscreen image assigned to rank 1 and save status updates.
7. Press `Escape`; expected: fullscreen closes and same image card is focused in board mode.
8. Press `q` in board mode; expected: previous instance opens if available.
9. Press `Backspace`; expected: no instance navigation occurs.

Secondary acceptance gates are:
1. Ranking backend and CLI test suites remain green.
2. Ranking frontend model and key-routing tests remain green and include new auto-advance and palette determinism coverage.
3. TypeScript compile, frontend build, repository lint, and GUI smoke checks pass.
4. Browse baseline API/import checks remain green.

Planned command checks are:

    pytest tests/test_ranking_backend.py tests/test_ranking_cli.py -q
    pytest tests/test_import_contract.py tests/test_dataset_http.py -q
    cd frontend && npm run test -- src/features/ranking/model src/features/ranking src/app/model/__tests__/appMode.test.ts
    cd frontend && npx tsc --noEmit
    cd frontend && npm run build && rsync -a --delete dist/ ../src/lenslet/frontend/
    python scripts/gui_smoke_acceptance.py
    python scripts/lint_repo.py

Sprint 1 command evidence (2026-02-28):
1. `cd frontend && npm run test -- src/features/ranking src/app/model/__tests__/appMode.test.ts` -> pass (`4` files, `20` tests).
2. `cd frontend && npx tsc --noEmit` -> pass.
3. `cd frontend && npm run build` -> pass.
4. `python scripts/lint_repo.py` -> pass.
5. Cleanup and review routines completed via subagents using `code-simplifier` then `code-review`; one high and one low finding were fixed and follow-up review reported no remaining actionable findings.

Sprint 1 manual-acceptance note:
1. Browser/manual acceptance steps for fullscreen pan/zoom and keyflow are not executed in this CLI iteration and remain queued for Sprint 2/3 gate runs.

Sprint 2 command evidence (2026-02-28):
1. `cd frontend && npm run test -- src/features/ranking/model src/features/ranking` -> pass (`5` files, `26` tests), including new splitter clamp + palette determinism suites.
2. `cd frontend && npm run test -- src/features/ranking/model src/features/ranking src/app/model/__tests__/appMode.test.ts` -> pass (`6` files, `28` tests).
3. `cd frontend && npx tsc --noEmit` -> pass.
4. `cd frontend && npm run build && rsync -a --delete dist/ ../src/lenslet/frontend/` -> pass.
5. `python scripts/lint_repo.py` -> pass.
6. `python scripts/gui_smoke_acceptance.py` -> fail in this environment (`Compare images` dialog timeout after 45s in browse-mode path); captured as a Sprint 3 release-gate blocker for follow-up triage.
7. Sprint 2 cleanup/review routines completed via subagents (`code-simplifier`, then `code-review`); cleanup applied conservative readability edits, follow-up review reported no actionable findings.

Sprint 3 command evidence (2026-02-28):
1. `pytest tests/test_ranking_backend.py tests/test_ranking_cli.py -q` -> pass (`12` tests).
2. `pytest tests/test_import_contract.py tests/test_dataset_http.py -q` -> pass (`4` tests).
3. `cd frontend && npm run test -- src/features/ranking/model src/features/ranking src/app/model/__tests__/appMode.test.ts` -> pass (`6` files, `28` tests).
4. `cd frontend && npx tsc --noEmit` -> pass.
5. `cd frontend && npm run build && rsync -a --delete dist/ ../src/lenslet/frontend/` -> pass.
6. `python scripts/gui_smoke_acceptance.py` -> fail (`Compare images` dialog visibility timeout after `45000ms`).
7. `python scripts/gui_smoke_acceptance.py` (rerun) -> fail with same timeout/signature.
8. `python scripts/lint_repo.py` -> pass (ruff + file-size guardrails).
9. Sprint 3 cleanup/review routines completed via subagents (`code-simplifier` then `code-review`): cleanup was no-op, one review pass reported two issues in import-contract parsing/allowlist, fixes were applied, and follow-up review reported no actionable findings.

Expected outcomes are:
1. Rank assignment can proceed in a rapid `number -> number -> number` cadence after initial focus.
2. Fullscreen interaction and board interaction remain behaviorally consistent for ranking actions.
3. Top unranked area provides larger preview utility and is user-resizable on desktop pointers.
4. Ranking mini-app remains lightweight and portable without introducing new heavy infrastructure.


## Risks and Recovery


Primary risks are keyboard conflicts across board/fullscreen contexts, pointer conflicts between splitter and drag-drop, and accidental coupling to browse-specific viewer assumptions.

Recovery path is to keep changes isolated behind ranking-local helpers/components so regressions can be rolled back sprint-by-sprint without backend or browse disruptions.

Idempotent retry strategy remains the current autosave pattern and backend latest-entry collapse behavior. This plan does not change backend persistence semantics.

If portability guardrails are threatened during implementation, fallback is to ship a ranking-local fullscreen component with minimal dependencies and defer broader shared abstraction to a separate approved follow-up.

Current Sprint 3 blocker:
1. `python scripts/gui_smoke_acceptance.py` repeatedly times out waiting for the browse `Compare images` dialog (`Locator.wait_for` at `45000ms`) despite otherwise healthy API traffic in server logs.
2. Proposed unblock: next iteration performs focused browse compare-flow triage (script selector/interaction sequence vs UI behavior), lands the minimal fix, and reruns the full T11 gate set until green.


## Progress Log


- [x] 2026-02-28 06:23:15Z Initial interaction/layout iteration plan drafted.
- [x] 2026-02-28 06:26:54Z Mandatory review feedback integrated into first revision.
- [x] 2026-02-28 06:36:40Z Revalidated plan against cleanup commit `c64ac3b` and removed stale references to deleted ranking smoke/packaging scripts.
- [x] 2026-02-28 06:36:40Z Added explicit mini-app portability/debloat scope and layout-sketch path reference (`docs/msedge_cPDvMjjYTr.png`).
- [x] 2026-02-28 06:42:05Z Integrated second review feedback: tightened key contracts, made portability boundary concrete, and added deterministic manual acceptance script.
- [x] 2026-02-28 06:45:41Z Sprint 1 implementation started (`T1`-`T4` scope lock confirmed).
- [x] 2026-02-28 07:00:51Z Sprint 1 implementation completed (`T1`-`T4`): board auto-advance helper + tests, mode-aware keyboard routing, ranking-local fullscreen overlay with pan/zoom + `a/d` traversal, per-card fullscreen control, and rank header label cleanup.
- [x] 2026-02-28 07:00:51Z Sprint 1 cleanup/review gates completed: `code-simplifier` cleanup pass applied, `code-review` pass run twice, Enter-key interactive-control regression fixed, and follow-up review returned no remaining actionable findings.
- [x] 2026-02-28 07:07:03Z Sprint 2 implementation started (`T5`-`T8` scope lock confirmed).
- [x] 2026-02-28 07:07:03Z Sprint 2 implementation completed (`T5`-`T8`): unranked-top / ranks-bottom workspace with responsive mobile fallback, desktop-pointer splitter with clamped bounds, deterministic card color-dot mapping from initial image order, and splitter/card drag boundary hardening.
- [x] 2026-02-28 07:16:31Z Sprint 2 cleanup and review gates completed: `code-simplifier` and `code-review` subagent routines run on post-implementation diff, no actionable defects remained.
- [x] 2026-02-28 07:16:31Z Sprint 2 validation sweep run: ranking/app-mode tests, TypeScript, frontend build, and repo lint passed; `gui_smoke_acceptance.py` failed with `Compare images` dialog timeout and is tracked for Sprint 3 release-gate triage.
- [x] 2026-02-28 07:20:00Z Sprint 3 implementation started (`T9`-`T11` scope lock confirmed).
- [x] 2026-02-28 07:20:00Z Sprint 3 partial implementation completed (`T9`, `T10`): ranking import-boundary contract coverage added in `tests/test_import_contract.py`, and README + ranking specification docs now match shipped keymap/layout behavior.
- [x] 2026-02-28 07:29:34Z Sprint 3 cleanup and review gates completed: `code-simplifier` subagent performed no-op cleanup pass; `code-review` found two import-contract issues, fixes were applied, and follow-up review returned no actionable findings.
- [x] 2026-02-28 07:29:34Z Sprint 3 validation sweep executed: pytest ranking/backend + import/dataset gates, Vitest ranking/app-mode gates, TypeScript, frontend build+bundle sync, and lint passed; GUI smoke blocker reproduced on two runs.
- [ ] 2026-02-28 07:29:34Z Final validation and handoff notes blocked pending browse `Compare images` dialog timeout triage/fix and a green rerun of `python scripts/gui_smoke_acceptance.py`.


## Artifacts and Handoff


Primary artifact is this plan at `docs/20260228_ranking_mode_interaction_layout_iteration_plan.md`.

Key implementation touch points are expected in:
1. `frontend/src/features/ranking/RankingApp.tsx`
2. `frontend/src/features/ranking/ranking.css`
3. `frontend/src/features/ranking/model/board.ts`
4. `frontend/src/features/ranking/model/session.ts` and ranking model tests
5. ranking docs/README sections describing keybindings and layout behavior

Operator handoff notes after each sprint should include the exact keymap behavior, fullscreen boundary decisions, splitter clamp constants, palette mapping rule, and whether any portability boundary exceptions were needed.

Sprint 1 handoff notes (closed 2026-02-28):
1. Keymap shipped: board mode uses `1-9` rank (with deterministic unranked auto-advance in initial dataset order), `ArrowLeft/ArrowRight` selection movement, `q/e` instance prev/next, and `Enter` fullscreen open. Fullscreen mode uses `1-9` rank current image, `a/d` prev/next image in initial order, and `Escape` close.
2. Fullscreen boundary: ranking-local overlay in `RankingApp` uses image URLs only, supports wheel zoom + pointer pan, and restores focus to the same card on close; no browse-specific viewer/file-path API imports were introduced.
3. UI updates delivered: per-card fullscreen trigger button, rank headers rendered as `1`, `2`, `3`, and footer hotkey text updated to new contract.
4. Portability exceptions: none needed for Sprint 1.
5. Remaining scope: Sprint 2 (`T5`-`T8`) layout inversion + splitter + color dots.

Sprint 2 handoff notes (closed 2026-02-28):
1. Layout inversion shipped in `RankingApp` + `ranking.css`: unranked cards now occupy a larger top workspace panel, rank buckets move to a dedicated bottom panel, and narrow/coarse-pointer layouts collapse to non-resizable stacked behavior.
2. Splitter implementation is ranking-local: desktop mouse pointer only, min/max clamped by `frontend/src/features/ranking/model/layout.ts` constants (`RANKING_MIN_UNRANKED_HEIGHT_PX=220`, `RANKING_MIN_RANKS_HEIGHT_PX=180`, `RANKING_SPLITTER_HEIGHT_PX=10`) with dedicated model tests.
3. Deterministic card identity dots shipped via `frontend/src/features/ranking/model/palette.ts`, mapping unique image IDs in initial dataset order onto a small curated palette; dot rendering is applied consistently in all card locations.
4. Pointer-boundary hardening shipped: splitter resize mode suppresses card drag/drop interactions, splitter pointerdown ignores non-mouse pointers, and drag state is cleared when resizing begins to avoid interaction crossover.
5. Portability exceptions: none. New logic is ranking-local and does not import browse-heavy modules.

Sprint 3 handoff notes (in progress 2026-02-28):
1. Portability boundary is now enforced by automated import-contract coverage in `tests/test_import_contract.py`: ranking feature imports must resolve inside `frontend/src/features/ranking` unless explicitly allowlisted (`../../api/base`, `../../lib/fetcher`), and `vitest` imports are limited to ranking test files.
2. Operator docs now match shipped interaction behavior in `README.md` and `docs/20260227_SPEC_ranking_tool.md` (unranked-top layout, desktop-only splitter drag, board/fullscreen keymaps, and `Backspace` no-op for instance navigation).
3. Release-gate status: all Sprint 3 validations except GUI smoke are green; blocker remains the browse `Compare images` dialog timeout in `python scripts/gui_smoke_acceptance.py`, with follow-up triage queued for next iteration.

Revision note: this revision updates repository alignment after commit `c64ac3b`, removes outdated validation references, adds explicit mini-app lightweight/portable guardrails, explicitly references the committed layout sketch path, and incorporates mandatory second-pass review feedback.
