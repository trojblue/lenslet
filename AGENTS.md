# Repository Guidelines

For each proposed change, examine the existing system and redesign it into the most elegant solution that would have emerged if the change had been a foundational assumption from the start.

## Project Structure & Module Organization
- `src/lenslet/` is the shipping Python package. `server.py` is the public FastAPI facade; runtime/routes live under `web/`, CLI entrypoints under `cli/`, and storage backends under `storage/`.
- `frontend/` contains the React + Vite source. App composition lives under `frontend/src/app/`, reusable UI under `shared/`, and domain code under `features/`.
- `src/lenslet/frontend/` is the generated packaged UI. Mirror `frontend/dist/` into it with `rsync --delete`; do not hand-edit generated assets.
- `scripts/browser/` contains the live Playwright acceptance, continuity, and performance probes.
- `tests/` hosts pytest suites (`test_*.py`).
- `docs/` contains the canonical design contract plus active investigations and execution plans. `notebooks/` is for experiments.
- `dist/` is build output (safe to delete locally).

## Documentation Scope
- `DEVELOPMENT.md` is the current setup, architecture, build, and release guide. Prefer linking to it over duplicating volatile details here.
- `docs/DESIGN_SYSTEM.md` is the canonical frontend presentation-continuity contract. Read it before changing asynchronous UI, loading/empty/error states, tabs, persisted layout, or media presentation.
- `docs/` contains active design/execution docs.
- Dated observations and execution plans are evidence and decision records, not evergreen behavior contracts. When they conflict with `docs/DESIGN_SYSTEM.md`, update the plan or the design contract explicitly rather than silently choosing one.
- `docs/agents_archive/` is historical context only; do not treat it as current source-of-truth unless explicitly asked.
- For routine text searches, prefer excluding `docs/agents_archive/` to reduce noise.
- New Ralph loop workspaces should default to `docs/ralph/<YYYYMMDD_slug>/` unless overridden.

## Build, Test, and Development Commands
- `python scripts/setup_dev.py` — install the validated Python/frontend/browser development stack for a fresh checkout.
- `python -m pip install -c constraints/runtime-py313.txt -e ".[dev]"` — update the editable Python install with validated runtime constraints.
- `lenslet /path/to/images --reload --port 7070` — run the gallery with auto-reload.
- `python -m lenslet.cli /path/to/images --reload` — module form (handy for debuggers).
- `cd frontend && npm ci && npm run dev` — install the locked frontend dependencies and run the UI dev server (proxies to `:7070`).
- `npm --prefix frontend test -- --run` — run the frontend Vitest suite.
- `cd frontend && npx tsc --noEmit` — type-check the frontend.
- `npm --prefix frontend run build` followed by `rsync -a --delete frontend/dist/ src/lenslet/frontend/` — build and deterministically mirror the served UI bundle.
- `python scripts/lint_repo.py` — run post-change lint checks (`ruff` + file-size guardrails: warn >1200 lines, fail >2000 lines).
- `python -m playwright install chromium` — one-time browser install for real browser validation.
- `python -m scripts.browser.gui_smoke.acceptance` — run Playwright-based end-to-end acceptance checks against a live Lenslet server.
- `python -m scripts.browser.gui_jitter.probe --scenario <toolbar|grid|inspector|metrics> --output-json /tmp/<name>.json` — capture painted-frame continuity for the affected frontend surface.
- `python -m scripts.browser.large_tree.smoke --dataset-dir data/fixtures/large_tree_40k --output-json data/fixtures/large_tree_40k_smoke_result.json` — optional large-tree performance probe (40k images across 10k folders).
- `python -m build` — build wheels into `dist/`.
- `pytest` — run tests.

## Coding Style & Naming Conventions
- Python 3.10+, 4-space indentation, type hints everywhere.
- Prefer small, composable functions (<50 lines) and explicit, “minimal/fast/boring” implementations.
- Prefer boring/stable dependencies; avoid introducing new libraries unless the payoff is clear and documented.
- Naming: `snake_case` for modules/functions/vars, `CamelCase` for classes.
- CLI flags should align with existing patterns (`--port`, `--host`, etc.).
- If using `ruff` or `black`, avoid repo-wide rewrites unless requested.

## Testing Guidelines
- Framework: `pytest`. Name tests `tests/test_*.py`.
- For API tests, use `httpx.AsyncClient` against the FastAPI app.
- Prefer real-environment validation (live server + Playwright/user flows) over adding many tiny, isolated tests for one change.
- Keep smoke checks lean and scenario-driven; avoid bloated smoke-only suites that duplicate low-level unit coverage.
- Use small, temporary image fixtures for focused unit/integration tests; keep runtime under 30s where practical.
- After feature completion, run `python scripts/lint_repo.py` before handoff.
- For frontend changes, run focused Vitest plus TypeScript; run the full frontend suite when shared state, query ownership, or common UI primitives change.
- For frontend/browse behavior changes, run `python -m scripts.browser.gui_smoke.acceptance` after rebuilding and mirroring packaged assets.
- For asynchronous presentation, layout, tab, persisted-state, loading/empty/error, or media changes, run the relevant `gui_jitter` scenario. A stable outer rectangle is not sufficient: assertions must cover affected descendant values/actions/rows and decoded image identity or pixels. Cold unvisited targets and the earliest post-action painted frame are mandatory.
- For large-tree performance or hydration regressions, run `python -m scripts.browser.large_tree.smoke --dataset-dir data/fixtures/large_tree_40k`.

## Frontend Presentation Rules
- Treat requested identity and presented identity separately. During a compatible async transition, retain one complete settled presentation and atomically promote the next; never show new labels with old, blank, loading, or undecoded content.
- Timing thresholds delay status copy only. They do not justify clearing values, hiding buttons, inserting skeletons, dimming retained media, or showing false empty/zero states.
- State required for the first visible frame must be derived or initialized before paint. Do not use passive effects to restore visible persisted state, discover active query fields, or notify a parent of data required to render the current tab.
- Tab, disclosure, and responsive visibility changes must preserve drafts, selection, expansion, scroll, query registration, and last-settled presentation unless they cross an explicit hard-reset boundary.
- Decode navigable media before promotion. Keep labels, pixels, opacity, and transforms bound to one presented identity, with bounded resource lifetime and latest-target guards.
- Use `docs/DESIGN_SYSTEM.md` for the full contract and exception boundaries. If a requested behavior changes that contract, update the document and the focused painted-frame gate in the same change.

## Commit & Pull Request Guidelines
- Commit messages: Conventional Commits (`feat:`, `fix:`, `chore:`, `refactor:`), imperative mood.
- PRs should include a concise summary, linked issue (if any), reproduction steps, and UI screenshots/GIFs when applicable.
- If you touch UI assets, note whether `src/lenslet/frontend/` was regenerated and how.

## Security & Configuration Tips
- Source datasets stay read-only (no writes into image directories or S3 sources), but Lenslet may write workspace state/caches under `.lenslet/`, `<table>.lenslet.json`, `<table>.cache/`, or `/tmp/lenslet` when using `--no-write`.
- Avoid sensitive paths and real user data; use small placeholders in tests/docs.
- Default host/port is `127.0.0.1:7070`; document any changes in `README.md`.

## Additional Notes
- You are working on a pre-release alpha version, which means no backwards compatibility for existing users is required.
- This project is under active development. Use a hard cutover approach and never implement backward compatibility.
