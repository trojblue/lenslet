# Sync Indicator Toolbar Consolidation Plan


## Purpose / Big Picture


After this work, Lenslet will show a compact sync/presence indicator in the main top toolbar so the UI no longer needs a dedicated status row. The indicator will present a colored dot with the viewing count (or a dash when unknown), and on hover it will show quick presence text. Clicking the indicator will open a small status card (similar to Google Docs) with sync status, connection status, presence, and “last edited” time; the card closes on outside click or Escape and restores focus to the trigger. The existing StatusBar remains for banners (zoom warning, recent updates, persistence), but the old “All changes saved / Live / X viewing” pill row is removed. Users can visually confirm state changes (live, unstable, recent edit flash, editing, offline/connecting) and quickly verify it works by editing a tag/notes field and watching the dot color and card contents update.


## Progress


- [ ] 2026-01-24: Confirmed current sync/presence behavior and gathered UX requirements.
- [ ] 2026-01-24: Draft plan and review notes.
- [ ] 2026-01-24: Implement toolbar indicator, remove status pills, and validate UI behavior.


## Surprises & Discoveries


No surprises yet. Syncing is client-side inflight writes, and “editing” is TTL-based (edit within ~60s).


## Decision Log


- 2026-01-24 (assistant + user): Place the compact indicator in the main toolbar, always visible (grid + viewer). On mobile, show only the dot; the count appears in the expanded card.
- 2026-01-24 (assistant + user): Dot color precedence is Offline/Connecting (grey) > Lag/Unstable (yellow) > Recent Edit (purple) > Editing (blue) > Live (green).
- 2026-01-24 (assistant + user): Yellow “unstable” triggers on reconnecting, polling fallback, sync error (conflicts or save failures), or any inflight edit older than 10 seconds.
- 2026-01-24 (assistant + user): Purple “recent edit” flash duration should match the gallery highlight timeout (currently 6000ms) and be centralized for reuse.
- 2026-01-24 (assistant + user): “Last edited” uses server timestamps from item/metrics update events; if none exist, display “No edits yet.” Use relative time for <24 hours, absolute date/time otherwise.
- 2026-01-24 (assistant): `connectionStatus` values `idle`/`connecting` map to the grey state to avoid misrepresenting live connectivity.


## Outcomes & Retrospective


Target outcome is a single, compact status indicator in the toolbar that replaces the old sync row while preserving visibility of important system states. Retrospective will note whether long-sync detection accurately reflects “stuck” edits without flagging normal short bursts.


## Context and Orientation


No PLANS.md was found in the repository, so this plan is self-contained.

Relevant files and concepts:

- `frontend/src/shared/ui/Toolbar.tsx` renders the main toolbar and is the insertion point for the compact indicator and card. It already tracks `isNarrow` for responsive behavior.
- `frontend/src/app/AppShell.tsx` derives sync status, connection status, presence, and handles event streams; it will provide data to the toolbar.
- `frontend/src/app/components/StatusBar.tsx` contains the current sync/presence pill row that must be removed while keeping banners (zoom warning, persistence, recent updates).
- `frontend/src/api/items.ts` owns sync status and inflight tracking; it will expose long-sync age for yellow state.
- `frontend/src/api/polling.ts` + `frontend/src/api/client.ts` expose fallback polling and connection status.
- `frontend/src/styles.css` and `frontend/src/theme.css` provide theme tokens and component styling.

Terminology:

- “Syncing” = client-side writes in flight (pending/inflight patches).
- “Editing” = someone has edited within the last ~60 seconds (presence TTL).
- “Recent edit flash” = temporary purple state triggered by server item/metrics update events.


## Plan of Work


The implementation will add a compact indicator and click-to-open status card in the toolbar, replace the current StatusBar sync/presence row, and introduce a reliable long-sync detection mechanism. The indicator’s visual state is derived from connection status, sync status, presence data, polling fallback, recent edit events, and long-sync age. A small UI component will handle hover title and click popover behavior, and AppShell will supply computed values and timestamps while reusing the toolbar’s existing responsive layout logic.

Sprint Plan:

1) Sprint 1 — Toolbar indicator + status card skeleton. Goal: render the compact dot+count in the toolbar, show hover text, open/close the status card on click, and remove the old sync row. Demo: top toolbar shows the indicator with a placeholder card; StatusBar shows only banners.
2) Sprint 2 — State logic + long-sync detection + last edited time. Goal: correct dot color precedence, long-sync detection, and last-edited formatting; verify with simulated edits and connection changes. Demo: dot and card reflect live/offline/reconnecting/polling/error/recent-edit/editing states, with correct time formatting.


## Concrete Steps


Commands (run from repo root):

  cd /home/ubuntu/dev/lenslet
  npm --prefix frontend run dev

Task/Ticket Details:

T1: Remove StatusBar sync/presence pills while preserving banners.
- Goal: Delete the bottom “All changes saved / Live / viewing” pill row from `frontend/src/app/components/StatusBar.tsx` and stop passing `syncTone`, `syncLabel`, `connectionTone`, `connectionLabel`, and `presence` props from `frontend/src/app/AppShell.tsx`.
- Affected files: `frontend/src/app/components/StatusBar.tsx`, `frontend/src/app/AppShell.tsx`.
- Validation: The StatusBar only shows zoom warnings, persistence banner, and recent updates. No sync row remains.

T2: Add indicator render + placement in the toolbar.
- Goal: Insert a compact indicator in `frontend/src/shared/ui/Toolbar.tsx` (or a new `frontend/src/shared/ui/SyncIndicator.tsx`), positioned to avoid collisions with search/nav and respecting existing `isNarrow` behavior. Desktop shows `● N`; mobile shows only `●`.
- Affected files: `frontend/src/shared/ui/Toolbar.tsx` (plus optional new component file), `frontend/src/styles.css` for layout classes.
- Validation: Indicator appears in grid and viewer modes; on mobile it shows only the dot; layout stays stable when the count changes.

T3: Implement indicator interactions (hover + click card + accessibility).
- Goal: Provide hover text via `title` (“X viewing · Y editing”), and a click-to-open card below the indicator. The trigger must be a real button with `aria-haspopup`, `aria-expanded`, and focus restored on close; close on outside click and Escape; toggle on re-click.
- Affected files: `frontend/src/shared/ui/Toolbar.tsx` or `frontend/src/shared/ui/SyncIndicator.tsx`.
- Validation: Hover shows presence text; click opens a card; outside click/Escape closes it; keyboard users can focus the button and close the card.

T4: Wire toolbar indicator props from AppShell.
- Goal: Compute and pass the data required by the indicator: presence counts, sync state, connection status, polling fallback, last edited time, recent edit flash window, and viewing count (or “—” when missing).
- Affected files: `frontend/src/app/AppShell.tsx`, `frontend/src/shared/ui/Toolbar.tsx`.
- Validation: Indicator shows “● —” if presence is missing; shows “● N” once presence arrives; hover text updates with presence changes.

T5: Implement long-sync detection in items API.
- Goal: Track the age of inflight edits and expose the oldest inflight age so the UI can mark “unstable” if any inflight edit exceeds 10 seconds. Track start times for queue-based updates (per-path) and direct inflight updates; clear when done.
- Affected files: `frontend/src/api/items.ts` (add tracking map and exported getter or hook), `frontend/src/app/AppShell.tsx` (consume it).
- Validation: Simulate a stalled patch (network throttle or forced delay) and confirm the indicator turns yellow after 10s while still syncing; normal quick edits do not trigger yellow.

T6: Centralize “recent edit flash” duration and reuse for purple state.
- Goal: Extract the existing highlight timeout (currently 6000ms in AppShell) into a shared constant (e.g., `frontend/src/lib/constants.ts`) used both for gallery highlights and indicator purple duration.
- Affected files: `frontend/src/app/AppShell.tsx`, optional `frontend/src/lib/constants.ts`.
- Validation: Gallery highlight and purple indicator share the same duration.

T7: Define dot color precedence and compute indicator state.
- Goal: Implement precedence: Offline/Connecting (grey) > Lag/Unstable (yellow) > Recent Edit (purple) > Editing (blue) > Live (green). Define “Lag/Unstable” as reconnecting OR polling fallback OR sync error OR oldest inflight edit age > 10s. Define “Recent Edit” as last edit within flash duration. Define “Editing” as `presence.editing > 0`, and hold blue for up to 15 minutes after the last edit to prevent immediate green if no active editors.
- Affected files: `frontend/src/app/AppShell.tsx` or a new helper module (pure function).
- Validation: Trigger each state and verify the dot color changes with correct precedence. Confirm it returns to green after 15 minutes of no edits.

T8: Implement “Last edited” formatting and card copy.
- Goal: Use server `updated_at` timestamps from `item-updated` and `metrics-updated` events to set `lastEditedAt`, with fallback to receipt time if missing/invalid. Display relative time for <24 hours (seconds/minutes/hours) and absolute time for older (e.g., “Jan 12, 2026, 2:14 PM”). Show “No edits yet.” if no edits have occurred. Define card copy for sync/connection/error states so removing the StatusBar pills does not remove context.
- Affected files: `frontend/src/app/AppShell.tsx`, `frontend/src/lib/util.ts` (add formatter helpers), `frontend/src/shared/ui/Toolbar.tsx` (card display).
- Validation: Fresh edits show “seconds/minutes ago.” After 24 hours, card shows formatted date/time; before any edits, card shows “No edits yet.” Sync/connection labels appear in the card.

T9: Add styles and tokens for indicator + card.
- Goal: Introduce CSS classes for the dot colors (grey/yellow/purple/blue/green) and card layout (padding, border, shadow, z-index) using existing theme variables; ensure the card appears above the toolbar and does not clip on narrow screens.
- Affected files: `frontend/src/styles.css`, optionally `frontend/src/theme.css`.
- Validation: Card is readable, visually consistent, and not clipped on narrow viewports.


## Validation and Acceptance


Sprint 1 acceptance:

- The StatusBar no longer shows the three-pill sync row.
- The toolbar displays a compact indicator in both grid and viewer modes.
- Hover shows “X viewing · Y editing.”
- Click opens a small card below the indicator, and outside click/Escape closes it; focus returns to the trigger.

Sprint 2 acceptance:

- Dot color precedence follows Offline/Connecting > Unstable > Recent Edit > Editing > Live.
- Yellow triggers on reconnecting, polling fallback, sync error, or inflight edits > 10s.
- Purple flashes for the same duration as the gallery highlight.
- After 15 minutes of no edits, the dot returns to green.
- “Last edited” shows relative time for <24 hours and full date/time afterward; “No edits yet.” appears before any edit event.

Manual verification steps:

- Open the app and confirm the dot shows grey `● —` before presence arrives.
- Make a tag/note edit and verify purple flash, then blue while `editing > 0`, and green after 15 minutes without edits.
- Disconnect the network and confirm grey (offline). Trigger reconnecting to confirm yellow.
- Simulate a long inflight edit (network throttling) and confirm yellow after 10 seconds.
- Confirm card copy reflects “All changes saved / Syncing… / Not saved — …” and “Live / Reconnecting… / Offline”.


## Idempotence and Recovery


All changes are additive or localized to UI components and helper functions. Re-running the steps is safe. If needed, revert by removing the SyncIndicator component, restoring the StatusBar pill row props, and deleting the inflight age tracking logic; no data migrations are required.


## Artifacts and Notes


Planned indicator rendering (conceptual):

  [ ● 3 ]

Hover title:

  3 viewing · 1 editing

Expanded card (conceptual):

  All changes saved
  Live
  3 viewing · 1 editing
  Last edited: 5 minutes ago


## Interfaces and Dependencies


- Toolbar indicator props (example):
  - `presence?: { viewing: number; editing: number }`
  - `connectionStatus: ConnectionStatus`
  - `syncStatus: SyncStatus`
  - `pollingEnabled: boolean`
  - `lastEditedAt?: string | null`
  - `recentEditActive: boolean`
  - `longSyncMs?: number | null`

- New helper exports (example):
  - `getOldestInflightAgeMs()` or `useOldestInflightAgeMs()` from `frontend/src/api/items.ts`.
  - `formatRelativeTime(ts)` and `formatAbsoluteTime(ts)` in `frontend/src/lib/util.ts`.

Dependencies remain within existing frontend modules; no new external libraries are required.


Change note: Updated plan after subagent review to split tasks, add accessibility/responsiveness, clarify connection status mapping, and add card copy/styling requirements.
