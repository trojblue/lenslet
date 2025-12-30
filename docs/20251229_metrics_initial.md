# Add parquet-backed metrics, filtering, and a lightweight analysis workspace to Lenslet

This ExecPlan is a living document. The sections `Progress`, `Surprises & Discoveries`, `Decision Log`, and `Outcomes & Retrospective` must be kept up to date as work proceeds.

If a PLANS.md file is checked into the repo, this document must be maintained in accordance with it.

## Purpose / Big Picture

After this change, Lenslet users can open a dataset whose metadata and metrics are stored in Parquet files, sort the gallery by any metric (for example, `clip_aesthetic` high → low), filter by metric ranges using a histogram-based UI that overlays the filtered distribution on the full population, and save those filter/sort presets as “Smart Folders” that persist alongside the dataset. Users can also run in a “one-off” mode that leaves no traces (no writes), using the same UI and code paths with writes disabled.

The user-visible proof is: start the server on a dataset that contains `items.parquet` and `metrics.parquet`, open the UI, switch to the Metrics panel, select a metric, see a population histogram and a filtered overlay histogram, brush a range to filter, sort by that metric, save the view as a Smart Folder, reload the page and see the Smart Folder still present (unless running in no-write mode).

## Progress

- [x] (2025-12-29) Drafted the initial ExecPlan based on current repo architecture summary and UX decisions.
- [x] (2025-12-29) Implemented Parquet dataset ingestion on the backend (items + metrics), plus a dataset workspace folder `.lenslet/`.
- [x] (2025-12-29) Added a minimal “View State” layer on the frontend separating pool (scope) from view (filters/sort), without breaking existing folder routing.
- [x] (2025-12-29) Added metric sorting and a dedicated Filter entry point in the Toolbar, wired into the derived-state pipeline.
- [x] (2025-12-29) Implemented a lightweight left rail + left panel host (Folders vs Metrics) while keeping the existing CSS grid + resize logic intact.
- [x] (2025-12-29) Implemented histogram overlay (population vs filtered) and range brushing for metric filters.
- [x] (2025-12-29) Implemented persisted Smart Folders (saved views) stored under `DATASET_ROOT/.lenslet/`, plus no-write behavior.
- [x] (2025-12-29) Documented “dos and don’ts” for future expansion (more workspaces/panels, inference, embeddings) without turning the UI into a docking system.

## Surprises & Discoveries

- None yet. Update this section with concrete evidence if unexpected behavior appears (for example: Parquet schema mismatches, UI perf regressions, or file permission failures on FSx).

## Decision Log

- Decision: Store persistent workspace artifacts next to the dataset in `DATASET_ROOT/.lenslet/` by default.
  Rationale: Dev pods may restart and lose `~/`, while the dataset on FSx is durable. Keeping workspace co-located makes the “project” travel with the dataset.
  Date/Author: 2025-12-29 / Assistant + User

- Decision: Avoid DuckDB initially; implement with simpler in-memory logic (Python + Parquet readers; client-side derived state).
  Rationale: Performance is not currently the bottleneck; additional dependencies and query engines add complexity. The plan must not block future DuckDB adoption.
  Date/Author: 2025-12-29 / Assistant + User

- Decision: Use a single system with an optional “no-write” switch rather than multiple modes and multiple storage backends.
  Rationale: Minimizes maintenance and mental overhead. “One-off mode” becomes a special case of the main system with writes disabled.
  Date/Author: 2025-12-29 / Assistant + User

- Decision: Implement a lightweight “VSCode-style” approach limited to vertical panels only.
  Rationale: A full docking system (bottom panels, arbitrary docking) increases layout/state complexity. Vertical-only keeps the skeleton stable.
  Date/Author: 2025-12-29 / Assistant + User

- Decision: Keep “Sort” and “Filter” as distinct UI affordances; do not hide filtering in the sort dropdown.
  Rationale: Prevents UI ambiguity and “random commands everywhere.” Keeps the mental model: Sort changes order; Filter changes membership.
  Date/Author: 2025-12-29 / Assistant + User

## Outcomes & Retrospective

- (2025-12-29) Shipped Parquet ingestion with metrics, view-state separation, metrics sorting/filtering with histogram brushing, left-rail panel switcher, and Smart Folder persistence with no-write export fallback. Added backend tests for Parquet joins and workspace persistence. No major surprises observed.

## Context and Orientation

Lenslet today is a FastAPI backend and a React (Vite) frontend.

On the frontend, `frontend/src/AppShell.tsx` defines the entire layout using a CSS grid with three columns: a left panel (folder tree), a central virtualized image grid, and a right panel (inspector). `useSidebars` controls left/right panel widths and open/close state by updating CSS variables, minimizing re-rendering. The UI state uses a “derived state” pattern in `AppShell`: fetch folder data, merge optimistic star overrides, apply filters, apply sort, and render the final list.

Key frontend paths mentioned in this plan:
- `frontend/src/AppShell.tsx` (layout, state derivation)
- `frontend/src/shared/ui/Toolbar.tsx` (sort control, panel toggles, search)
- `frontend/src/features/browse/model/apply.ts` (applyFilters/applySort pipeline)
- `frontend/src/features/browse/model/sorters.ts` (sort comparators)
- `frontend/src/features/inspector/Inspector.tsx` (details panel)

Backend context (from existing plan draft):
- FastAPI serves folder index and thumbnails.
- Storage is in-memory, read-only indexing today (filesystem/S3/HTTP), with session-only metadata.
- This ExecPlan adds Parquet-backed dataset ingestion and a dataset-local workspace directory.

Definitions used in this plan:
- Dataset root: the directory (or mounted path) that contains the dataset’s Parquet files and the images they refer to.
- Workspace folder: `DATASET_ROOT/.lenslet/`, where Lenslet stores saved views and cached artifacts in heavy-use mode.
- Pool (scope): the set of images currently under consideration (for example a folder path, or a saved Smart Folder that defines a set).
- View state: filters, sort, and optional visualization settings (like “selected metric”) applied to the pool.
- Smart Folder: a saved “view” that can be re-applied later; it typically includes a pool selector plus filters and sort.

## Plan of Work

This plan proceeds in milestones that each produce a demonstrably working behavior. Milestones intentionally avoid a full UI redesign; they extend the current skeleton in small, testable increments.

### Milestone 1: Parquet dataset ingestion (backend) with workspace folder semantics

Goal: Start Lenslet on a dataset that is described by Parquet files rather than only by scanning directories, and load per-image metrics from Parquet.

Work:
1) Define the initial on-disk dataset format. At minimum:
   - `DATASET_ROOT/items.parquet` contains one row per image. It must include a stable identifier and a reference to the image location. Prefer:
     - `image_id` (string or int) and `path` (string, relative path under dataset root).
     - optional: `mtime`, `size`, and any other display metadata you already use.
   - `DATASET_ROOT/metrics.parquet` contains one row per image with:
     - `image_id` (matching `items.parquet`) and metric columns (float or nullable float).
   The system must still be able to read image pixels from disk using the `path` column (thumbnails and full images).

2) Implement a backend ingestion path that:
   - loads `items.parquet` into memory at startup and constructs the same in-memory index the frontend expects.
   - if `metrics.parquet` exists, joins metrics into the item model in memory.
   - if `metrics.parquet` does not exist, items still load and the UI operates without metrics.

3) Add workspace folder support:
   - In heavy-use mode (default), ensure `DATASET_ROOT/.lenslet/` exists and is writable.
   - In no-write mode, do not create `.lenslet/` and never write to it.

Files and edits (expected):
- In the backend entry point (for example `src/lenslet/server.py` or wherever dataset initialization occurs), add a “ParquetDataset” initialization path.
- In the storage layer (for example `src/lenslet/storage/...`), add a storage implementation that reads Parquet.
- Update the Pydantic `Item` model to include metrics either as:
  - `metrics: dict[str, float]` (MVP), or
  - a slimmer representation if payload becomes an issue later.
  The MVP should prioritize working behavior over payload optimization.

Acceptance:
- Starting the server with a dataset that contains `items.parquet` yields a working gallery.
- If `metrics.parquet` exists, the API responses include metric values for items (at least for a few test rows).

### Milestone 2: Frontend “View State” separation (pool vs view), without breaking current routing

Goal: Make it easy to keep filters constant while changing the pool (folder/scope), enabling analysis workflows.

Work:
1) Introduce explicit state in `AppShell.tsx`:
   - PoolState: derived from current hash route (folder path) initially.
   - ViewState: holds filters and sort.
   This is primarily a refactor: the derived list in `useMemo` should become:
   - `poolItems` (resolved from folderData or search results)
   - `visibleItems` (applyFilters + applySort)

2) Keep current hash routing behavior intact: folder navigation still changes the pool.

3) Ensure the existing star filter and sort continue to work exactly as before after the refactor.

Acceptance:
- Before/after behavior matches for existing features (folder browsing, star filter, existing sorts).
- No new UI yet; this milestone is structural and verified by unchanged UX plus passing tests.

### Milestone 3: Metric sorting (Toolbar) integrated into the existing derived state pipeline

Goal: Sort by any metric from the Sort dropdown, without conflating filtering and sorting.

Work:
1) Update frontend types (for example `frontend/src/lib/types.ts`) so `Item` includes metrics from the backend.
2) Update sorting logic:
   - Extend `SortKey` to include metric sort keys, ideally as a tagged union:
     - built-in sorts (name/date/random)
     - metric sorts (metric key string)
   - Implement a comparator that treats missing metric values consistently (decide and document; for MVP use `-Infinity` for missing values when sorting ascending, or place missing last by default).
3) Update Toolbar sort dropdown:
   - Add a “Metrics” group populated by discovered metric keys.
   - Metric discovery should be stable and cheap: scan the first N items that have metrics, union keys, and memoize.

Acceptance:
- User can sort by a metric high → low and see the grid reorder accordingly.
- Sorting does not introduce visible jank on typical dataset sizes.

### Milestone 4: Lightweight left rail + left panel host (Folders vs Metrics), vertical-only

Goal: Introduce a “webapp” feel with a tool rail and switchable left panel content, without adding bottom panels or docking.

Work:
1) Keep the top-level grid in `AppShell.tsx` unchanged.
2) Inside the left column, add:
   - a narrow vertical rail (icons) for choosing which left panel tool is active:
     - Folders tool
     - Metrics tool
   - a panel host area that renders the selected panel.
3) Ensure the left panel remains resizable and collapsible via existing `useSidebars` logic.
4) Define minimal switching behavior:
   - Clicking the Filter button (added in the next milestone) automatically opens the left panel and selects the Metrics tool.
   - Users can manually switch back to Folders via the rail icon.

Acceptance:
- The folder tree still works when the Folders tool is active.
- Switching to Metrics shows a placeholder “Metrics Panel” without breaking layout.
- Resizing and collapsing the left panel behaves as before.

### Milestone 5: Filters as a first-class UI with histogram overlay (population vs filtered), wired to ViewState

Goal: Provide intuitive metric filtering and summary visualization without adding “random commands everywhere.”

Work:
1) Add a dedicated Filter entry point in the Toolbar:
   - A Filter button with an active-filter count badge.
   - Clicking it opens the left panel (if closed) and activates the Metrics tool.
2) Implement filter chips somewhere stable (recommended: a slim row under Toolbar or at the top of the grid region):
   - Each chip displays a readable filter (for example `clip_aesthetic: 0.70–0.92`).
   - Chips can be removed with one click.
3) Implement the Metrics panel as the primary filter editor:
   - A metric picker (choose metric).
   - A histogram view for the selected metric that renders:
     - population distribution for `poolItems`
     - overlay distribution for `visibleItems`
   - Brushing/dragging selects a range and updates `ViewState.filters`.
4) Histogram computation (MVP constraints):
   - Compute only for the selected metric (not for all metrics simultaneously).
   - Use memoization keyed by: metric key + pool identity + filter identity + bin count.
   - Choose a fixed, reasonable bin count (for example 40) for MVP.

Acceptance:
- User selects a metric and sees two distributions: population and filtered overlay.
- User brushes a range and sees the gallery update immediately.
- The overlay changes as filters change, proving it represents the filtered set.

### Milestone 6: Persisted Smart Folders (saved views) stored in `DATASET_ROOT/.lenslet/`, with no-write behavior

Goal: Turn ad-hoc filtering into reusable “Smart Folders” that persist across reloads, without introducing multiple modes or separate systems.

Work:
1) Define a saved view format (JSON) that is versioned and self-describing. It must include:
   - a human name
   - a pool selector (initially folder path; later may include other pool types)
   - filters (serialized)
   - sort (serialized)
   - optional: last selected metric for histogram
2) Backend persistence:
   - Add endpoints to read and write saved views under `DATASET_ROOT/.lenslet/views.json`.
   - In no-write mode, write endpoints must refuse safely (for example HTTP 403) and the UI must fall back to “export view” rather than failing silently.
3) Frontend integration:
   - Show Smart Folders in the Folders panel (as a section above the folder tree).
   - Add a small “Views” dropdown or button in the Toolbar for quick access while in the Metrics panel, so users do not need to switch tools to apply a saved view.
   - Implement “Save as Smart Folder” action from the current ViewState.
4) Apply semantics:
   - Applying a Smart Folder sets both pool and view state.
   - Provide an “Apply filters only” secondary action (later milestone if time permits) to reuse filters across folders without duplicating views.

Acceptance:
- In heavy-use mode, saving a Smart Folder persists it to disk and it reappears after a page refresh.
- In no-write mode, saving offers an export path (download/copy) and does not create `.lenslet/`.

### Milestone 7: Documentation and guardrails for future expansion (without implementing them yet)

Goal: Capture how to extend Lenslet without accumulating UI entropy or architectural debt.

Work:
1) Document the separation of concerns as rules for future contributors:
   - Workspaces: center-canvas task (Browse, Analyze, Compare, Annotate).
   - Panels: vertical side panels that support a workspace (Folders, Metrics, Inspector).
   - ViewState: shared data-level concepts (pool + filters + sort) used by Browse/Analyze-like workspaces.
2) Document dos and don’ts:
   - Do keep Filter separate from Sort.
   - Do keep Smart Folders as saved views, not “a special panel.”
   - Do prefer adding new workspaces via the left rail rather than stacking more permanent panels.
   - Don’t add bottom panels or docking until there is a clear, validated need.
   - Don’t compute histograms for all metrics by default; compute only what the user is looking at.
3) Record future plans (not implemented in this ExecPlan):
   - Inference-generated metrics:
     - a UI action to compute a metric column and cache it into Parquet, recording provenance.
     - caching location: `DATASET_ROOT/.lenslet/metrics_cache/` or merging into `metrics.parquet` with a manifest.
   - Embeddings:
     - store embeddings in Parquet keyed by `image_id`.
     - future: searchable index (may require additional infra; out of scope).
   - Payload optimization:
     - optional later change from per-item metrics dict to columnar metric endpoints.
   - DuckDB:
     - optional adoption later for large datasets and complex filtering; must be optional and not required for basic behavior.

Acceptance:
- A newcomer can read the docs and understand where to add future features without breaking the mental model or bloating the UI.

## Concrete Steps

These steps are written to be adapted to the repo’s existing tooling. If a command fails because the project uses a different tool (for example `pnpm` vs `npm`, or `uv` vs `pip`), inspect `frontend/package.json` and the backend’s `pyproject.toml`/README to choose the matching command.

1) From repository root, install frontend dependencies and run the dev server:

    cd frontend
    (choose one)
      pnpm install
      pnpm dev
    or
      npm install
      npm run dev

   Expected: a local dev URL prints in the terminal (for example `http://localhost:5173`).

2) In another terminal from repository root, run the backend on a dataset root directory:

    (example)
    python -m lenslet.server --root /path/to/DATASET_ROOT --port 8080

   Expected: server starts without errors. If there is a health endpoint, verify it:

    curl -i http://localhost:8080/health

   Expected: HTTP 200.

3) Prepare a minimal dataset for validation:
   - Ensure images exist under `DATASET_ROOT/` at the `path` locations referenced.
   - Create `items.parquet` with at least columns: `image_id`, `path`.
   - Create `metrics.parquet` with `image_id` and one metric column (for example `clip_aesthetic`).

4) Validation flow in the browser:
   - Navigate to the dataset folder (existing routing).
   - Open Metrics panel (left rail icon or Filter button).
   - Choose metric `clip_aesthetic`, confirm histogram appears.
   - Brush a range and confirm grid updates.
   - Sort by `clip_aesthetic` descending and confirm order changes.
   - Save as Smart Folder, refresh page, confirm it persists (heavy-use mode).
   - Restart backend with `--no-write` (or equivalent), attempt to save, confirm it does not write and instead exports.

## Validation and Acceptance

Acceptance is behavioral and must be demonstrable by a human:

- Parquet ingestion:
  - Starting the server on a dataset with `items.parquet` displays images in the gallery.
  - If `metrics.parquet` exists, at least one metric is visible in the Inspector for a selected image and available as a sort key.

- Sorting:
  - Selecting “Sort by metric: clip_aesthetic (desc)” reorders items correctly (spot-check by reading displayed metric values).

- Filtering and histogram overlay:
  - Metrics panel shows population histogram for selected metric.
  - After applying a range filter, an overlay distribution updates and visibly differs from the population when appropriate.
  - Clearing the filter restores the full population overlay and item count.

- Persistence:
  - In heavy-use mode, saving a Smart Folder persists to `DATASET_ROOT/.lenslet/views.json` and is visible after reload.
  - In no-write mode, Lenslet does not create `.lenslet/` and does not write any files.

Testing expectations (adapt to repo tooling):
- Run the frontend unit tests (if present) and ensure new tests exist for:
  - filter AST evaluation for metric ranges
  - sort comparator for metric values and missing values
- Run backend tests (if present) and ensure new tests exist for:
  - reading `items.parquet` and joining `metrics.parquet`
  - write denial in no-write mode

## Idempotence and Recovery

- Creating `.lenslet/` is idempotent. If it already exists, the server must reuse it.
- If `views.json` is malformed, the server must:
  - refuse to load it with a clear error and safe fallback (for example treat as empty views),
  - and not crash the whole app.
- If `metrics.parquet` schema changes (added columns), the ingestion should tolerate it and surface new keys in the UI.
- No-write mode must never write even partially; if a save is attempted, it must fail safely and not leave partial files.
- If a Parquet file is missing or unreadable, the UI should still load the gallery without metrics rather than failing entirely.

## Artifacts and Notes

Keep example artifacts minimal and repository-local:

- Example dataset layout:

    DATASET_ROOT/
      items.parquet
      metrics.parquet
      images/
        0001.jpg
        0002.jpg
      .lenslet/
        views.json

- Example “views.json” structure (indented example; versioned):

    {
      "version": 1,
      "views": [
        {
          "id": "top_clip",
          "name": "Top clip_aesthetic",
          "pool": { "kind": "folder", "path": "images/" },
          "view": {
            "filters": { "and": [ { "metricRange": { "key": "clip_aesthetic", "min": 0.7, "max": 1.0 } } ] },
            "sort": { "kind": "metric", "key": "clip_aesthetic", "dir": "desc" },
            "selectedMetric": "clip_aesthetic"
          }
        }
      ]
    }

## Interfaces and Dependencies

Backend interfaces (names and paths must be adapted to the repo’s actual module layout):
- A Parquet dataset loader that can:
  - read `items.parquet`
  - optionally read and join `metrics.parquet`
  - produce the in-memory list used by existing endpoints
- A workspace manager that exposes:
  - `workspace_root = DATASET_ROOT/.lenslet/`
  - `can_write: bool` (driven by a server flag / config)
  - helpers for atomic writes (write temp file then rename) to avoid corrupting `views.json`

Frontend interfaces (TypeScript; exact file paths based on existing structure):
- `PoolState`:
  - `kind: 'folder' | 'smartFolder' | 'search'`
  - `path?: string`
  - `smartFolderId?: string`
- `ViewState`:
  - `filters: FilterAST`
  - `sort: SortSpec`
  - `selectedMetric?: string`
- `FilterAST` (MVP):
  - supports at least: star filter (existing) and metric range filter
  - is serializable to JSON for persistence
- `SortSpec`:
  - `kind: 'builtin' | 'metric'`
  - `key: string`
  - `dir: 'asc' | 'desc'`

Dependencies:
- Parquet reading: use existing Python stack already in repo if available. If not:
  - prefer `pyarrow` for Parquet I/O (fast and common).
  - allow `pandas.read_parquet` if pandas is already present and acceptable for dataset sizes.
- Histogram rendering:
  - MVP can use SVG or Canvas without adding chart libraries.
  - Avoid heavy chart dependencies until the interaction is validated.

## Future Expansion Guardrails (Do / Don’t)

Do:
- Keep “workspaces” as center-canvas tasks (Browse, Analyze, Compare, Annotate).
- Keep panels vertical-only; add new tools via the left rail.
- Keep Filter separate from Sort; Smart Folders remain saved views, not a special panel.
- Compute histograms only for the selected metric; avoid all-metrics aggregation by default.

Don’t:
- Don’t introduce bottom panels or arbitrary docking without validated need.
- Don’t add panel proliferation that duplicates existing workspace affordances.
- Don’t couple dataset ingestion to a single backend engine (DuckDB should stay optional).

---

Change note (required for living plans): This initial version encodes the decisions from discussion: dataset-local workspace, no DuckDB initially, single system with optional no-write, and a lightweight VSCode-style vertical panel approach.
