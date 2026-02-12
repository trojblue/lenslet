# Compare Mode for Selected Images


## Purpose / Big Picture


This plan adds a compare workspace that lets a user select two or more images in the existing gallery, click a new Compare tool in the left sidebar, and open a modal overlay that shows a split A/B view with a draggable divider and synchronized pan/zoom. The compare overlay behaves like fullscreen viewer navigation, except left/right (or A/D) moves within only the selected images. Success is visible when a user can select multiple images, open Compare, see filenames for A and B, drag the split handle, zoom/pan both images in sync, and step through the selected subset without leaving the compare overlay.


## Progress


- [x] 2026-01-26: Reviewed frontend layout and state flow in `frontend/src/app/AppShell.tsx`, viewer logic in `frontend/src/features/viewer/Viewer.tsx`, selection behavior in `frontend/src/features/browse/components/VirtualGrid.tsx`, and sidebar tool switcher in `frontend/src/app/components/LeftSidebar.tsx`.
- [x] 2026-01-26: Clarified compare UX requirements (left sidebar tool, modal overlay, split slider, sync pan/zoom, navigation limited to selected images).
- [ ] 2026-01-26: Implement compare mode and validate UI flows.


## Surprises & Discoveries


Selection order in `VirtualGrid` is insertion-ordered (Set-based) for ctrl/meta toggles, so compare navigation should normalize to the current `items` order to match the visible sort rather than user click order.


## Decision Log


2026-01-26 (user + assistant): Add a third left sidebar tool for Compare, alongside Folders and Metrics, and use it to open a compare overlay rather than adding a separate compare gallery.

2026-01-26 (user + assistant): Compare overlay uses a split slider (draggable divider) with synchronized zoom/pan and filename labels for both images.

2026-01-26 (assistant): Compare navigation (left/right, A/D) advances through only the selected images in current grid order; A/B are adjacent items in that ordered subset.

2026-01-26 (assistant): Compare opens as a modal overlay similar to the existing fullscreen viewer, with its own close control and Escape handling; background shortcuts are disabled while compare is open, and opening compare closes any active viewer to avoid stacked overlays.

2026-01-26 (assistant): Compare should not replace the active left panel (folders/metrics). Provide a Compare action button in the left sidebar (or next to the tool buttons) that opens the overlay without changing `leftTool`.

2026-01-26 (assistant): Compare history behavior should mirror Viewer: optional `pushState` on open and `popstate` closes compare; opening compare closes viewer without calling `history.back()` to avoid popping unrelated history.


## Outcomes & Retrospective


No outcomes yet. The intended outcome is a compare overlay that is usable without changing existing selection behavior or requiring a separate compare gallery.


## Context and Orientation


No `PLANS.md` or `plan.md` exists in the repo.

The main app state lives in `frontend/src/app/AppShell.tsx`, which already manages selection, viewer overlay, and left/right navigation for fullscreen. The left sidebar tool switcher is in `frontend/src/app/components/LeftSidebar.tsx`, which currently supports `folders` and `metrics`. The viewer overlay is in `frontend/src/features/viewer/Viewer.tsx`, with zoom/pan implemented in `frontend/src/features/viewer/hooks/useZoomPan.ts`. The grid selection logic and ordering are in `frontend/src/features/browse/components/VirtualGrid.tsx`. Compare mode should reuse `api.getFile` and `useBlobUrl` for image loading and should avoid modifying selection mechanics.


## Plan of Work


First, add a Compare action button in the left sidebar (adjacent to the tool buttons) and wire AppShell state to open/close a compare overlay while preventing conflicts with the existing viewer. Next, derive a stable compare list from the current `items` array and `selectedPaths`, clamp the compare index so `B` always exists, and implement navigation that advances within that subset while suppressing background shortcuts. Then implement the compare overlay UI with a split slider, synchronized pan/zoom, and filename labels. Finally, add styles and guardrails for the divider handle, empty-state messaging, focus restoration on close, and prefetching of adjacent compare items.


### Sprint Plan


1) Sprint 1 — Compare scaffolding and navigation (Tasks C1–C3). Goal: open/close compare overlay from the sidebar, derive ordered selected subset, and navigate within that subset with proper focus and key handling. Demo outcome: select 2+ images, click Compare, overlay opens with filenames and Prev/Next controls limited to selected images; Escape closes and focus returns to the grid.

2) Sprint 2 — Split slider and synced pan/zoom (Tasks C4–C6). Goal: render A/B split view with draggable divider and synchronized zoom/pan, plus polish for empty state and divider affordances. Demo outcome: drag the divider, zoom/pan both images in sync, and step through the selected subset while the overlay updates.


## Concrete Steps


From the repo root:

    cd /home/ubuntu/dev/lenslet


### Task/Ticket Details


1) C1 — Add Compare action entry (non-panel). Goal: expose Compare as an action button in the left sidebar (without replacing the folders/metrics panel state) and provide an affordance to open the compare overlay. Affected files/areas: `frontend/src/app/components/LeftSidebar.tsx`, `frontend/src/app/AppShell.tsx`. Validation: run the UI and confirm Compare is visible and opens the overlay without changing the active panel.

2) C2 — Compare state + selection subset. Goal: add compare overlay state and derive a stable ordered subset of selected items (based on `items` order), clamp the compare index to `[0, compareItems.length - 2]` so `B` always exists, and define nav step size (recommended: step by 1). Ensure compare opening closes the fullscreen viewer if active, does not call `history.back()`, optionally pushes its own history state, and that background shortcuts are suppressed while compare is open. Affected files/areas: `frontend/src/app/AppShell.tsx`. Validation: with 3+ selected images, confirm navigation steps through only the selected subset and never opens the fullscreen viewer or triggers global shortcuts while compare is open.

3) C3 — Compare overlay skeleton + accessibility. Goal: create a new compare overlay component with header, filename labels for A/B, close button, aria-modal/role attributes, and key handling (Esc to close, A/D or arrows to navigate). Restore focus to the last focused grid cell on close. Consider whether the main toolbar should enter a “compare-active” state (zoom slider + back button) or remain in grid mode. Affected files/areas: `frontend/src/features/compare/CompareViewer.tsx` (new), `frontend/src/app/AppShell.tsx`, optionally `frontend/src/shared/ui/Toolbar.tsx`. Validation: open compare overlay and verify close, focus restoration, and navigation without rendering image content yet.

4) C4 — Split slider rendering. Goal: implement a split A/B view with a draggable divider, a generous hit area, and cursor feedback. Affected files/areas: `frontend/src/features/compare/CompareViewer.tsx`, `frontend/src/styles.css` (or a dedicated compare CSS module if preferred). Validation: drag the divider and confirm it adjusts the visible portion of the B image without affecting layout.

5) C5 — Synced pan/zoom. Goal: add a compare zoom/pan hook that applies a shared `scale/tx/ty` to both images and fits both to the viewport on load. Decide whether to use a shared base (min of both image fit scales) or per-image base with a shared scale multiplier so sync feels consistent even with differing aspect ratios. Affected files/areas: `frontend/src/features/compare/hooks/useCompareZoomPan.ts` (new) or inline logic in compare component. Validation: wheel zoom and drag pan on either image and confirm both layers move together without “jump” on load/resize.

6) C6 — Polish + guardrails. Goal: add empty-state messaging when fewer than two images are selected, ensure compare closes if selection drops below two, add a generous divider hit area with pointer-capture so dragging doesn’t trigger pan, and prefetch adjacent compare images for smooth navigation. Affected files/areas: `frontend/src/app/AppShell.tsx`, `frontend/src/features/compare/CompareViewer.tsx`. Validation: deselect down to one image and verify compare closes or shows the empty state; drag the divider without panning; navigate and observe prefetch behavior (network panel or timing).


## Validation and Acceptance


Sprint 1 validation focuses on state flow and navigation. Acceptance: selecting 2+ images and clicking Compare opens the overlay; the overlay shows filenames for A/B; left/right or A/D navigates only within the selected subset; Escape closes compare and returns focus to the grid; background shortcuts do not fire while compare is open.

Sprint 2 validation focuses on visual compare behavior. Acceptance: the split slider divider moves with drag; both images zoom and pan in sync; filenames remain accurate as navigation advances; compare overlay is visually aligned with the existing viewer presentation (toolbar offset, full viewport coverage below the toolbar).

Overall acceptance: compare mode does not alter selection behavior, does not allow navigation outside the selected subset, and does not require a separate compare gallery. No server behavior changes occur.


## Idempotence and Recovery


All compare changes are additive and local to the frontend. If compare UI regressions occur, revert by removing the new compare component and sidebar tool, and restore AppShell state to its previous shape. Rerunning the UI is safe because compare state is ephemeral and derived from existing selection data.


## Artifacts and Notes


Proposed selection normalization (ordered by current grid):

    const compareItems = useMemo(
      () => items.filter((it) => selectedSet.has(it.path)),
      [items, selectedSet]
    )

Proposed A/B mapping from the ordered subset:

    const aItem = compareItems[compareIndex] ?? null
    const bItem = compareItems[compareIndex + 1] ?? null


## Interfaces and Dependencies


Compare uses existing frontend APIs and hooks: `api.getFile`, `api.prefetchFile`, and `useBlobUrl`. No new backend endpoints are required. The compare overlay component should accept the ordered compare list, current index, and callbacks for navigation and close. The zoom/pan logic can be modeled after `frontend/src/features/viewer/hooks/useZoomPan.ts`, but must apply shared transforms to both images.
