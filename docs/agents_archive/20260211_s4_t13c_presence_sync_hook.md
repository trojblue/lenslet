# S4 T13c - AppShell Presence/Sync Domain Hook

## Goal

Extract AppShell presence/sync lifecycle ownership into a dedicated hook while preserving behavior for:

- presence scope join/move/leave lifecycle,
- event stream subscription and connection-status handling,
- sync activity derivation (recent highlights/touches/off-view summary), and
- toolbar/status indicator parity.

## Implementation

- Added `frontend/src/app/hooks/useAppPresenceSync.ts`.
  - Owns presence refs/state (`lease`, active scope, pending scope, coalesce timers).
  - Owns lifecycle transitions (`joinPresenceScope`, `movePresenceScope`, reconnect/pagehide/pageshow handling, heartbeat refresh).
  - Owns event subscriptions via `connectEvents` + `subscribeEvents` + `subscribeEventStatus` and applies item/metric sync updates.
  - Owns activity derivation via `usePresenceActivity`, plus derived `offViewSummary`, `recentTouchesDisplay`, and edit-recency labels.
  - Owns persistence health probe (`api.getHealth`) for read-only banner state.

- Rewired `frontend/src/app/AppShell.tsx` to consume hook outputs:
  - `connectionStatus`, `connectionLabel`, `presence`, `editingCount`, `recentEditActive`, `hasEdits`, `lastEditedLabel`, `persistenceEnabled`.
  - `highlightedPaths`, `onVisiblePathsChange`, `offViewSummary`, `recentTouchesDisplay`, `clearOffViewActivity`.
- Removed inlined presence/sync orchestration from `AppShell` and updated seam-anchor comment for `T13c`.
- `AppShell.tsx` line count moved from `2020` to `1664`.

## Validation

Run from `frontend/`:

- `npm run test -- src/app/__tests__/appShellHelpers.test.ts src/app/__tests__/presenceActivity.test.ts src/app/__tests__/presenceUi.test.ts src/features/browse/model/__tests__/filters.test.ts src/features/browse/model/__tests__/pagedFolder.test.ts src/features/browse/model/__tests__/prefetchPolicy.test.ts src/api/__tests__/client.events.test.ts src/api/__tests__/client.presence.test.ts src/api/__tests__/client.exportComparison.test.ts`
  - Result: `39 passed`.
- `npm run build`
  - Result: success.
- `npx tsc --noEmit`
  - Result: known pre-existing failures remain in:
    - `src/api/__tests__/client.presence.test.ts`
    - `src/app/AppShell.tsx`
    - `src/app/components/StatusBar.tsx`
    - `src/features/inspector/Inspector.tsx`

## Notes

- No API or payload contract changes.
- Presence/sync behavior remains best-effort and non-blocking on lifecycle failures.
