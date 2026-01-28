# Embedding Similarity Lookup Plan


## Purpose / Big Picture


This plan adds embedding-based similarity search to Lenslet without inflating baseline memory usage or item payloads. Users will be able to choose an embedding column (or rely on auto-detection), run "Find similar" from a selected image, or paste a base64-packed float32 query vector, and get a ranked result set with top K and min score controls. The gallery remains CPU-only by default, with optional FAISS acceleration, and embeddings are loaded on demand into a float32 matrix rather than Python lists. The end state is visible when a dataset with a fixed-size list embedding column can be queried from the UI and the API, returning ordered results without crashing due to memory pressure.


## Progress


- [x] 2026-01-28: Captured requirements and constraints (auto-detect columns, CLI override, vector input, top K/min score, cosine default, CPU-only, optional FAISS, cache allowed).
- [ ] 2026-01-28: Implement backend embedding detection, loading, search endpoints, and tests.
- [ ] 2026-01-28: Implement frontend similarity UI (selected image + vector input).
- [ ] 2026-01-28: Add caching, optional FAISS, and documentation.


## Surprises & Discoveries


The table dataset path loads all Parquet columns into Python lists via `pyarrow.Table.to_pydict()` in `src/lenslet/storage/table.py`, which would pull embedding vectors into memory and risk OOM. This means embedding columns must be excluded from the base table load and handled by a dedicated loader.


## Decision Log


2026-01-28 (assistant): Use auto-detection of fixed-size list columns as a fallback, with explicit CLI `--embedding-column` overrides to decide which embedding sets are available.

2026-01-28 (assistant): Treat cosine similarity as the default metric; allow per-column overrides via CLI configuration.

2026-01-28 (assistant): Keep embeddings out of item payloads and UI metrics; similarity results are returned as a ranked list with scores and kept in a dedicated similarity mode.

2026-01-28 (assistant): Support query vectors via base64-packed float32 input and selected-image lookup, with minimal validation (base64 decode, length check, finite values).

2026-01-28 (assistant): Keep CPU-only behavior as the baseline, with optional FAISS acceleration behind an optional dependency.

2026-01-28 (assistant): Load embeddings from the same Parquet table by row index, but return both `row_index` and `path` in similarity results to disambiguate duplicates and simplify UI mapping.

2026-01-28 (assistant): Similarity mode preserves the ranking returned by the backend; filters may remove items but must not reorder results, and sort controls are disabled while similarity mode is active.

2026-01-28 (assistant): Cache embeddings under the workspace cache path by default, with an override flag for an external cache directory and respect for `--no-write`.


## Outcomes & Retrospective


No implementation has been completed yet. When the plan is executed, the outcome should be a working embedding similarity workflow in both API and UI, plus documentation and tests; any gaps and lessons learned will be recorded here.


## Context and Orientation


Lenslet has two Parquet-backed modes: `src/lenslet/storage/table.py` for arbitrary tables (used when `items.parquet` exists) and `src/lenslet/storage/parquet.py` for the legacy `items.parquet` plus `metrics.parquet` pattern. The table mode is the one that will host embeddings for this plan. The app is created in `src/lenslet/server.py` and CLI parsing is in `src/lenslet/cli.py`. The frontend state, including search and sorting, lives in `frontend/src/app/AppShell.tsx`, with toolbar controls in `frontend/src/shared/ui/Toolbar.tsx`, and item types in `frontend/src/lib/types.ts`.

The plan avoids loading embedding columns in `TableStorage` and instead reads them separately via PyArrow and NumPy, using the dataset's `items.parquet` and the resolved path column for row mapping. Similarity results are a dedicated UI mode rather than being mixed into existing metrics. No PLANS.md was found during repository scan.


## Plan of Work


First, introduce embedding configuration and Parquet schema detection so the server knows which embedding columns exist and which ones to ignore in the base table load, including a rejected list with reasons. Then, add a dedicated embedding index loader that reads only the embedding column plus a join key, converts to float32, normalizes vectors for cosine search, and exposes a search API. Next, wire backend routes for listing embeddings and performing similarity search by path or vector with strict input validation and clear error responses. After that, integrate the frontend: add a "Find similar" action in the Inspector, a modal for selecting embeddings and pasting vectors, and a similarity results mode that preserves ranking. Finally, add cache and preload support, optional FAISS acceleration, update documentation, and add tests for invalid inputs and cache behavior.

### Sprint Plan


1. Sprint 1 - Backend detection and NumPy search. Goal: the server can list embeddings and return top K similarity results without loading embedding columns into `TableStorage`. Demo outcome: start the server and call `GET /embeddings` and `POST /embeddings/search` with either a path or base64 vector; results are ordered by similarity and include row indices. Tasks: T1, T2, T3a, T4, T5.

2. Sprint 2 - Frontend similarity workflow. Goal: users can trigger "Find similar" from the Inspector, choose an embedding set, paste a vector, and see similarity results with a clear way to exit the mode. Demo outcome: UI button opens a modal, performs a search, and the grid updates to similarity results with sorting disabled. Tasks: T6, T7a, T7b.

3. Sprint 3 - Cache, optional FAISS, and docs. Goal: embeddings can be cached, optionally preloaded, and optionally accelerated by FAISS; documentation explains usage and dependencies. Demo outcome: first request builds cache files under the workspace cache or an override directory, subsequent runs reuse the cache when allowed, and README shows CLI usage and vector format. Tasks: T8a, T8b, T9.


## Concrete Steps


Run commands from the repository root unless otherwise stated.

    cd /home/ubuntu/dev/lenslet
    pytest -q

### Task/Ticket Details


1. T1 - Embedding config and detection rules. Goal: define configuration for embedding columns, metrics, and auto-detection, and capture rejected columns with reasons. Affected files: new `src/lenslet/embeddings/config.py` and `src/lenslet/embeddings/detect.py`, plus CLI/server wiring in `src/lenslet/cli.py` and `src/lenslet/server.py`. Validation: start the server on a dataset with one fixed-size list column and one variable-length list column; `GET /embeddings` lists the fixed-size column and includes the variable-length column in a rejected list with a reason.

2. T2 - Exclude embedding columns from `TableStorage` loads. Goal: modify table loading to read only non-embedding columns into `TableStorage` so embeddings are not stored as Python lists. Affected files: `src/lenslet/storage/table.py`, `src/lenslet/cli.py`, `src/lenslet/server.py`. Validation: a unit test asserts that `TableStorage._columns` excludes embedding columns, and a manual run on a dataset with embeddings does not spike memory or crash.

3. T3a - Embedding index loader and NumPy search core. Goal: implement an `EmbeddingIndex` that loads a fixed-size list embedding column plus a join key (row index and resolved `path`), casts to float32, normalizes for cosine, and supports search by vector and by path. Include strict base64 decoding, length checks, and finite-value checks. Handle fp16 and bf16 by casting to float32 and rejecting unsupported types with explicit errors. Affected files: new `src/lenslet/embeddings/index.py` and `src/lenslet/embeddings/io.py`. Validation: a unit test builds a tiny Parquet table with a fixed-size list embedding column and asserts cosine search returns the expected nearest neighbor; tests verify invalid base64 and dimension mismatch errors.

4. T4 - Backend endpoints for embeddings. Goal: add `GET /embeddings` to list available embedding columns and `POST /embeddings/search` to run similarity queries by `query_path` or `query_vector_b64`, with `top_k` and `min_score`. The response includes `row_index`, `path`, and `score` per item. Affected files: `src/lenslet/server.py`, plus new response models in `src/lenslet/api_models.py` (or equivalent). Validation: API tests with `httpx.AsyncClient` show that both query modes return ordered results and that missing paths or dimension mismatches return clear 4xx errors.

5. T5 - Backend tests for detection and search. Goal: cover auto-detection rules, CLI overrides, rejected columns, vector decoding errors, duplicate paths, and invalid vectors (NaNs, zero vector). Affected files: `tests/test_embeddings_search.py` (new), `tests/test_parquet_ingestion.py` (extended). Validation: `pytest -k embeddings` passes under 30s.

6. T6 - Frontend API and types. Goal: add client calls and typed responses for embeddings list and search, including a similarity result type with `path`, `row_index`, and `score`. Affected files: `frontend/src/api/client.ts`, `frontend/src/api/embeddings.ts` (new), `frontend/src/shared/api/embeddings.ts` (new), `frontend/src/lib/types.ts`. Validation: TypeScript build succeeds and API functions return parsed results in a local dev run.

7. T7a - Similarity modal UI. Goal: add a "Find similar" action in the Inspector and a modal supporting embedding selection, base64 vector input, and "use selected image". Disable or hide the action when no embeddings are available. Affected files: `frontend/src/features/inspector/Inspector.tsx` and new UI under `frontend/src/features/embeddings/`. Validation: run the app, select an image, open the modal, and see embedding choices; when no embeddings exist, the action is disabled with an explanation.

8. T7b - Similarity mode in AppShell. Goal: add a similarity results mode that replaces the grid items with similarity results, preserves backend order, applies filters without reordering, and disables sort controls. Provide a clear exit back to normal browsing. Affected files: `frontend/src/app/AppShell.tsx`, `frontend/src/shared/ui/Toolbar.tsx`. Validation: run the app, perform similarity search, observe results ordered by score, and exit back to the original folder view.

9. T8a - Cache format and invalidation. Goal: define a cache format (for example `.npz`) keyed by dataset path, embedding column name, dtype, dimension, and Parquet file mtime/size. Store under the workspace cache path by default and support `--embedding-cache-dir` override. Respect `--no-write` by disabling cache writes. Affected files: `src/lenslet/workspace.py`, `src/lenslet/embeddings/cache.py`, `src/lenslet/cli.py`, `src/lenslet/server.py`. Validation: first run writes cache files when allowed; changes to the Parquet file invalidate the cache; `--no-write` prevents cache creation.

10. T8b - Preload behavior. Goal: add a preload option that builds the embedding index at startup and reports any failures without preventing the server from starting. Affected files: `src/lenslet/server.py`, `src/lenslet/embeddings/index.py`. Validation: start server with `--embedding-preload` and confirm logs indicate successful build; with missing embeddings, server starts and reports the error.

11. T9 - Optional dependencies and documentation. Goal: add an `embeddings` optional extra for NumPy and a `embeddings-faiss` extra for FAISS, and document CLI usage, vector format, and similarity behavior in `README.md` and `docs/`. Affected files: `pyproject.toml`, `README.md`, `docs/`. Validation: `pip install -e ".[embeddings]"` works, and the README example results in successful API calls.


## Validation and Acceptance


Sprint 1 validation confirms embedding columns are excluded from the base table load, `GET /embeddings` returns detected and rejected columns with reasons, and `POST /embeddings/search` returns top K results ordered by similarity for both `query_path` and base64 vector inputs. Tests cover invalid base64, dimension mismatch, NaN vectors, and duplicate paths. Manual validation confirms no memory spike on datasets with large embedding columns.

Sprint 2 validation confirms the Inspector exposes a working "Find similar" flow, embedding selection and vector input are usable, similarity results replace the grid with a clear exit, and sort controls are disabled while similarity mode is active. Filters remove items without reordering.

Sprint 3 validation confirms cache behavior (created when allowed, reused on subsequent starts, invalidated on Parquet changes, disabled in `--no-write`), that optional FAISS works when installed and falls back when not installed, and that documentation accurately reflects CLI usage and vector encoding.

Overall acceptance is met when a user can run the server on a large `items.parquet` with an embedding column, avoid loading embeddings into the item cache, run similarity search from both the API and UI, and see ordered results without a crash or UI confusion.


## Idempotence and Recovery


Embedding caches are safe to delete; rebuilding them is a pure, repeatable operation based on `items.parquet`, the selected embedding column, and the cache key. Running the server with `--no-write` disables cache writes and keeps the feature read-only. If a cache is corrupted, deleting the cache directory and reloading safely rebuilds it. If FAISS is unavailable, the system falls back to NumPy without changing API behavior. If an embedding column is removed or its schema changes, auto-detection should drop it and the cache key should no longer match.


## Artifacts and Notes


Example `POST /embeddings/search` payloads:

    {"embedding": "clip", "query_path": "/images/cat.jpg", "top_k": 50, "min_score": 0.2}

    {"embedding": "clip", "query_vector_b64": "BASE64_FLOAT32", "top_k": 50, "min_score": 0.2}

Example response sketch (ordering is significant):

    {"embedding": "clip", "items": [{"row_index": 12, "path": "/images/cat.jpg", "score": 1.0}, {"row_index": 78, "path": "/images/tiger.jpg", "score": 0.87}]}

Vector encoding contract (documented and enforced by the server):

    - base64 standard encoding
    - little-endian float32
    - length must equal embedding dimension

Suggested cache location patterns:

    DATASET_ROOT/.lenslet/embeddings_cache/{hash}.npz
    <parquet>.cache/embeddings_cache/{hash}.npz
    /custom/cache/dir/embeddings_cache/{hash}.npz


## Interfaces and Dependencies


API endpoints should be:

- `GET /embeddings` returns available embeddings with name, dimension, dtype, metric, and a rejected list with reasons.
- `POST /embeddings/search` accepts `embedding`, `query_path` or `query_vector_b64`, `top_k`, `min_score`, and returns ordered items with `row_index`, `path`, and `score`.

CLI flags should include:

- `--embedding-column` (repeatable, to override auto-detection).
- `--embedding-metric <name>:<metric>` (repeatable; default cosine).
- `--embedding-preload` (build on startup).
- `--embedding-cache/--no-embedding-cache` (enable/disable cache; auto-disabled by `--no-write`).
- `--embedding-cache-dir <path>` (override cache location).
- `--embedding-backend {auto,numpy,faiss}`.

Dependencies should include:

- `embeddings` extra: NumPy (required for similarity search).
- `embeddings-faiss` extra: FAISS CPU for accelerated search.
- PyArrow remains the Parquet reader.

If a bfloat16 column is encountered and the local PyArrow build lacks bfloat16 support, the server should report the column as rejected with a clear reason.


Change note: Updated after subagent review to clarify join key, vector encoding, detection rules, split tasks, add validation gaps, and refine cache invalidation.
