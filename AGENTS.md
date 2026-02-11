# Repository Guidelines

For each proposed change, examine the existing system and redesign it into the most elegant solution that would have emerged if the change had been a foundational assumption from the start.

## Project Structure & Module Organization
- `src/lenslet/` is the shipping Python package. Key entrypoints: `cli.py` (CLI) and `server.py` (FastAPI app).
- `src/lenslet/storage/` holds storage backends: `local.py` (read-only filesystem) and `memory.py` (RAM cache).
- `frontend/` contains the React source; build output is copied into `src/lenslet/frontend/` for serving.
- `tests/` hosts pytest suites (`test_*.py`).
- `docs/` and `notebooks/` are for lightweight design notes and experiments.
- `dist/` is build output (safe to delete locally).

## Build, Test, and Development Commands
- `pip install -e . && pip install -e ".[dev]"` — editable install with dev tools.
- `lenslet /path/to/images --reload --port 7070` — run the gallery with auto-reload.
- `python -m lenslet.cli /path/to/images --reload` — module form (handy for debuggers).
- `cd frontend && npm install && npm run dev` — run the UI dev server (proxies to `:7070`).
- `cd frontend && npm run build && cp -r dist/* ../src/lenslet/frontend/` — build UI bundle.
- `python -m build` — build wheels into `dist/`.
- `pytest` — run tests.

## Coding Style & Naming Conventions
- Python 3.10+, 4-space indentation, type hints everywhere.
- Prefer small, composable functions (<50 lines) and explicit, “minimal/fast/boring” implementations.
- Naming: `snake_case` for modules/functions/vars, `CamelCase` for classes.
- CLI flags should align with existing patterns (`--port`, `--host`, etc.).
- If using `ruff` or `black`, avoid repo-wide rewrites unless requested.

## Testing Guidelines
- Framework: `pytest`. Name tests `tests/test_*.py`.
- For API tests, use `httpx.AsyncClient` against the FastAPI app.
- Use small, temporary image fixtures; keep runtime under 30s.

## Commit & Pull Request Guidelines
- Commit messages: Conventional Commits (`feat:`, `fix:`, `chore:`, `refactor:`), imperative mood.
- PRs should include a concise summary, linked issue (if any), reproduction steps, and UI screenshots/GIFs when applicable.
- If you touch UI assets, note whether `src/lenslet/frontend/` was regenerated and how.

## Security & Configuration Tips
- The server must never write into the served image directory; keep it read-only.
- Avoid sensitive paths and real user data; use small placeholders in tests/docs.
- Default host/port is `127.0.0.1:7070`; document any changes in `README.md`.
