# 2026-03-04 UI Jitter Review

## Scope
Targeted UX review focused on layout jitter and attention breaks during:
- viewer/fullscreen transitions
- compare mode transitions
- inspector metadata autoload transitions

This document records findings and improvement areas only. No implementation is included in this session.

## Primary User-Reported Issue
In viewer mode, toolbar controls shift when `Back` appears and other controls are disabled/hidden. This causes re-targeting and visual fatigue.

## Findings (Ranked)

### 1) High: `Back` insertion shifts the left toolbar anchor
What happens:
- `Back` is mounted only when `viewerActive`, pushing adjacent controls.
- Sort/filters remain but change state, so the left cluster “shape” changes mid-flow.

Evidence:
- `frontend/src/shared/ui/Toolbar.tsx:248`
- `frontend/src/shared/ui/Toolbar.tsx:256`
- `frontend/src/app/AppShell.tsx:1203`

Improvement area:
- Keep a permanent back-button slot.
- Prefer hide/disable (`opacity` + `pointer-events`) over mount/unmount.
- Place `Back` to the right of sort/filter anchors to preserve spatial memory.

---

### 2) High: Right-side toolbar controls are replaced between browse/viewer states
What happens:
- Viewer nav appears only in viewer.
- Upload/search/refresh disappear in viewer.
- Horizontal control map changes significantly.

Evidence:
- `frontend/src/shared/ui/Toolbar.tsx:353`
- `frontend/src/shared/ui/Toolbar.tsx:407`
- `frontend/src/shared/ui/Toolbar.tsx:444`

Improvement area:
- Reserve fixed sub-slots for nav/search/upload/refresh.
- Keep layout stable; only toggle affordance/interaction state.

---

### 3) Medium: Compact viewer branch changes toolbar density abruptly
What happens:
- In compact conditions, labels/parts of toolbar are removed.
- Crossing viewport + mode boundaries causes extra re-scan cost.

Evidence:
- `frontend/src/shared/ui/Toolbar.tsx:192`
- `frontend/src/shared/ui/Toolbar.tsx:193`
- `frontend/src/styles.css:902`

Improvement area:
- Keep stable footprint in compact mode with icon-only disabled states, not removal.

---

### 4) Medium: Status/similarity/filter-chip bars mount/unmount above grid
What happens:
- Top stack appears/disappears.
- Grid viewport height changes, which reads as content jump.

Evidence:
- `frontend/src/app/components/StatusBar.tsx:49`
- `frontend/src/app/AppShell.tsx:1331`
- `frontend/src/app/AppShell.tsx:1354`

Improvement area:
- Use a persistent top-stack region with reserved height bands.
- Fade content in/out inside fixed bands instead of adding/removing bands.

---

### 5) Medium: Metric scrollbar mode changes effective grid width
What happens:
- Grid switches scrollbar strategy and right padding.
- This shifts grid content width when metric scrollbar toggles.

Evidence:
- `frontend/src/app/AppShell.tsx:1399`
- `frontend/src/features/browse/components/VirtualGrid.tsx:621`
- `frontend/src/features/browse/components/MetricScrollbar.tsx:90`

Improvement area:
- Keep a constant right gutter and consistent scrollbar policy across modes.

---

### 6) Medium: Mobile search row mount/unmount changes toolbar height and overlay offsets
What happens:
- Mobile search row is conditionally mounted.
- `--toolbar-h` is recalculated from actual height.
- Overlays using `toolbar-offset` can shift vertically.

Evidence:
- `frontend/src/shared/ui/Toolbar.tsx:457`
- `frontend/src/app/AppShell.tsx:781`
- `frontend/src/app/AppShell.tsx:787`
- `frontend/src/styles.css:209`

Improvement area:
- Keep a persistent search-row slot on narrow layouts.
- Hide via interaction/visibility states instead of mount/unmount.

---

### 7) Low: Dynamic text widths cause micro horizontal drift
What happens:
- Labels such as `Upload` vs `Uploading…`, `Select` vs `Done (n)`, and badge counts change width.
- Nearby controls nudge slightly.

Evidence:
- `frontend/src/shared/ui/Toolbar.tsx:200`
- `frontend/src/shared/ui/Toolbar.tsx:421`
- `frontend/src/shared/ui/toolbar/ToolbarFilterMenu.tsx:46`

Improvement area:
- Assign fixed/min widths for dynamic-label buttons.
- Keep badge container mounted with `visibility: hidden` when empty.

## Additional Improvement Proposal: Inspector Quick View Reservation (User Suggestion)

### Current behavior causing jitter
Selection change resets metadata state before autoload completes:
- `setMetaRaw(null)` and `setMetaState('idle')` on context change.
- Quick View visibility currently depends on metadata payload presence.
- Result: Quick View disappears, then appears again after metadata load.

Evidence:
- `frontend/src/features/inspector/hooks/useInspectorSingleMetadata.ts:40`
- `frontend/src/features/inspector/hooks/useInspectorSingleMetadata.ts:42`
- `frontend/src/features/inspector/hooks/useInspectorSingleMetadata.ts:44`
- `frontend/src/features/inspector/Inspector.tsx:303`
- `frontend/src/features/inspector/Inspector.tsx:306`

### Desired behavior (as proposed)
When autoload metadata is enabled:
- If previous image had Quick View: keep a temporary Quick View placeholder footprint while next image metadata is pending.
- If next image also has Quick View: hydrate in-place with minimal layout movement.
- If next image has no Quick View: remove placeholder after metadata resolves.
- If previous image had no Quick View: do not reserve space for next image until metadata confirms availability.

### Improvement area (design-level, no implementation yet)
- Add transient “pending quick view reservation” state in inspector rendering.
- Cache last confirmed Quick View footprint (row-count or measured height).
- Render placeholder skeleton/empty rows during pending state.
- Clear reservation only after metadata settles for the new selection.

## Additional Simplification Proposal: Remove Single-Image `Item` Section

This one is less about jitter and more about reducing cognitive grouping overhead in inspector.

### Current behavior
- In single-select mode, inspector renders an `Item` section containing only filename and `Find similar`.
- Filename is separated from the thumbnail by an additional vertical section boundary.
- `Find similar` is currently coupled to `OverviewSection` action area.

Evidence:
- `frontend/src/features/inspector/sections/OverviewSection.tsx:125`
- `frontend/src/features/inspector/sections/OverviewSection.tsx:131`
- `frontend/src/features/inspector/sections/OverviewSection.tsx:160`
- `frontend/src/features/inspector/Inspector.tsx:580`

### Proposed direction (plan-only)
- Remove `Item` section for single-select mode.
- Show filename directly under the inspector thumbnail block (same visual group).
- Move `Find similar` to:
  - `Basics` section button/action area, and
  - item right-click context menu for quick access.

Context-menu evidence (current item menu has no `Find similar` entry):
- `frontend/src/app/menu/AppContextMenuItems.tsx:244`

### Expected UX benefit
- Fewer section boundaries in single-image flow.
- Less vertical scrolling and less “which section is this in?” scanning.
- Better information grouping: preview + identity (filename) together.
- Action discoverability preserved via `Basics` + context menu.

### Notes / guardrails for future implementation
- Keep multi-select `Selection` section behavior intact (selection actions/export).
- Ensure `Find similar` disabled-reason text remains available somewhere visible when embeddings are unavailable.
- Validate keyboard and context-menu parity after relocation.

## Additional Micro UX Tweaks (Requested)

### A) Quick View: replace text `Copy` button with icon action
Current behavior:
- Each Quick View row uses a text `Copy` button (`Copy`/`Copied`) with `min-w-[64px]`.
- This consumes horizontal space that could be used for row value text.

Evidence:
- `frontend/src/features/inspector/sections/QuickViewSection.tsx:60`
- `frontend/src/features/inspector/sections/QuickViewSection.tsx:62`
- `frontend/src/features/inspector/sections/QuickViewSection.tsx:67`

Planned improvement:
- Use icon-only copy control per row (tooltip + `aria-label` preserved).
- Keep copied feedback via icon state and/or existing copied toast semantics.
- Objective: denser, cleaner row layout for long metadata values.

---

### B) Basics section: align label and value columns to the left
Current behavior:
- Value column is right-aligned (`text-right`) in `CopyableInfoValue`.
- Left/right split creates unnecessary visual tension for short factual fields.

Evidence:
- `frontend/src/features/inspector/sections/BasicsSection.tsx:48`
- `frontend/src/features/inspector/sections/BasicsSection.tsx:50`
- `frontend/src/features/inspector/sections/BasicsSection.tsx:123`

Planned improvement:
- Left-align both label and value while keeping fixed label width and spacing.
- Example target rhythm:
  - `Dimensions      832x1216`
  - `Size            1.2MB`
- Keep rows readable with existing gap/w-width conventions.

---

### C) Compare Metadata table: prioritize click-to-copy on text cells over pan
Current behavior:
- Pan starts on pointer down across the full table body area.
- Clickable value/path buttons can lose click intent when slight movement starts pan.
- Cursor remains grab/grabbing across the area, reducing affordance clarity for clickable text.

Evidence:
- `frontend/src/features/inspector/sections/CompareMetadataSection.tsx:113`
- `frontend/src/features/inspector/sections/CompareMetadataSection.tsx:177`
- `frontend/src/features/inspector/sections/CompareMetadataSection.tsx:225`
- `frontend/src/features/inspector/sections/CompareMetadataSection.tsx:239`

Planned improvement:
- Gate pan start to non-interactive table gaps/background.
- Do not start pan when pointerdown originates in copyable button content.
- Cursor behavior:
  - over clickable path/value text: pointer cursor, click copies
  - over non-interactive spacing/background: grab cursor, drag pans
- Preserve horizontal pan for large compare tables without breaking copy interaction.

## Suggested Execution Order (Future Work)
1. Stabilize toolbar slot layout (findings 1-3).
2. Stabilize vertical top-stack and grid width behavior (findings 4-6).
3. Add micro-jitter polish for dynamic labels and badges (finding 7).
4. Implement inspector Quick View reservation behavior.
5. Implement inspector single-image simplification (`Item` removal + filename grouping + `Find similar` relocation).
6. Apply requested micro UX tweaks (Quick View copy icon, Basics alignment, compare table click-vs-pan priority).

## Acceptance Checks (Future Work)
- Repeatedly navigate viewer next/prev: toolbar anchor controls do not shift horizontally.
- Toggle similarity mode/filter chips/status banners: grid top anchor remains visually stable.
- Toggle metric scrollbar mode: thumbnail column alignment does not reflow.
- Inspector autoload on:
  - quick-view -> quick-view: minimal/no section jump.
  - quick-view -> no-quick-view: placeholder removed only after metadata resolves.
  - no-quick-view -> quick-view: no pre-reservation before confirmation.
- Quick View rows: icon-copy controls leave more visible value text; copy feedback remains clear.
- Basics rows: labels and values read left-to-right with stable spacing.
- Compare Metadata table:
  - clicking value/path text reliably copies
  - dragging on non-interactive table gaps pans horizontally
  - cursor shape matches interaction target (pointer vs grab).
