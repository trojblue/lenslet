# Ranking Mode Execution Plan for Lenslet


## Outcome + Scope Lock


After implementation, operators can launch a dedicated ranking workflow with `lenslet rank <dataset.json>`, annotate image instances with ties, autosave progress, resume sessions, and export collapsed latest-per-instance results without creating a separate repository. Ranking logic remains isolated in ranking-specific modules so future mini-apps can be added through the same composition seams without introducing a registry framework in this phase.

Goals for this plan are:
1. Add a first-class ranking mode with dedicated backend modules and route bundle, plus a dedicated frontend mode path, launched via CLI subcommand.
2. Reuse existing shared primitives only where they are genuinely generic, especially HTTP/fetch helpers and existing image delivery paths.
3. Keep browse mode behavior and contracts stable.
4. Deliver robust JSONL append-only persistence with optional collapsed JSON export.

Non-goals for this plan are:
1. No multi-user, authentication, assignment queues, or database integration.
2. No generalized mini-app registry framework in this phase.
3. No repository split or separate package publication.
4. No broad browse-shell refactor.

Locked functional decisions for this implementation are:
1. Ranking API is namespaced under `/rank/*` to avoid route collisions, and `GET /health` in ranking mode reports `mode: "ranking"`.
2. Resume rule is deterministic: client opens at `last_completed_instance_index + 1` when available, otherwise index `0`.
3. Dataset image paths are local filesystem only, may be absolute or relative to dataset JSON location, and are validated for existence at load time.
4. Results persistence defaults to a workspace path outside image directories, with optional `--results-path` override; writes must never target a directory that contains served image files.
5. Export defaults to all latest saved entries; `completed_only=true` is optional filtering.

Approval matrix for behavior changes is:
1. Pre-approved: `lenslet rank <dataset.json>` CLI shape, single frontend app with ranking mode branch, reuse of existing image-serving mechanisms when appropriate, and optional collapsed export endpoint in addition to JSONL append log.
2. Requires sign-off: any change to default browse launch behavior, any incompatible API change in existing browse routes, or any new registry-style architecture that increases framework surface.

Deferred and out-of-scope items are: multi-app registry extraction, separate package/repo split, collaborative annotation features, and advanced ranking analytics beyond core metadata in the provided spec.


## Context


No `PLANS.md` file exists in this repository, so this document is the execution source of truth and is written to satisfy the plan format requirements directly.

Current architecture has reusable seams in backend app creation and route registration, but browse assumptions remain implicit in several modules. Frontend has reusable shared utilities, while the primary browse shell is monolithic and should not be entangled with ranking flow internals.

Scope-lock decisions from the user are: use `lenslet rank <dataset.json>`, keep one frontend app for now, reuse existing image/thumb delivery where appropriate, include optional collapsed export endpoint, and avoid introducing a registry abstraction at this stage.

In this plan, “ranking mode” means a separate application mode within the same package and deployable, not a feature flag inside browse workflows. “Isolated module” means ranking-specific backend and frontend code placed in dedicated namespaces and imported by composition boundaries rather than cross-feature reach-ins.


## Plan of Work


Implementation follows three sprints so each sprint is independently demoable and testable while keeping total scope bounded.

### Sprint Plan


1. Sprint 1 builds ranking backend foundations and CLI launch compatibility.
   Status: completed in iteration 1 (2026-02-28).
   Sprint goal: produce a runnable ranking backend with validated persistence and explicit app factory entrypoint.
   Demo outcome: `lenslet rank <dataset.json>` starts cleanly, ranking endpoints respond, append-only saves survive reload, and existing `lenslet <directory>` behavior remains unchanged.
   Tasks:
   1. [x] T1: Add `src/lenslet/ranking/` domain modules for dataset parsing, ranking payload validation, and deterministic resume/progress derivation.
   2. [x] T2: Add ranking persistence module for append-only JSONL writes with file lock, malformed-tail tolerance, latest-entry collapse, and safe results-path validation.
   3. [x] T3: Add ranking app factory and ranking routes under `/rank/*`, plus ranking-mode health payload.
   4. [x] T4: Migrate CLI parser to include `rank` subcommand with minimal V1 flags (`--host`, `--port`, `--reload`, `--results-path`) and add compatibility tests for existing browse invocation.

2. Sprint 2 builds ranking frontend mode and interaction flow.
   Sprint goal: deliver a focused ranking UI branch isolated from browse shell internals.
   Demo outcome: user can place images across rank columns, navigate with mouse/keyboard, autosave safely, and resume session state correctly.
   Tasks:
   1. T5: Add ranking frontend mode boot path and mode handshake using ranking health/API contracts while keeping browse mount path intact.
   2. T6: Implement ranking board core interactions: fixed rank columns, drag/drop moves, selected-card state, and navigation guards.
   3. T7: Implement keyboard controls, autosave triggers, resume/load behavior, and stale-write prevention policy for out-of-order save responses.

3. Sprint 3 hardens behavior, validates cross-mode safety, and finalizes documentation.
   Sprint goal: verify ranking behavior end-to-end and prove browse remains stable.
   Demo outcome: ranking flow passes realistic MVP usage checks, browse canary checks pass, and operator docs are complete.
   Tasks:
   1. T8: Add backend tests for validation invariants, persistence collapse semantics, malformed trailing JSONL handling, and stale-write acceptance policy.
   2. T9: Add frontend tests plus one browser smoke for ranking session flow including autosave/resume/navigation constraints.
   3. T10: Add browse canary regression gates and frontend packaging sync gate to ensure shipping assets remain aligned.
   4. T11: Update docs/README usage and add concise operator handoff notes for ranking mode launch, data format, export semantics, and limits.

### Scope Budget and Guardrails


Scope budget is three sprints and eleven tasks. Planned edits are limited to CLI wiring, app factory composition, dedicated ranking backend modules, dedicated ranking frontend modules, targeted tests, and documentation updates. No cross-cutting framework rewrite is budgeted.

Quality guardrails are:
1. Quality floor: save/export correctness, validation before persistence, and crash-tolerant JSONL handling are mandatory.
2. Maintainability floor: ranking code must live in dedicated modules with explicit interfaces; browse modules are touched only at composition seams.
3. Complexity ceiling: no registry framework, no new infrastructure service, and no speculative abstractions for future mini-apps.

Removal/debloat constraints are:
1. Keep CLI flags minimal for ranking V1 and avoid porting browse-only flags.
2. Avoid duplicate fetch/API helpers; reuse existing generic utilities where they already fit.
3. Keep ranking-specific styles and state isolated; do not broaden global browse styles beyond mode-level integration points.

### Execution Instructions


While implementing each sprint, update this plan document continuously, especially the Progress Log and any acceptance notes that changed. After each sprint is complete, append clear handoff notes describing what shipped, what was validated, and what remains open.

For minor script-level uncertainties, such as exact file placement or helper naming, proceed according to this approved plan to maintain momentum. After the sprint finishes, request clarification and then apply follow-up adjustments if needed.

### Gate Routine (applies to every task T1-T11)


0. Plan gate (fast): restate task goal, acceptance criteria, and exact files to touch before edits.
1. Implement gate (correctness-first): implement the smallest coherent slice for the task and run task-targeted verification signals.
2. Cleanup gate (reduce noise before review): run conservative cleanup after each completed sprint.
3. Review gate (review the ship diff): run independent review after cleanup, address findings, and rerun review when needed.

### code-simplifier routine


After each complete sprint, spawn a subagent and instruct it to use the `code-simplifier` skill to scan current sprint changes. Start with non-semantic cleanup first: lint/format autofixes, obvious dead code removal, small readability edits that do not change behavior, and comments/docs that reflect already-true behavior. Keep this pass conservative and do not expand into semantic refactors unless explicitly approved.

### review routine


After each complete sprint and after the cleanup subagent finishes, spawn a fresh agent and request a code review using the `code-review` skill. Review the post-cleanup diff, fix findings, and rerun review until no blocking issues remain for that sprint scope.


## Interfaces and Dependencies


Ranking backend interfaces in this plan are:
1. `GET /rank/dataset` returns dataset instances and ranking configuration needed by the client.
2. `POST /rank/save` appends one validated ranking event to JSONL.
3. `GET /rank/progress` returns completed instance ids and `last_completed_instance_index`.
4. `GET /rank/export` returns collapsed latest-per-instance JSON and supports `completed_only=true`.
5. `GET /health` includes `mode: "ranking"` when launched via `lenslet rank`.

CLI interface in this plan is:
1. `lenslet rank <dataset.json> [--host ...] [--port ...] [--reload] [--results-path ...]`.
2. Existing browse invocation `lenslet <directory|table>` remains unchanged and covered by compatibility tests.

Frontend dependencies in this plan are mode-gated entry/mount logic and ranking-specific API/model modules. Shared dependencies are limited to existing generic fetch/base/request-budget utilities and existing image delivery endpoints only when contracts fit unchanged behavior.

Operational dependencies are local filesystem read access for dataset/images and controlled local filesystem write access for results JSONL outside served image directories by default.


## Validation and Acceptance


Validation hierarchy distinguishes primary acceptance gates, which mirror real operator workflow, from secondary fast proxy checks.

Primary acceptance gates are:
1. Sprint 1 primary gate: run ranking mode backend with a real dataset JSON and verify valid saves append lines, invalid saves are rejected, and browse CLI entry still works unchanged.
2. Sprint 2 primary gate: execute full ranking session in browser with drag/drop and keyboard controls, including autosave and deterministic resume after refresh.
3. Sprint 3 primary gate: run a representative MVP dataset scenario (for example 100 instances with 5 images each on local filesystem), complete a meaningful annotation pass, export collapsed results, and verify latest-entry-per-instance correctness.

Secondary acceptance gates are:
1. Backend unit/integration tests for validation, persistence collapse behavior, malformed-tail tolerance, and stale-write handling.
2. Frontend tests for ranking state transitions, keybindings, navigation guard behavior, and mode boot contract.
3. Browse canary tests and packaging/build sync checks.
4. Repo lint/type checks for touched areas.

Planned command checks are:

    pytest tests/test_ranking_*.py -q
    pytest tests/test_import_contract.py tests/test_dataset_http.py -q
    cd frontend && npm run test -- src/features/ranking
    cd frontend && npx tsc --noEmit
    cd frontend && npm run build && cp -r dist/* ../src/lenslet/frontend/
    python scripts/lint_repo.py
    lenslet rank data/fixtures/ranking_dataset.json --port 7071

Sprint 1 execution evidence (2026-02-28):
1. `pytest tests/test_ranking_*.py -q` -> pass (10 tests).
2. `pytest tests/test_import_contract.py -q` -> pass.
3. `python scripts/lint_repo.py` -> pass (`ruff` clean; existing frontend file-size warnings unchanged).
4. `lenslet rank data/fixtures/ranking_dataset.json --port 7071` -> deferred in this iteration because no checked-in ranking fixture exists yet; API behavior is covered by `tests/test_ranking_backend.py`.

Expected outcomes are:
1. Ranking tests pass and browse canary tests confirm no regression in existing entrypoints/contracts.
2. Ranking session is resumable and autosave is non-blocking with stale-write protection.
3. Export output is deterministic for latest-entry collapse and ignores malformed trailing JSONL line fragments.

Deferred validation note: a 500+ instance soak run is tracked as post-merge follow-up and is not a blocking V1 acceptance gate.


## Risks and Recovery


Key risks are accidental browse regressions from shared composition points, frontend CSS bleed between browse and ranking modes, and autosave race conditions causing stale persistence.

Recovery strategy is to keep ranking code in isolated modules and integrate through narrow seams, allowing rollback by removing ranking mode wiring without touching browse internals. Persistence writes are append-only; retries are safe because read paths collapse to latest valid entry per instance.

Idempotent retry strategy is to include monotonic save ordering metadata and ignore stale save responses when a newer local state has already been accepted. This closes out-of-order autosave races without requiring transactional infrastructure.

Hidden dependency risk exists around image serving assumptions. Mitigation is to reuse existing image-serving APIs only when contracts fit unchanged behavior; otherwise add a ranking-local media read path instead of mutating browse contracts.


## Progress Log


- [x] 2026-02-28 04:52:07Z Scope lock confirmed with user decisions for CLI shape, frontend shape, reuse boundary, export behavior, and anti-overengineering constraint.
- [x] 2026-02-28 04:52:07Z Initial implementation plan drafted with three sprints.
- [x] 2026-02-28 04:56:49Z Mandatory subagent review completed and feedback incorporated.
- [x] 2026-02-28 05:36:00Z Sprint 1 T1-T4 implemented: ranking domain/persistence/app/routes/CLI delivered with targeted backend and CLI tests.
- [x] 2026-02-28 05:36:00Z Sprint 1 cleanup + review gates completed: code-simplifier pass, independent reviews, and follow-up fixes for malformed-tail append boundary and `rank` path compatibility edge cases.
- [x] 2026-02-28 05:36:00Z Sprint 1 handoff notes added after implementation.
- [ ] 2026-02-28 00:00:00Z Sprint 2 handoff notes added after implementation.
- [ ] 2026-02-28 00:00:00Z Sprint 3 handoff notes and final retrospective added.


## Artifacts and Handoff


Primary artifact is this plan document at `docs/20260228_ranking_mode_execution_plan.md`.

Implementation handoff notes for the next operator are:
1. Execute sprints in order and do not start frontend interaction work before Sprint 1 contracts are stable.
2. Keep ranking feature code inside dedicated ranking namespaces and only touch shared modules at composition boundaries.
3. Record acceptance evidence per sprint directly in this file, including command outcomes and scope decisions.

Initial operator command transcript template is:

    git status --short
    pytest -q
    lenslet rank <dataset.json> --port 7071

Revision note: updated after mandatory subagent review to tighten API contracts, de-scope speculative work, add explicit browse regression gates, correct frontend validation commands, and add results-path safety plus autosave race-closure requirements.

Sprint 1 handoff notes (2026-02-28):
1. Shipped backend-only ranking mode foundations:
   - New package `src/lenslet/ranking/` with dataset loading/validation, save payload validation + progress derivation, append-only JSONL persistence with file lock, and `/rank/*` route bundle.
   - New app factory `create_ranking_app(...)` with ranking-mode health payload (`mode: "ranking"`).
   - CLI dispatch now supports `lenslet rank <dataset.json> [--host --port --reload --results-path]` while keeping existing browse invocation behavior and compatibility for local directories named `rank`.
2. Validation executed:
   - `pytest tests/test_ranking_*.py -q`
   - `pytest tests/test_import_contract.py -q`
   - `python scripts/lint_repo.py`
3. Remaining open scope:
   - Sprint 2 frontend ranking mode implementation (`T5-T7`).
   - Manual CLI smoke with a checked-in ranking fixture (fixture creation is currently pending).
