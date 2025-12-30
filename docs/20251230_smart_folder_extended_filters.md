# Smart Folders: Extended Filters (filename/date/stars/comments/url/dimensions)

This ExecPlan is a living document. The sections `Progress`, `Surprises & Discoveries`, `Decision Log`, and `Outcomes & Retrospective` must be kept up to date as work proceeds.

If a PLANS.md file is checked into the repo, this document must be maintained in accordance with it.

## Purpose / Big Picture

Extend Smart Folders beyond metrics-only filters so users can build practical views from everyday metadata: filename includes/excludes, star ratings (including “not in”), comments contain/not contain, URL contain/not contain, and width/height comparisons, plus date ranges. These filters should be first-class in ViewState, persist in Smart Folders, and behave consistently in no-write mode.

User-visible proof: a user can open a dataset, set filters like “filename contains ‘draft’”, “stars not in {1,2}”, “comments contain ‘hero’”, “url contains ‘s3://bucket’”, “width >= 2048”, and “date between 2024-01-01 and 2024-06-30”, save as a Smart Folder, refresh, and see it reapply correctly.

## Progress

- [x] (2025-12-30) Implemented extended Smart Folder filters (filename, date, stars include/exclude, comments, url, width/height) with UI, persistence, and tests.

## Surprises & Discoveries

- None yet. Update this section with concrete evidence if unexpected behavior appears.

## Decision Log

- Decision: Extend the existing FilterAST with new clause types rather than introducing a parallel “advanced filter” system.
  Rationale: Minimal code surface area and reuse of current ViewState, persistence, and derived-state pipeline.
  Date/Author: 2025-12-30 / Assistant + User

- Decision: Keep filter evaluation client-side for now (matching current metrics filter behavior).
  Rationale: Avoid backend query engine complexity; keep MVP fast and simple.
  Date/Author: 2025-12-30 / Assistant + User

## Outcomes & Retrospective

- Added new FilterAST clauses, client-side matching logic, UI controls, and backend item fields for comments/url; verified via frontend filter tests.

## Context and Orientation

Current filter support:
- Metrics range filter and star filter in `frontend/src/features/browse/model/filters.ts`.
- ViewState stored in `frontend/src/app/AppShell.tsx` and persisted in `views.json` via `/views` endpoints.
- Item model in `frontend/src/lib/types.ts` includes `name`, `path`, `addedAt`, `size`, `w`, `h`, and `metrics`.

This plan extends the FilterAST and UI to cover additional fields, and adds backend plumbing for fields not currently exposed (comments, url) where needed.

## Plan of Work

### Milestone 1: Define filter schema (FilterAST) and helpers

Goal: Represent new filters in a stable, serializable schema, keeping compatibility with existing Smart Folders.

Work:
1) Extend `FilterClause` in `frontend/src/lib/types.ts` to include:
   - `starsIn`: `{ starsIn: { values: number[] } }` (includes 0 for “none”).
   - `starsNotIn`: `{ starsNotIn: { values: number[] } }`.
   - `nameContains`: `{ nameContains: { value: string } }`.
   - `nameNotContains`: `{ nameNotContains: { value: string } }`.
   - `commentsContains`: `{ commentsContains: { value: string } }`.
   - `commentsNotContains`: `{ commentsNotContains: { value: string } }`.
   - `urlContains`: `{ urlContains: { value: string } }`.
   - `urlNotContains`: `{ urlNotContains: { value: string } }`.
   - `dateRange`: `{ dateRange: { from?: string; to?: string } }` (ISO, UTC).
   - `widthCompare`: `{ widthCompare: { op: '<' | '<=' | '>' | '>='; value: number } }`.
   - `heightCompare`: `{ heightCompare: { op: '<' | '<=' | '>' | '>='; value: number } }`.
2) Add helper functions in `frontend/src/features/browse/model/filters.ts` for get/set/remove operations per clause.
3) Update `countActiveFilters` to count only meaningful clauses (non-empty arrays and non-empty strings).

Acceptance:
- FilterAST can represent all new filter types.
- Parsing unknown or malformed clauses safely drops them without breaking existing views.

### Milestone 2: Data plumbing for filterable fields

Goal: Ensure all filterable fields are present in `Item` on the frontend.

Work:
1) Confirm available fields today (already present):
   - `name`, `path`, `addedAt`, `size`, `w`, `h`, `star`, `metrics`.
2) Add fields as needed:
   - `comments` (string, from sidecar `notes` or a dedicated comment field).
   - `url` (string if source is S3/HTTP; empty/null otherwise).
3) Backend changes:
   - Update `Item` model in `src/lenslet/server.py` to include `comments` and `url` if needed.
   - Populate `comments` from sidecar metadata (or a stable server-side cache).
   - For datasets with URL-backed sources (S3/HTTP), propagate `url` through storage to `Item`.
4) Frontend: update `frontend/src/lib/types.ts` and any dependent rendering to accept the new optional fields.

Acceptance:
- Items expose `comments` and `url` where applicable (null/empty otherwise).
- Existing behavior for local filesystem datasets remains unchanged.

### Milestone 3: Filter evaluation logic

Goal: Make filters work on the client with predictable semantics and performance.

Work:
1) Extend `matchesClause` in `frontend/src/features/browse/model/filters.ts`:
   - Stars include and exclude logic (0 means “none”).
   - Contains/not-contains for filename, comments, URL (case-insensitive, substring).
   - Date range on `addedAt` (parse once per item per pass; treat missing as non-match).
   - Width/height comparisons (treat 0 or missing as non-match).
2) Keep existing metric filter behavior unchanged.

Acceptance:
- A filter set of mixed clause types works (AND semantics).
- Not-in and not-contains behave as expected.

### Milestone 4: UI for editing filters

Goal: Make new filters discoverable and easy to edit alongside metrics.

Work:
1) Extend the Filters UI:
   - Add a new “Attributes” section in `frontend/src/features/metrics/MetricsPanel.tsx` (or split into a new FiltersPanel).
   - Controls:
     - Star rating include/exclude multi-select (two chips or a toggle).
     - Filename contains / does not contain inputs.
     - Comments contains / does not contain inputs.
     - URL contains / does not contain inputs.
     - Date range from/to (simple date inputs; store ISO strings).
     - Width and height comparison selectors (`<`, `<=`, `>`, `>=`) with numeric inputs.
2) Update filter chips in `frontend/src/app/AppShell.tsx` to show the new filters and allow removal.
3) Update the toolbar filters badge count to include all active filters (not just stars/metrics).

Acceptance:
- UI supports editing all new filters.
- Active filters show as chips and can be removed individually.

### Milestone 5: Persistence and Smart Folders

Goal: Ensure Smart Folders persist and re-apply extended filters reliably.

Work:
1) Keep `views.json` format stable (version 1), but allow additional clause types in `view.filters`.
2) Update parsing/validation in `frontend/src/app/AppShell.tsx` to accept new clauses and reject malformed data safely.
3) Ensure no-write mode exports the same view payload with the new filters.

Acceptance:
- Saving a Smart Folder persists the new filters.
- Reloading re-applies them without errors.

### Milestone 6: Tests

Goal: Protect filter logic with targeted tests.

Work:
1) Add tests in `frontend/src/features/browse/model/__tests__/filters.test.ts` for:
   - stars in / stars not in
   - filename contains / not contains
   - comments contains / not contains
   - url contains / not contains
   - date ranges
   - width/height comparisons
2) Add tests for clause parsing/validation if a helper is introduced.

Acceptance:
- Tests cover all new filter types.
- Tests run under existing test tooling (vitest).

## Validation and Acceptance

- Users can filter by filename contains/not contains.
- Users can filter by star rating include or exclude sets (including “none”).
- Users can filter by comments and URL contains/not contains.
- Users can filter by width and height using comparison operators.
- Users can filter by date range using ISO dates.
- Smart Folders persist the full filter set and reapply after refresh.
- No-write mode exports views with the extended filters.

## Idempotence and Recovery

- Loading a view with unknown filter clauses should ignore those clauses, not crash.
- Malformed filters in localStorage or `views.json` should be dropped with safe defaults.
- Missing fields on items (comments/url/addedAt) should make the item not match filters targeting those fields.

## Interfaces and Dependencies

Frontend:
- `frontend/src/lib/types.ts`: FilterAST + Item fields.
- `frontend/src/features/browse/model/filters.ts`: clause evaluation + helpers.
- `frontend/src/features/metrics/MetricsPanel.tsx` or a new `frontend/src/features/filters/FiltersPanel.tsx`: UI controls.
- `frontend/src/app/AppShell.tsx`: filter chips, persistence parsing/validation.

Backend:
- `src/lenslet/server.py`: expose `comments` and `url` on Item if required.
- Storage (dataset/parquet/memory/local): ensure url/comment data are available where possible.

## Future Expansion Guardrails (Do / Don’t)

Do:
- Keep all filters in a single FilterAST with AND semantics.
- Keep UI sections compact and grouped (Stars, Text, Date, Size/Dimensions, Metrics).

Don’t:
- Don’t add backend query engines until client-side filtering becomes a bottleneck.
- Don’t introduce multiple filter schemas or hidden filter state that bypasses Smart Folders.

---

Change note (required for living plans): This plan extends Smart Folders to cover filename/date/star/comments/url/dimension filters, preserving the existing ViewState and persistence model.
