# Lenslet Session Launch Info Plan


## Outcome + Scope Lock


After implementation, a user with several Lenslet instances open can identify what each viewer was loaded from without checking the terminal. The Settings menu will include a neutral Session section using the agreed wording `Session` and `Loaded from`, and the browser tab title will include a concise dataset/table/folder label.

The user-facing goal is diagnostic provenance, not product promotion. The UI must avoid wording such as `Opened with Lenslet`. The section should read like:

    Session
    Loaded from: Hugging Face dataset
    incantor/aes-composite-x0.2-additional-images
    Remote table · read-only · 37,670 rows

Goals are to show launch provenance for known CLI launch modes: local folders, local parquet files, folder `items.parquet`, Hugging Face datasets, and remote parquet URIs. The implementation should reuse `/health`, keep values backend-redacted and display-ready, show a copyable launch command only when it is safe to disclose and expected to run, and update the browser title for instance identification.

Non-goals are a persistent banner, an About page, command history, telemetry, share-link promotion, exact shell-history reconstruction, support for every programmatic `create_app*` embedding case, or any behavior change to loading, write permissions, source-column switching, refresh, thumbnails, or media policy.

Pre-approved behavior changes are adding a small launch/session payload to `/health`, changing the settings trigger title from `Theme settings` to `Settings`, adding the Session section above Source in the settings menu, adding a `Copy command` action only when `copy_command` exists, and setting a static instance title in the form `Lenslet · <title_label>`. Showing full local absolute paths, raw signed URLs/query strings, a persistent product plug, or any new network call requires user sign-off.

Deferred items are a richer About panel, visual instance badges outside Settings, recent-session history, exact recreation of every non-default CLI option, and combining current folder path into the browser title. The approved title behavior prioritizes instance identity over live folder context.


## Context


There is no `PLANS.md` in this repo. The applicable repository instructions are in `AGENTS.md`: treat Lenslet as pre-release alpha, prefer hard cutovers, keep edits scoped, and run `python scripts/lint_repo.py` before handoff.

Current health payloads already expose table diagnostics through `table_launch_status`, and the frontend already passes that status into `ThemeSettingsMenu`. The settings panel currently has Theme, Source, Inspector, Media, and Compare sections, with Source showing `Launch status` for table-backed launches. This makes Settings the natural placement and avoids a new modal.

Relevant backend files are `src/lenslet/cli/browse.py`, `src/lenslet/web/models.py`, `src/lenslet/web/app/options.py`, `src/lenslet/web/app/local.py`, `src/lenslet/web/app/storage.py`, `src/lenslet/web/app/table.py`, and `src/lenslet/web/app/health.py`. Relevant frontend files are `frontend/src/lib/types.ts`, `frontend/src/app/hooks/useAppHealthPolling.ts`, `frontend/src/shared/ui/ThemeSettingsMenu.tsx`, `frontend/src/shared/ui/Toolbar.tsx`, `frontend/src/shared/ui/toolbar/ToolbarMobileDrawer.tsx`, `frontend/src/styles.css`, and focused tests under `frontend/src/shared/ui/**/__tests__`, `frontend/src/app/**/__tests__`, `tests/cli`, and `tests/web/app`.

The main ambiguity is command fidelity. This plan resolves it by treating the copied command as an optional artifact. `copy_command` must be present only when every argument is safe to disclose and the sanitized command is expected to run. Local absolute paths and signed/credentialed remote URLs should generally produce session metadata without a copy command unless the user explicitly approves disclosure.

Subagent review tightened this plan around security and scope: it requires exact redaction rules, a clearer display-ready payload shape, explicit title behavior, a single implementation sprint, and real tests that ensure raw local paths and URL secrets never reach the session payload or title.


## Interfaces and Dependencies


Add a `LaunchSessionPayload` Pydantic model and optional `launch_session` field on `HealthResponse`. Use a minimal display-ready contract:

    kind: str
    loaded_from_label: str
    target_label: str
    title_label: str
    detail_label: str | None
    copy_command: str | None

All string fields must already be safe for display before they leave the backend. The frontend must not receive raw sensitive values and then redact them itself.

Redaction rules are part of the interface. Hugging Face targets may show the dataset id, for example `incantor/aes-composite-x0.2-additional-images`. Local paths should show a basename or shortened label such as `.../items.parquet` or `.../images`, not a full absolute path. HTTP/HTTPS URLs should remove username, password, query, and fragment. S3 URIs should show bucket/key-style labels only when no credential material is present. If redaction would make a command non-runnable, omit `copy_command`.

Add matching TypeScript types to `frontend/src/lib/types.ts` and carry the value through `useAppHealthPolling`. Do not add a new HTTP endpoint; `/health` is already polled and contains adjacent launch diagnostics.

Carry launch session data through static app options or health payload closures. Prefer the smallest local design that avoids adding mutable context if static options are enough. CLI launches should build this payload from `BrowseTarget` and normalized args. Programmatic app creation should omit `launch_session` unless the caller supplies known-safe provenance; do not invent vague fallback provenance that could reduce trust.


## Plan of Work


Scope budget: one implementation sprint, five substantive tasks, plus one cleanup gate and one review gate after the sprint. Expected write areas are one CLI/session helper path, one app-option/backend health path, one frontend Settings/title path, and focused tests. Avoid new top-level UI concepts, new routes, broad app-shell refactors, or duplicate launch-status renderers.

Quality guardrails: for every substantive code ticket, use the `better-code` skill before and during implementation. State assumptions and ambiguous interpretations before coding, choose the smallest non-speculative change, touch only lines tied to the request or verification, remove only unused code introduced by the change, and attach a concrete verification check. While implementing the sprint, update this plan continuously, especially Progress Log and Artifacts and Handoff. After the sprint, add handoff notes. For minor script-level uncertainties such as exact helper placement, proceed according to this approved plan to maintain momentum, then ask for clarification after the sprint and apply follow-up adjustments.

Delegate subagents early to find real codepaths/files when that reduces context load or speeds execution. If a delegated cleanup or review task starts, let it continue long enough to produce useful results. If it is still in progress after 10 minutes, ask for a progress update and why more time is needed. Before 40 minutes have elapsed from subagent launch, wait instead of substituting manual review, unless the user explicitly approves a downgrade.

Debloat/removal list: rename or retitle the misleading `Theme settings` wording where it is no longer accurate; do not create a separate Settings route, About modal, global state store, or frontend redaction layer; do not add a generic programmatic fallback session payload unless provenance is known.

### Sprint 1: Session Metadata and Settings Surface

Demo outcome: `/health` returns safe `launch_session` metadata for known CLI launch paths, Settings shows the Session section, copy command appears only when safe+runnable, and the browser title identifies the instance without leaking sensitive values.

1. T1.1 Lock redaction and command eligibility rules. Implement a small backend owner for launch-session construction, preferably a narrow helper module rather than helpers spread across constructors. The helper must encode local path, HF, HTTP/HTTPS, S3, and command eligibility rules. Validation: focused backend tests prove local absolute paths are shortened, signed/credentialed URLs lose sensitive material, and unsafe commands are omitted.

2. T1.2 Add the health contract and app plumbing. Add `LaunchSessionPayload` to `src/lenslet/web/models.py`, add the minimal app option or health-closure field needed to expose `launch_session`, and thread it through local, storage, and table app health payloads. Validation: focused health tests assert the field is present for known CLI/app-option cases and omitted when no trusted provenance is supplied.

3. T1.3 Build CLI session metadata. In `src/lenslet/cli/browse.py`, derive `kind`, `loaded_from_label`, `target_label`, `title_label`, `detail_label`, and optional `copy_command` from `BrowseTarget` plus normalized args. Include `--source-column`, `--path-column`, `--base-dir`, and `--trust-remote-paths` in `copy_command` only when the complete command remains safe to disclose and expected to run. Validation: `tests/cli/test_browse_table_launch.py` or a new focused CLI test covers HF shorthand, `hf://`, remote parquet URI, local parquet, local folder, explicit `--path-column`, and unsafe-command omission.

4. T1.4 Add Settings UI and clipboard behavior. Extend TypeScript health types/state, retitle the settings trigger to `Settings`, and add a Session section above Source in `ThemeSettingsMenu`. Render `Loaded from`, target, compact detail, and `Copy command` only when `copy_command` exists. Clipboard failures should use an existing quiet action-feedback pattern if available; otherwise leave the button accessible and avoid throwing. Validation: `frontend/src/shared/ui/__tests__/ThemeSettingsMenu.test.tsx` covers remote HF, redacted local target, missing command, copy command present, and clipboard failure behavior. `frontend/src/shared/ui/toolbar/__tests__/ToolbarMobileDrawer.test.tsx` covers that the same settings menu remains reachable from mobile.

5. T1.5 Set the browser title safely. Use `launch_session.title_label` to set a static instance title `Lenslet · <title_label>`, falling back to `Lenslet`. Do not parse target labels in the frontend. Validation: a focused app or boot test proves title updates when session metadata is present, falls back when missing, and never receives raw local paths or signed URL query material.

For each task, use this gate routine. First, the code agent briefly restates the goal, acceptance criteria, material assumptions/ambiguities, and files to touch. If an ambiguity would change behavior, stop and ask. If the ticket includes substantive code work, invoke `better-code` to restate the key invariants, smallest robust approach, and verification evidence. Then implement the smallest coherent slice, avoiding speculative features, one-off abstractions, unrelated cleanup, and broad refactors. Finally, run the task’s concrete verification before marking it complete.

### code-simplifier routine

After Sprint 1 is complete, spawn a subagent and instruct it to use the `code-simplifier` skill to scan current sprint changes. Start with non-semantic cleanup first: formatting/lint autofixes, obvious dead code removal, small readability edits that do not change behavior, and docs/comments that reflect what is already true. Keep this conservative; do not expand into semantic refactors unless explicitly approved. Once the cleanup subagent starts, do not interrupt or repurpose it just to save time. If it is still running after 10 minutes, ask for a brief progress update, then keep waiting. Only fall back to manual cleanup review after 40 minutes with no usable response, or when the user explicitly approves the downgrade. If the cleanup subagent is unavailable or fails to launch, stop and ask the user for an alternative cleanup/review path.

### review routine

After Sprint 1 is complete and the cleanup subagent finishes, spawn a fresh agent and request a code review using the `code-review` skill. Instruct the review subagent to be constructively adversarial: actively look for ways the change could fail, where scope or validation is weak, and what should be removed or simplified, while keeping feedback actionable and focused on shipping a robust result. Use the best available model in the environment with `reasoning_effort` set to `medium`; do not default to mini/fast models unless the user explicitly approves. Review the post-cleanup diff, apply fixes, then rerun review when needed. Once the review subagent starts, do not interrupt, repurpose, or terminate it to save time. If it is still running after 10 minutes, ask for a brief progress update, then keep waiting. Before 40 minutes have elapsed from launch, do not continue with manual/self-review, do not make fixes from guessed findings, and do not mark the gate complete unless the user explicitly approves a downgrade. Manual diff review is a fallback only after 40 minutes with no usable response, or when the user explicitly approves that downgrade. If the review subagent is unavailable or fails to launch, stop and ask the user for an alternative review path.


## Validation and Acceptance


Primary acceptance is a real remote-HF-style launch path close to the user scenario. Run a live Lenslet server against a small or existing HF/remote-table fixture, open the browser, and confirm Settings shows `Session`, `Loaded from: Hugging Face dataset`, the dataset id, read-only/table row context, and a working `Copy command` only when safe. Confirm the browser title includes the dataset id. If network access to the original dataset is not appropriate for automated tests, use a monkeypatched remote table loader that exercises the same remote target codepath and document that limitation.

Primary security acceptance is that `/health.launch_session` and `document.title` do not include raw local absolute paths, URL usernames/passwords, query strings, fragments, or token-like signed URL material. A signed URL fixture must not emit `?`, username/password, or query material anywhere in `launch_session`.

Secondary backend gates are:

1. Run focused CLI and health tests:

       pytest -q tests/cli/test_browse_table_launch.py tests/cli/test_direct_cli_helpers.py tests/web/app/test_indexing_health_contract.py

2. Run any new focused launch-session health tests added during implementation, for example:

       pytest -q tests/web/app/test_launch_session_health.py

3. Confirm `--path-column`, `--source-column`, `--base-dir`, and `--trust-remote-paths` are represented in `copy_command` only when safe and expected to run.

Secondary frontend gates are:

1. Run focused settings and mobile drawer tests:

       cd frontend && npm test -- ThemeSettingsMenu ToolbarMobileDrawer

2. Run the focused app/title test added during implementation.

3. Run the frontend build when frontend assets are changed:

       cd frontend && npm run build

   Regenerate `src/lenslet/frontend/` only as a final packaging step if repo convention for this change requires committed packaged assets, and note that decision in handoff.

Final gates are:

1. Run repository lint:

       python scripts/lint_repo.py

2. Run browser acceptance when a live server and browser dependencies are available:

       python -m scripts.browser.gui_smoke.acceptance

   If it is not run, record exactly why and what command/scenario would satisfy it.

Completion requires the Settings section and browser title to work in the primary remote-HF-style scenario, not just unit fixtures.


## Risks and Recovery


The main security risk is leaking sensitive local paths or signed URL details through `/health`, clipboard text, or the browser title. Recovery is to redact more aggressively, omit `copy_command` for unsafe cases, and keep full raw values out of the payload.

The main UX risk is making Settings too dense. Recovery is to show only four Session elements: `Loaded from`, target, compact detail, and `Copy command` if available. Keep detailed row/dimension/media diagnostics in the existing Source section.

The main implementation risk is spreading launch metadata through too many constructors. Recovery is to keep metadata static and optional, passed through app options or health closures only; do not add global state or a new route.

The title behavior intentionally prioritizes instance identity over current folder context. If that proves confusing, recovery is to combine labels later, for example `Lenslet · <session> · <folder>`, but that is deferred unless the user asks.

Rollback is safe: remove the optional `launch_session` field and frontend Session rendering. Existing table launch status, media behavior, and source-column switching should remain unchanged. Retrying implementation is idempotent because the feature is additive and read-only.


## Progress Log


- [x] 2026-06-11: Scope wording agreed: use `Session` and `Loaded from`; avoid `Opened with Lenslet` and persistent product-plug language.
- [x] 2026-06-11: Codepath discovery found existing `/health.table_launch_status` and `ThemeSettingsMenu` Source/Launch status as the natural integration points.
- [x] 2026-06-11: Required plan review completed with subagent feedback. Incorporated security-sensitive `copy_command`, display-ready payload fields, explicit title behavior, precise redaction rules, and a one-sprint scope.
- [x] 2026-06-11: Sprint 1 started.
- [x] 2026-06-11: Implemented backend `launch_session` health payload, CLI launch-session construction, Settings Session UI, copy command action, and static document title from `title_label`.
- [x] 2026-06-11: Packaged frontend assets under `src/lenslet/frontend/` regenerated from `frontend/dist/`.
- [x] 2026-06-11: Cleanup gate completed. It added a narrow type annotation and caught a competing path-based title effect; the effect was removed so session title remains static.
- [x] 2026-06-11: Review gate completed. It found HF URI query/fragment leakage in labels; the redaction helper now parses only netloc/path and a regression test covers tokenized HF URIs.
- [x] 2026-06-11: Final validation completed with focused pytest, full frontend Vitest, frontend build, packaged-asset sync, `git diff --check`, `python scripts/lint_repo.py`, and `python -m scripts.browser.gui_smoke.acceptance`.


## Artifacts and Handoff


Target plan path: `docs/20260611_session_launch_info_plan.md`.

Suggested Settings copy:

    Session
    Loaded from: Hugging Face dataset
    incantor/aes-composite-x0.2-additional-images
    Remote table · read-only · 37,670 rows
    Copy command

Suggested local parquet copy when the command is unsafe to disclose:

    Session
    Loaded from: Local Parquet
    .../items.parquet
    Table · writable sidecar · 37,670 rows

Suggested title behavior:

    Lenslet · incantor/aes-composite-x0.2-additional-images
    Lenslet · items.parquet
    Lenslet

Subagent review changes incorporated: optional safe+runnable `copy_command`; backend-redacted display-ready payload fields; explicit redaction rules; title label supplied by backend; one cleanup/review gate after the feature sprint; actual test paths plus new focused tests where needed.

Handoff note for implementers: preserve the existing table diagnostics in Source. Session is provenance and instance identification only. Keep the payload safe enough to show to a shared browser client by default.

Implementation handoff, 2026-06-11: The shipped app now exposes optional `launch_session` metadata through `/health`, supplied by known CLI launch paths and omitted for unknown programmatic provenance unless explicitly passed through app options. The Settings menu shows a compact Session block above Source when the payload is present; `Copy command` appears only when the backend includes a safe runnable command. The browser title is static per instance via `Lenslet · <title_label>` and no longer includes live folder context.

Validation evidence recorded during implementation: `pytest -q tests/cli/test_browse_table_launch.py tests/web/app/test_launch_session_health.py tests/web/app/test_indexing_health_contract.py` passed; `pytest -q tests/cli/test_direct_cli_helpers.py tests/cli/test_ranking_cli.py tests/web/routes/test_table_source_settings.py tests/api/test_import_contract.py tests/api/test_programmatic_api.py` passed; `pytest -q tests/cli/test_browse_table_launch.py tests/cli/test_direct_cli_helpers.py tests/cli/test_ranking_cli.py tests/web/app/test_launch_session_health.py tests/web/app/test_indexing_health_contract.py tests/web/routes/test_table_source_settings.py` passed; `cd frontend && npm test -- ThemeSettingsMenu ToolbarMobileDrawer launchSessionTitle` passed; `cd frontend && npm test -- --run` passed; `cd frontend && npm run build` passed; `rsync -a --delete frontend/dist/ src/lenslet/frontend/` regenerated packaged assets; `git diff --check` passed; `python scripts/lint_repo.py` passed; `python -m scripts.browser.gui_smoke.acceptance` passed with the existing non-strict folder re-entry anchor warning. After review fixes, `pytest -q tests/web/app/test_launch_session_health.py tests/cli/test_browse_table_launch.py`, `cd frontend && npm test -- ThemeSettingsMenu ToolbarMobileDrawer launchSessionTitle`, `cd frontend && npm run build`, `python scripts/lint_repo.py`, and `git diff --check` passed again.
