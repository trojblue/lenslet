# Repository Guidelines

## Project Structure & Module Organization
- `src/lenslet/` — shipping package. `cli.py` exposes the `lenslet` entrypoint; `server.py` hosts the FastAPI app; `storage/` contains `local.py` (read-only FS) and `memory.py` (RAM cache); `frontend/` holds the bundled static UI served by the backend.
- `frontend/` — React source code for UI development. Run `npm run dev` here. After changes, build and copy to `src/lenslet/frontend/`.
- `docs/` and `notebooks/` — design notes and exploratory work; keep notebooks lightweight and checked in without large binaries.
- `dist/` — build artifacts; safe to delete locally. Avoid editing generated files directly.

## Build, Test, and Development Commands
- Install for hacking: `pip install -e .` then `pip install -e ".[dev]"`.
- Run the gallery (auto-reload): `lenslet /path/to/images --reload --port 7070`.
- Module form (useful for debuggers): `python -m lenslet.cli /path/to/images --reload`.
- Build distribution: `python -m build` → wheels in `dist/`.
- Frontend dev: `cd frontend && npm install && npm run dev` (proxies to backend at :7070).
- Frontend build: `cd frontend && npm run build && cp -r dist/* ../src/lenslet/frontend/`.
- Lint/format: standard PEP8; if you use `ruff` or `black`, keep outputs minimal and avoid repo-wide rewrites unless requested.

## Coding Style & Naming Conventions
- Python 3.10+; 4-space indentation; type hints everywhere; prefer small, composable functions (<50 lines) per DEVELOPMENT.md.
- Follow "minimal, fast, boring" rules: explicit over implicit, no global state, avoid clever wrappers.
- Names: modules and files `snake_case`; classes `CamelCase`; functions/vars `snake_case`; CLI flags align with existing options (`--port`, `--host`, etc.).

## Testing Guidelines
- Framework: `pytest` (installed via `.[dev]`). Place tests under `tests/` with `test_*.py` naming.
- For API tests, use `httpx.AsyncClient` against the FastAPI app; prefer in-memory paths and temporary image fixtures.
- Add regression tests for bug fixes; keep runtime short (<30s). Run `pytest` before pushing.

## Commit & Pull Request Guidelines
- Use Conventional Commit prefixes (`feat:`, `fix:`, `chore:`, `refactor:`) as seen in history; keep subject lines imperative.
- PRs stay focused and ideally under ~400 changed lines. Include: summary of behavior change, linked issue (if any), reproduction steps, and screenshots/GIFs for UI-impacting changes.
- If touching the UI bundle, note whether static assets in `src/lenslet/frontend/` were regenerated and how.

## Security & Configuration Tips
- Lenslet never writes into the served image directory; keep it read-only and avoid pointing at sensitive paths.
- Do not commit real user data or large media; use small placeholder images for tests and docs.
- Validate new flags/ports don't conflict with defaults (`127.0.0.1:7070`) and document any changes in `README.md`.
