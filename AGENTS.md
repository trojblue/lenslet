# Repository Guidelines

For each proposed change, examine the existing system and redesign it into the most elegant solution that would have emerged if the change had been a foundational assumption from the start.

## Project Structure & Module Organization
- `src/lenslet/` is the shipping Python package. Key entrypoints: `cli.py` (CLI) and `server.py` (FastAPI app).
- `src/lenslet/storage/` holds storage backends: `local.py` (read-only filesystem) and `memory.py` (RAM cache).
- `frontend/` contains the React source; build output is copied into `src/lenslet/frontend/` for serving.
- `tests/` hosts pytest suites (`test_*.py`).
- `docs/` and `notebooks/` are for lightweight design notes and experiments.
- `dist/` is build output (safe to delete locally).

## Documentation Scope
- `docs/` contains active design/execution docs.
- `docs/agents_archive/` is historical context only; do not treat it as current source-of-truth unless explicitly asked.
- For routine text searches, prefer excluding `docs/agents_archive/` to reduce noise.
- New Ralph loop workspaces should default to `docs/ralph/<YYYYMMDD_slug>/` unless overridden.

## Build, Test, and Development Commands
- `pip install -e . && pip install -e ".[dev]"` — editable install with dev tools.
- `lenslet /path/to/images --reload --port 7070` — run the gallery with auto-reload.
- `python -m lenslet.cli /path/to/images --reload` — module form (handy for debuggers).
- `cd frontend && npm install && npm run dev` — run the UI dev server (proxies to `:7070`).
- `cd frontend && npm run build && cp -r dist/* ../src/lenslet/frontend/` — build UI bundle.
- `python scripts/lint_repo.py` — run post-change lint checks (`ruff` + file-size guardrails: warn >1200 lines, fail >2000 lines).
- `python -m playwright install chromium` — one-time browser install for real browser validation.
- `python scripts/gui_smoke_acceptance.py` — run Playwright-based end-to-end acceptance checks against a live Lenslet server.
- `python scripts/playwright_large_tree_smoke.py --dataset-dir data/fixtures/large_tree_40k --output-json data/fixtures/large_tree_40k_smoke_result.json` — optional large-tree performance probe (40k images across 10k folders).
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
- For frontend/browse behavior changes, run `python scripts/gui_smoke_acceptance.py`.
- For large-tree performance or hydration regressions, run `python scripts/playwright_large_tree_smoke.py --dataset-dir data/fixtures/large_tree_40k`.

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