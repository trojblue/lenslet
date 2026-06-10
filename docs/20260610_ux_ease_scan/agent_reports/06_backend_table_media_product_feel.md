# Backend/Table/Media Product Feel Scan

## Journeys Inspected

- Launching Lenslet on a normal local image directory, including auto-indexed filesystem storage, workspace creation under `.lenslet`, refresh behavior, labels, and thumbnail caching.
- Launching on a directory that contains `items.parquet`, where the UI behaves like a table-backed gallery but the command still looks like a directory launch.
- Launching on a standalone Parquet table with detected source columns, explicit `--source-column`, explicit `--path-column`, auto-detected `--base-dir`, and dimension caching.
- Launching on remote table inputs, including `hf://` datasets, Hugging Face owner/repo shorthand, HTTP/S3 remote tables via `unibox`, and table rows that point at HTTP/S3 media.
- Viewing media from local files, HTTP URLs, and S3 objects through `/file`, `/thumb`, direct HTTP originals, and generated thumbnails.
- Running in shared/read-only states: `--share`, `--no-write`, remote table mode, local table sidecar mode, and local browser trusted-origin mutation checks.
- Handling large or partially bad datasets: missing local files, outside-root paths, symlink safety checks, blank/non-image rows, missing dimensions, remote rows with bad credentials or timeouts, large recursive folders, and lazy Parquet field access.

## Current Strengths

- The launch model already supports the main user journeys: local folders, `items.parquet`, standalone Parquet, Hugging Face datasets, remote table URIs, HTTP media, and S3 media.
- The CLI has explicit controls for the important escape hatches: `--source-column`, `--path-column`, `--base-dir`, `--probe-dimensions`, `--no-cache-dimensions`, `--no-write`, `--share`, and thumbnail cache settings.
- Source image directories and S3 buckets are treated as read-only. Local path resolution enforces base-directory boundaries and realpath checks, so unsafe table paths are rejected instead of silently escaping the dataset root.
- The banner distinguishes filesystem, table, remote table, shared read-only, temp cache, and parquet sidecar workspaces. This is a good base for a more complete launch summary.
- Table source detection is better than a naive column-name match. It samples candidate columns, scores image-like values, supports extensionless S3 keys, and exposes source switching through `/table/source-columns`.
- Logical paths are derived consistently for local files, S3 keys, and HTTP URLs, and `--path-column` gives users control over display paths when table-derived paths are not what they want.
- Media reads use typed backend error categories, HTTP timeouts, connection pooling, lazy S3 client creation, and bounded remote dimension probing. The backend has enough structure to expose better UX without a rewrite.
- Large table behavior has practical safeguards: projected Parquet reads, lazy row field loading, recursive browse limits, direct window queries, and a static table refresh contract.
- Share mode correctly changes the mutation trust model, so remote viewers do not get write access just because the local owner can edit.

## Ranked Opportunities

1. **Make startup print the effective source plan**
   - Severity: High.
   - User impact: A user can launch a Parquet/HF/remote table and not know which column became the image source, which column controls paths, whether a root was auto-detected, how many rows became gallery items, how many were skipped, or whether dimensions will be read or written. Surprises show up later as missing rows, odd folder names, blank cards, or unexpected file changes.
   - Likely code area: `src/lenslet/cli/browse.py`, `src/lenslet/storage/table/launch.py`, `src/lenslet/storage/table/storage.py`, `/health`, and `frontend/src/app/components/StatusBar.tsx`.
   - Fix concept: Create a small launch summary object from the existing table launch and row-store data. Print it in the CLI banner and expose a redacted version to the UI: selected source column, path column or derived path mode, base/root policy, workspace kind, total table rows, gallery rows, skipped rows by reason, dimension coverage, and media source kind.
   - Effort: M.
   - Performance/code-bloat risk: Low to medium. Reuse counts already computed during row-store construction and dimension inspection; avoid introducing a second table scan.
   - Validation method: CLI snapshot tests for local directory, `items.parquet`, standalone Parquet, remote table, `--no-write`, and `--share`; API contract test for the summary payload; one browser smoke check that the UI status matches the launch state.

2. **Stop making Parquet dimension writes feel implicit**
   - Severity: High.
   - User impact: Lenslet strongly communicates that source images are read-only, but a standalone Parquet launch can write missing `width`/`height` back into the table by default. That may be correct for convenience, but it can surprise users working with shared datasets, checked-in tables, or read-only mental models.
   - Likely code area: `src/lenslet/cli/browse_args.py`, `src/lenslet/storage/table/launch.py`, README launch docs, and banner text in `src/lenslet/cli/browse.py`.
   - Fix concept: Treat Parquet mutation as a visible launch decision. At minimum, print the missing-dimension count and the exact write target before probing/caching. A cleaner alpha cutover would make no-write/no-cache the default and add an explicit `--cache-dimensions` opt-in for table mutation.
   - Effort: S for transparent messaging, M for changing the default.
   - Performance/code-bloat risk: Low. The only product risk is slower repeat loads if caching becomes opt-in; keep the flag obvious and the status clear.
   - Validation method: Tests for default table launch messaging, `--no-cache-dimensions`, `--no-write`, `--probe-dimensions`, and the existing dimension-cache write path.

3. **Show media failures instead of blank cards or endless loaders**
   - Severity: High.
   - User impact: Backend media routes can distinguish missing files, decode failures, remote permission errors, timeouts, and upstream failures, but the frontend often swallows blob fetch errors. Users see a missing thumbnail or a viewer that never resolves, which makes bad rows look like a UI bug.
   - Likely code area: `frontend/src/shared/hooks/useBlobUrl.ts`, thumbnail card components, `frontend/src/app/components/Viewer.tsx`, compare viewer code, and `src/lenslet/web/media.py`.
   - Fix concept: Replace the blob-only hook with a small resource state: `loading`, `url`, `error`, and `retry`. Render compact card-level placeholders and viewer-level error messages such as "remote access denied", "remote timed out", "file not found", or "decode failed". Keep the full error details in developer-visible text or logs, not in every card.
   - Effort: M.
   - Performance/code-bloat risk: Medium. Keep the state model centralized so every media surface does not grow separate error logic.
   - Validation method: Frontend tests with mocked 403, 404, 422, 504, and network failures; existing media route tests; Playwright smoke using a small table with one good row and several bad rows.

4. **Distinguish remote shape detection from real reachability**
   - Severity: High.
   - User impact: A remote URL/S3 column can look loadable because values have plausible URI shapes, while actual media access may fail from expired URLs, missing credentials, 403s, 404s, CORS, hotlink blocking, or slow hosts. The UI currently does not make that uncertainty clear.
   - Likely code area: `src/lenslet/storage/table/source_detection.py`, `src/lenslet/storage/table/storage.py`, `src/lenslet/storage/source/media.py`, `/table/source-columns`, and the settings source selector.
   - Fix concept: Add a bounded reachability sample that is separate from source detection. Report categories like `not_checked`, `reachable_sample`, `permission_failed`, `not_found`, `timeout`, and `unknown_error`. Run it lazily from source settings or after launch in the background; do not block first paint.
   - Effort: M.
   - Performance/code-bloat risk: Medium. Network probes can be expensive or flaky, so cap sample size, reuse the existing HTTP/S3 clients, cache results per source signature, and make the UI tolerant of unknowns.
   - Validation method: Fake HTTP server tests for success, 403, 404, timeout, and bad content type; S3 client stub tests; UI test that "looks image-like" is not presented as guaranteed reachable.

5. **Make the source selector diagnostic, not just a dropdown**
   - Severity: Medium.
   - User impact: Users can switch image columns, but the settings menu only shows `sample_usable / sample_total` and switch failures are swallowed. A wrong source column remains hard to understand, especially when multiple URL/path columns exist.
   - Likely code area: `frontend/src/shared/ui/ThemeSettingsMenu.tsx`, `frontend/src/app/AppShell.tsx`, `src/lenslet/web/routes/table_settings.py`, and `TableSourceColumnStatus`.
   - Fix concept: Show per-column subtitles with sampled rows, loadable rows, image-like rows, and warnings. Label the current recommendation. If a switch fails, surface the failure in the status bar and keep the previous source selected.
   - Effort: S.
   - Performance/code-bloat risk: Low. The backend already computes most candidate status fields.
   - Validation method: Component tests for candidate rendering and failed switches; API tests for warning fields; manual check with a table that has `image_url`, `source_url`, and `s3key`.

6. **Expose workspace/read-only state as a first-class UI concept**
   - Severity: Medium.
   - User impact: Local owners, share recipients, no-write users, and remote table viewers all see different persistence rules, but the UI collapses much of that into generic read-only or refresh-disabled text. Users need to know whether labels/views persist, stay in memory, write to a sidecar, or live in a temp cache.
   - Likely code area: `src/lenslet/workspace.py`, `src/lenslet/web/app/health.py`, `frontend/src/lib/types.ts`, `StatusBar`, and settings or command banner text.
   - Fix concept: Add a small workspace status payload: `persistent_sidecar`, `dataset_workspace`, `temp_workspace`, `memory_only`, or `shared_read_only`, plus `labels_persisted`, `views_persisted`, `thumbnail_cache`, and a redacted local-only path. Show this as one concise status item rather than a long warning.
   - Effort: S to M.
   - Performance/code-bloat risk: Low. The main risk is leaking local paths to shared clients; redact or omit paths when the request origin is not trusted local.
   - Validation method: Health contract tests for local, share, no-write, standalone Parquet, and remote table launches; browser smoke for share/read-only messaging.

7. **Surface skipped and degraded rows beyond terminal logs**
   - Severity: Medium.
   - User impact: Bad source rows, missing local files, paths outside the root, symlink-blocked files, blank sources, non-image values, and row-field read failures can remove or degrade content. If the user misses startup logs, the UI offers little explanation for why expected rows are absent.
   - Likely code area: `src/lenslet/storage/table/row_store.py`, `src/lenslet/storage/table/storage.py`, `src/lenslet/web/app/health.py`, `frontend/src/app/components/StatusBar.tsx`, and table source settings.
   - Fix concept: Accumulate a small degraded-row summary during row-store construction and lazy row-field reads. Expose counts by reason, with one drill-down endpoint or sample list only if needed. Show a dismissible status message when degradation is material.
   - Effort: M.
   - Performance/code-bloat risk: Low if only counters and a few examples are retained. Avoid storing every bad row in memory for huge tables.
   - Validation method: Unit tests for each skip reason, API contract tests for summary fields, and Playwright smoke with a mixed good/bad table.

8. **Make dimension completeness visible**
   - Severity: Medium.
   - User impact: Remote and large table launches can have many unknown dimensions. The gallery can still render with fallback aspect ratios, but width/height filters and visual confidence suffer. Users do not know whether dimensions are missing, being probed, cached, or intentionally skipped.
   - Likely code area: `src/lenslet/storage/table/launch.py`, `TableStorage`, `/health`, metrics/facet payloads, `StatusBar`, and attribute/filter UI.
   - Fix concept: Report dimension status as `known`, `missing`, `probe_policy`, `cache_policy`, and `write_target`. In UI, show a small status when many rows have unknown dimensions and make dimension filters indicate incomplete coverage.
   - Effort: M.
   - Performance/code-bloat risk: Low to medium. Counting known dimensions is already part of launch inspection; avoid probing all remote rows just to improve the number.
   - Validation method: Tests for tables with complete dimensions, partial dimensions, no dimensions, skipped probe, forced probe for caching, and no-write mode.

9. **Revisit direct HTTP originals as the default viewer strategy**
   - Severity: Medium.
   - User impact: Thumbnails are fetched through Lenslet, but the full-size viewer defaults to loading HTTP originals directly when proxying is off. That can fail due to CORS, auth, hotlink rules, mixed network policy, or temporary URL behavior even when backend thumbnails work.
   - Likely code area: `frontend/src/shared/originalImageResource.ts`, viewer components, `ThemeSettingsMenu`, and backend `/file` handling.
   - Fix concept: Prefer backend proxy for table/remote HTTP originals, or automatically fall back to proxy on direct image failure. Keep direct loading as an explicit performance toggle for users who know the remote host supports it.
   - Effort: M.
   - Performance/code-bloat risk: Medium. Proxying originals increases backend bandwidth and memory pressure for non-local media; pair it with clear limits and streaming where possible.
   - Validation method: Browser test with a remote image that allows backend fetch but blocks direct browser display; performance check for large originals; setting persistence test for users who opt into direct loading.

10. **Make remote/HF table startup feel alive**
   - Severity: Medium.
   - User impact: Loading an HF dataset or remote table can involve listing files, downloading shards, reading Parquet, concatenating tables, and detecting source columns before the server starts. With no progress, users cannot tell whether Lenslet is stuck, downloading, or about to open.
   - Likely code area: `src/lenslet/cli/hf_table.py`, `_load_remote_table` in `src/lenslet/cli/browse.py`, and terminal banner/degraded reporting utilities.
   - Fix concept: Print phase-based progress: resolving dataset, selected parquet files, downloading shard `n/m`, reading rows, selected source column, and final row count. For very large remote tables, add a clear memory/size warning and later move toward streaming or lazy dataset reads.
   - Effort: S for progress, L for true streaming/lazy remote table ingestion.
   - Performance/code-bloat risk: Low for progress messages, high for a streaming rewrite. Keep the first step observational.
   - Validation method: HF API/download stubs with captured stderr/stdout; failure tests for missing optional dependencies and bad URIs; manual run on a multi-shard fixture.

11. **Keep backend media error semantics through to HTTP and UI**
   - Severity: Low to Medium.
   - User impact: Remote 404s can be flattened to generic "file not found", and structured backend categories are not consistently available to the client. Users need different recovery paths for local missing files, remote not found, permission errors, timeouts, and decode failures.
   - Likely code area: `src/lenslet/web/media.py`, `src/lenslet/storage/source/media.py`, `src/lenslet/storage/source/media_errors.py`, API fetch utilities, and frontend error rendering.
   - Fix concept: Preserve structured error codes in media responses, with `RemoteMediaNotFoundError` handled before generic `FileNotFoundError`. Return stable client-facing codes such as `local_not_found`, `remote_not_found`, `permission`, `timeout`, `decode`, and `upstream`.
   - Effort: S.
   - Performance/code-bloat risk: Low. This is a contract cleanup, not a new subsystem.
   - Validation method: Extend existing media error contract tests and frontend fetch tests to assert displayed messages for each code.

12. **Add a bounded "what did Lenslet index?" inspection endpoint**
   - Severity: Low to Medium.
   - User impact: When a table launch looks wrong, users currently have to infer behavior from CLI logs, folder paths, and source settings. A lightweight inspection endpoint would make support and self-diagnosis much easier without adding setup burden.
   - Likely code area: `src/lenslet/web/routes`, `TableStorage`, `LocalStorage`, frontend settings/status surfaces, and docs.
   - Fix concept: Add a local-trusted endpoint or UI panel that reports the first few indexed rows, source values, logical paths, dimensions, media kind, and skip samples. Keep it diagnostic and bounded; do not make it part of normal browsing payloads.
   - Effort: M.
   - Performance/code-bloat risk: Medium. Limit samples, redact sensitive values for shared clients, and avoid creating a second table browser inside the app.
   - Validation method: API tests for bounded samples and redaction; manual diagnostics against local, S3, HTTP, and mixed-source tables.

## 3 Quick Wins

1. Print a compact launch summary after table/source detection: selected source column, path mode, base/root policy, workspace mode, dimension cache policy, total rows, gallery rows, and skipped rows.
2. Surface media fetch failures in thumbnails and viewers instead of swallowing blob errors. Start with stable messages for 403, 404, 422, 504, and generic upstream failure.
3. Improve the source column dropdown with `sample_loadable`, `sample_usable`, warnings, a recommended/current label, and visible switch failure feedback.

## 3 Medium Projects

1. Build a unified table/media diagnostics payload for health/status: workspace kind, media source kind, source/path selection, skipped-row counters, dimension coverage, and remote reachability sample state.
2. Redesign remote original loading around backend proxy plus direct-load fallback: default to reliable display, expose direct HTTP loading as an explicit performance choice, and add browser-side fallback on direct image failure.
3. Make remote/HF ingestion progressive and scalable: phase-based terminal progress first, then a larger streaming/lazy table path for datasets that should not be fully downloaded and concatenated before startup.

## Things Not To Do

- Do not probe every remote URL at launch. It would make large remote tables slow, noisy, and dependent on external host behavior before first paint.
- Do not add compatibility layers for old table/source contracts. This is alpha; make the cleaner source, workspace, and diagnostics contracts foundational.
- Do not silently write to source tables or cache directories while presenting the session as read-only. If anything is written, name the target and why.
- Do not expose raw local absolute paths, credentials, presigned URLs, or sensitive source values to shared clients.
- Do not bury source selection, row skips, media failures, or workspace persistence only in terminal logs. The UI needs concise state for the user currently looking at the gallery.
- Do not make users configure many flags before first useful load. Prefer automatic detection plus visible, reversible decisions.
- Do not remove large-table limits to make recursive loading appear easier. Keep limits, but explain them and offer direct window/query paths.
- Do not create separate diagnostic implementations in CLI, API, and frontend. One backend summary should feed the banner, health/status UI, and tests.

## Top 5 Recommendations

1. Add a shared launch/source summary and show it in both the CLI banner and UI health/status surfaces.
2. Make Parquet dimension caching explicit, with a strong preference for an alpha cutover to opt-in table mutation.
3. Render media failures as actionable thumbnail/viewer states using the backend's existing error categories.
4. Separate remote source shape detection from actual reachability, using bounded background samples instead of blocking launch.
5. Promote workspace/read-only, skipped-row, and dimension-completeness state from logs into first-class UI status.
