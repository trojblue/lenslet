# Filters: Condition Builder UI (refactor “Metrics” sidebar into “Add conditions”)

This ExecPlan is a living document. The sections `Progress`, `Surprises & Discoveries`, `Decision Log`, and `Outcomes & Retrospective` must be kept up to date as work proceeds.

If a PLANS.md file is checked into the repo, this document must be maintained in accordance with it.

## Purpose / Big Picture

The current Filters UI is functional but visually “always-on”: it renders every possible filter control (stars, filename, comments, url, dates, dimensions, metrics…), whether or not the user needs them. This creates clutter and makes the user scan a long sidebar to do a simple thing.

Target UX (like image 2/3): a **condition builder**:
- Start with an empty (or minimal) state
- Users **add** conditions only when needed
- Conditions are shown as rows: **Field → Operator → Value**, removable
- Support **match mode** (“Any/All conditions”) and **groups** (AND between groups, each group can be Any/All)
- Reuse the same component for:
  - the “Filters” surface on the metrics/browse page, and
  - Smart Folder creation/editing dialogs

User-visible proof:
- On the metrics page, user clicks Filters, adds:
  - “Filename contains ‘draft’”
  - “Stars not in {1,2}”
  - “Width >= 2048”
- Results update immediately; “Active filters” shows compact chips; user saves as Smart Folder; refresh re-applies.

## Progress

- [x] (2025-12-30) Draft UX spec + data model mapping (this doc).
- [x] Implement FilterBuilder components + integrate into metrics page.
- [x] Replace legacy “all filters listed” sidebar with builder + active chips.
- [ ] Add tests + migration coverage (model tests updated; UI/integration pending).

## Surprises & Discoveries

- None yet. Update with concrete findings (perf bottlenecks, confusing semantics, etc.).

## Decision Log

- Decision: Make the condition-builder the **single** filters editor (reused in metrics page + Smart Folder dialogs).
  Rationale: One mental model, one codepath, fewer drift bugs.
  Date/Author: 2025-12-30 / Assistant + User

- Decision: Keep filter evaluation semantics unchanged unless explicitly needed (client-side, same matching rules).
  Rationale: This is a UI refactor; we should not silently change meaning.
  Date/Author: 2025-12-30 / Assistant + User

- Decision: Extend FilterAST to support grouping (Any/All + nested groups), but keep leaf clauses compatible.
  Rationale: Desired UI implies OR/AND structure; we need a stable serialized form for Smart Folders.
  Date/Author: 2025-12-30 / Assistant + User

- Decision: Remove toolbar star quick-toggles so the FilterBuilder is the sole editor surface.
  Rationale: Avoids divergent filter semantics and keeps a single source of truth.
  Date/Author: 2025-12-30 / Assistant + User

## Outcomes & Retrospective

- (In progress) Metrics panel now uses the additive FilterBuilder and active chips are derived from the new AST; UI tests and Smart Folder dialog reuse still pending.

---

## Context and Orientation

Current situation (image 1):
- Left sidebar shows a long list of filter sections, most unused most of the time.
- The UX cost is *visual scanning* and *cognitive load*, not missing functionality.

Desired situation (image 2/3):
- “Any/All conditions” selector
- A small set of condition rows (only what the user added)
- + to add condition, + to add group, - to remove
- Optional “Found N items” feedback

## UX Spec

### Entry points
- Metrics/Browse page:
  - Keep the “Filters” button.
  - Clicking opens a **Filters drawer/panel** (or modal—match your product’s pattern).
- Smart Folder Create/Edit:
  - Use the same FilterBuilder component inside the dialog.

### Layout (builder)
1) Header row:
   - Match mode: `All conditions` / `Any condition` (i18n labels)
   - Actions: `Reset`, `Close` (and in dialogs: `Create/Save`)

2) Condition groups:
   - Default: a single group, match mode set by header.
   - Advanced: allow “Add group” → groups combine with **AND** (like image 3’s “且”).
   - Each group can optionally override match mode (Any/All), if we want parity with Finder-style “nested logic”.

3) Each condition row (3-column grid):
   - **Field** dropdown (Stars, Filename, Comments, URL, Date Added, Width, Height, File Size, Metrics…)
   - **Operator** dropdown (contextual to field)
   - **Value editor** (contextual: text input, number input, date picker, multiselect, range)
   - Row actions: remove (–), duplicate (optional), add (+) (optional; can also be global)

4) Footer feedback:
   - “Found N items” (debounced), plus a subtle spinner while recomputing.

### Interaction details (important for “feels clean”)
- Empty state:
  - Show a single CTA: `Add condition`
  - Optionally show 3–5 quick presets (Stars, Filename, Date, Width, Metric)

- Adding:
  - `Add condition` opens a searchable list of fields (categories: Attributes, Dimensions, Date, Metrics)
  - When a field is chosen, operator defaults intelligently (e.g., text → “contains”, number → “>=”, date → “between”)

- Editing:
  - Changes apply immediately (debounced) to match current behavior.
  - Invalid/empty value states do not create “active” filters (but remain editable).

- Removing:
  - Removing a row removes that clause from FilterAST.
  - Removing a group deletes it; if the last group is removed, builder returns to empty state.

- Compact summary (outside builder):
  - Active filters appear as chips (e.g., `Name contains "draft"`, `Width ≥ 2048`)
  - Chips are removable without opening the builder (optional but nice).

## Data Model & Serialization

### Goal
Represent the builder structure (Any/All + groups) in a stable, serializable AST that round-trips with UI and persists in Smart Folders.

### Proposed FilterAST shape
- Leaf clauses: keep your existing clause union (stars, text contains, date range, width compare, metric range, etc.).
- Add expression nodes:

- `FilterExpr`:
  - `{ all: FilterNode[] }`  // AND
  - `{ any: FilterNode[] }`  // OR
- `FilterNode = FilterExpr | FilterClause`

Notes:
- This mirrors the UI cleanly (group = expr node).
- Back-compat: existing saved filters that are “flat AND of clauses” become `{ all: [clauses...] }`.

### Normalization rules (to avoid junk state)
- Drop empty strings, empty arrays, and incomplete ranges from *active* evaluation.
- Keep incomplete rows in UI state but exclude them from `countActiveFilters` and matching.
- Collapse single-child groups on save (optional), or keep as-is for UI stability.

### Mapping UI ↔ AST
- UI builder state is basically the AST with some UI metadata (row ids for React keys).
- Persist only the AST; UI ids are ephemeral.

## Component Architecture

### New modules (suggested)
- `frontend/src/features/filters/FilterBuilder/`
  - `FilterBuilder.tsx` (top-level)
  - `FilterGroup.tsx`
  - `FilterRow.tsx`
  - `FieldRegistry.ts` (field definitions)
  - `ValueEditors/` (TextEditor, NumberEditor, DateRangeEditor, StarsEditor, MetricEditor)

### Field Registry (key to keeping code sane)
Each field declares:
- id, label, category
- allowed operators + label
- value editor type + validation
- clause encode/decode:
  - `toClause(field, op, value) -> FilterClause | null`
  - `fromClause(clause) -> { field, op, value } | null`

This avoids a giant switch statement across the UI and makes adding fields cheap.

### Metrics as a special field
Metrics are “dynamic keys”.
- Field: `Metric`
- Value editor becomes: `Metric key picker (searchable) + operator + value`
- Clause shape example:
  - `{ metricCompare: { key: string; op: '<'|...; value: number } }`
  - `{ metricRange: { key: string; min?: number; max?: number } }`

## Plan of Work

### Milestone 1: UX + AST agreement
Goal: Lock semantics so UI and persistence don’t drift.

Work:
1) Confirm required logic:
   - Phase 1: single group + Any/All (minimum for image 2)
   - Phase 2: multiple groups ANDed (image 3)
2) Define FilterExpr nodes (`all` / `any`) in shared types.
3) Write normalization + “active filter count” rules.

Acceptance:
- AST supports the UI without hacks.
- Existing saved filters still load and behave the same.

### Milestone 2: Build the FilterBuilder component (isolated)
Goal: A working builder storybook/dev page with local state.

Work:
1) Implement FieldRegistry for current supported filters.
2) Implement rows, operator switching, contextual value editors.
3) Implement add/remove condition, add/remove group.
4) Implement “Found N items” hook (pluggable callback).

Acceptance:
- Builder can construct/edit AST reliably.
- Empty/incomplete conditions don’t count as active.

### Milestone 3: Integrate into metrics/browse page
Goal: Replace cluttered sidebar with builder + chips.

Work:
1) Add “Active filters” chips summary in the collapsed view.
2) Replace legacy sections with FilterBuilder drawer/panel.
3) Wire into ViewState (same persistence pipeline).

Acceptance:
- Metrics page no longer lists every filter control by default.
- All filtering capabilities remain accessible via Add condition.

### Milestone 4: Smart Folder create/edit uses the same builder
Goal: One filter editor everywhere.

Work:
1) Embed FilterBuilder in Smart Folder dialog.
2) Ensure Save/Create persists AST.
3) Ensure reload rehydrates UI cleanly.

Acceptance:
- Smart Folders round-trip with no semantic change.

### Milestone 5: Tests
Goal: Prevent regressions and “UI builds wrong AST” bugs.

Work:
1) Unit tests:
   - clause ↔ row mapping (registry encode/decode)
   - AST normalization rules
   - matches() evaluation for all/all + any/any + grouped AND
2) UI tests (lightweight):
   - add condition → appears
   - remove → disappears
   - switching field updates operator/value editors
3) Integration test:
   - load old flat filters → builder shows equivalent single group.

Acceptance:
- Core transformations + evaluation covered.
- Back-compat verified.

## Validation and Acceptance

- Filters UI defaults to minimal/clean state.
- Users can add/remove conditions without scrolling through unused controls.
- Any/All semantics are explicit and correct.
- Optional grouping (AND between groups) matches desired design.
- Existing saved filters still work.
- Smart Folders persist and reload the full filter structure.
- Active filter count and chips reflect only meaningful criteria.

## Idempotence and Recovery

- Unknown clause types are ignored (and surfaced as a non-blocking “Some filters couldn’t be loaded” toast if you want).
- Malformed AST normalizes to empty safely.
- Incomplete rows never crash evaluation; they simply don’t match/apply.

## Future Expansion Guardrails (Do / Don’t)

Do:
- Keep filters declarative via FieldRegistry.
- Keep AST as the single source of truth (no hidden UI-only filter semantics).
- Keep “Add condition” searchable and categorized.

Don’t:
- Don’t add a second “advanced filter system”.
- Don’t silently change match semantics during the UI refactor.
- Don’t bake field-specific logic into the builder—push it into the registry.

---

Change note (required for living plans): This plan refactors the filters UX from an always-visible list of all controls into an additive condition-builder UI, preserving existing filter semantics and Smart Folder persistence.
