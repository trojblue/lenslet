# S0 T2a Server Module Structure Gate

Timestamp (UTC): `2026-02-11T04:22:50Z`  
Branch: `main`  
Plan ticket: `T2a`

## Objective

Lock one unambiguous extraction shape for `lenslet.server` before S1 code movement.

## Architecture Decision

- Keep `src/lenslet/server.py` as the only module at import path `lenslet.server`.
- Extract internals only into sibling modules under `src/lenslet/`:
  - `server_runtime.py`
  - `server_routes_common.py`
  - `server_routes_presence.py`
  - `server_routes_embeddings.py`
  - `server_routes_views.py`
  - `server_routes_index.py`
  - `server_routes_og.py`
  - `server_media.py`
- Do not create a `src/lenslet/server/` package directory.
- Do not create a mixed `server.py` plus `server/` hybrid layout.

## Compatibility Guardrails

- `import lenslet.server as server` must continue resolving to module path `lenslet.server`.
- `lenslet.server` must continue exposing:
  - `create_app`, `create_app_from_datasets`, `create_app_from_table`, `create_app_from_storage`
  - `HotpathTelemetry`, `_file_response`, `_thumb_response_async`, and `og`
- Tests that monkeypatch `lenslet.server.og.*` are part of the compatibility surface and must stay valid.

## Approved S1 Extraction Boundary

1. `server.py` becomes a facade/composer and stable export surface.
2. Route logic moves into domain registration helpers (`register_*_routes` functions).
3. Runtime wiring moves into `server_runtime.py`.
4. Media helper stack moves into `server_media.py`.
5. No route contract or payload semantic changes are allowed in extraction-only tickets (`T3`-`T5`).

## Validation

Command:

```bash
python - <<'PY'
import lenslet.server as server
assert server.__name__ == "lenslet.server"
assert hasattr(server, "og")
print("server-module-import-ok")
PY
```

Result:

- `server-module-import-ok`
