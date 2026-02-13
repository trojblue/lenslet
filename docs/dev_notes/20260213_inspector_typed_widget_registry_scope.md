# Inspector Typed Widget Registry Scope (Lean Refactor)

## Context

Inspector widget composition is currently hard-coded in JSX:

- `frontend/src/features/inspector/Inspector.tsx` always mounts `OverviewSection`, and mounts compare-only widgets with direct conditions (for example `compareActive && compareReady` for `CompareMetadataSection`).
- `frontend/src/features/inspector/sections/OverviewSection.tsx` explicitly composes multi-select widgets (`SelectionActionsSection`, `SelectionExportSection`) with inline conditions.
- In compare mode, export actions were intentionally removed from the old explicit action path in `frontend/src/features/inspector/sections/SelectionActionsSection.tsx`.

This behavior is intentional and currently correct. The issue is maintainability and growth pressure from more hard-coded composition branches.

## Decision

Adopt a **typed, compile-time widget registry** for Inspector composition.

This is a structural refactor only: preserve behavior and keep runtime semantics unchanged.

## Why This Balance

We want to remove hard-coded mounting logic without ballooning line count or introducing framework-level indirection.

This approach gives:

- One place to define widget order and visibility policy.
- Strong typing for widget ids and context.
- No plugin runtime, no cross-module registration complexity.
- Minimal churn to existing section components and hooks.

## Goals (Do)

1. Replace top-level hard-coded section mounting in `Inspector.tsx` with a typed registry map/filter/render pass.
2. Replace hard-coded multi-widget composition in `OverviewSection.tsx` with a small typed local registry for overview child widgets.
3. Keep existing section components (`OverviewSection`, `CompareMetadataSection`, `BasicsSection`, `MetadataSection`, `NotesSection`) and existing hooks intact.
4. Keep existing visibility semantics exactly the same.
5. Keep the implementation small and readable (target: no large framework layer).

## Non-Goals (Do Not)

1. No runtime/plugin registration API.
2. No lazy loading or bundle-splitting changes in this refactor.
3. No fetch lifecycle changes (for example compare metadata request timing).
4. No user-customizable widget ordering/persistence.
5. No broad localStorage migration work.

## Proposed Shape

### A. Top-level Inspector registry

Create a typed registry module (for example `frontend/src/features/inspector/inspectorWidgets.tsx`) with:

- `InspectorWidgetId` union.
- `InspectorWidgetContext` type containing only fields needed for visibility/render.
- `InspectorWidgetDefinition`:
  - `id`
  - `isVisible(ctx): boolean`
  - `render(ctx): JSX.Element`

`Inspector.tsx` becomes:

- Build `ctx` from existing local values/callbacks.
- Render `INSPECTOR_WIDGETS.filter(...).map(...)`.

### B. Overview local widget registry

Inside `OverviewSection.tsx` (or a sibling module), add a small typed array for multi-select child widgets:

- `SelectionActionsSection`
- `SelectionExportSection`

Keep current conditions unchanged (`SelectionExportSection` only when `!compareActive`, etc.).

## Guardrails To Prevent Line-Count Bloat

1. Keep exactly one thin registry type and one definition list per level (top-level and overview-level).
2. Do not introduce generic abstractions beyond current use case.
3. Reuse existing prop bundles/callbacks; avoid new wrapper components unless needed for typing.
4. Prefer explicit typed context fields over deep object plumbing.
5. Keep comments minimal and only where intent is non-obvious.

## Performance Expectation

Neutral for page-load performance.

- Registry-based rendering alone does not reduce shipped JS.
- This refactor should not regress runtime behavior; cost is expected to be negligible versus current conditional JSX.

## Acceptance Criteria

1. Inspector renders the same widget set for all current modes:
   - single selection
   - multi selection
   - compare active/not active
   - compare ready/not ready
2. `SelectionExportSection` remains absent in compare mode.
3. `CompareMetadataSection` remains mounted only when compare is active and ready.
4. Existing tests continue passing; add focused tests only if needed to lock visibility behavior.
5. Net complexity remains bounded (no new runtime architecture layers).

## Follow-Up (Explicitly Deferred)

If we later need startup gains, do a separate change for lazy-loading heavy widgets. That work is intentionally decoupled from this structural refactor.
