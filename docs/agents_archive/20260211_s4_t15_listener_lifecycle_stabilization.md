# S4 T15 - AppShell Listener Lifecycle Stabilization

## Scope

Ticket: `S4 / T15`  
Objective: reduce avoidable AppShell effect churn without changing behavior.

## Changes

1. Added `frontend/src/shared/hooks/useLatestRef.ts` to provide stable refs that always point at latest state/callback values.
2. Updated `frontend/src/app/AppShell.tsx` to stabilize listener lifecycles:
   - Hash sync listener now reads latest selection/hash callbacks from refs instead of remounting the listener when callback identities change.
   - Global keyboard listener now reads current state via a ref snapshot and stays mounted across routine scope/selection/viewer changes.
   - Pinch-resize listener now reads the latest grid size from a ref, so thumb-size changes no longer cause touch listener teardown/rebind.

## Behavioral Parity Notes

- No route/API/state contract changes.
- Keyboard shortcuts, hash sync behavior, and pinch resize semantics are unchanged; only listener ownership and stale-closure handling changed.

## Churn Reduction Evidence

- `hashchange` listener effect moved from callback-identity dependencies to stable ref dependencies.
- Global `keydown` listener effect moved from mutable state dependencies (`current`, `items`, `selectedPaths`, `viewer`, `compareOpen`, `mobileSelectMode`, `openFolder`) to a stable ref dependency.
- Pinch listener effect removed direct `gridItemSize` dependency; slider/pinch updates now reuse a mounted listener.

These shifts eliminate repeated listener attach/remove cycles during common UI interactions (selection changes, viewer open/close transitions, and continuous pinch/size updates).

## Validation

- `cd frontend && npm run test -- src/app/__tests__/appShellHelpers.test.ts src/app/__tests__/appShellSelectors.test.ts src/app/__tests__/presenceActivity.test.ts src/app/__tests__/presenceUi.test.ts src/features/browse/model/__tests__/filters.test.ts src/features/browse/model/__tests__/pagedFolder.test.ts src/features/browse/model/__tests__/prefetchPolicy.test.ts src/api/__tests__/client.events.test.ts src/api/__tests__/client.presence.test.ts src/api/__tests__/client.exportComparison.test.ts` -> `45 passed`.
- `cd frontend && npm run build` -> success.
- `cd frontend && npx tsc --noEmit` -> fails with known pre-existing repo errors in:
  - `src/api/__tests__/client.presence.test.ts`
  - `src/app/AppShell.tsx` (`visualViewport` typing)
  - `src/app/components/StatusBar.tsx`
  - `src/features/inspector/Inspector.tsx`
