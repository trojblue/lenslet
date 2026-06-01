# 2026-05-24 Resizing Interactions Review

## Scope

Browser-based review of Lenslet browse-mode behavior under narrow windows, short windows, sidebar resizing, viewer/compare overlays, and partial zoom-equivalent scaling.

Live app used for review:
- Frontend: `http://127.0.0.1:5173/`
- Backend: `http://127.0.0.1:7070/`
- Fixture dataset: `/tmp/lenslet-resize-audit-knmvyttj`

Validation sources:
- Local Playwright geometry sweep across `320`, `360`, `390`, `480`, `640`, `760`, `900`, `1024`, `1180`, and `1440` width slices.
- Subagent scans for narrow toolbar/grid, vertical compression/overlays, and sidebar/inspector resizing.
- Existing source correlation in `frontend/src/shared/ui/Toolbar.tsx`, `frontend/src/styles.css`, `frontend/src/lib/breakpoints.ts`, `frontend/src/features/inspector/Inspector.tsx`, `frontend/src/features/viewer/Viewer.tsx`, and `frontend/src/features/compare/CompareViewer.tsx`.

No new dependencies were installed during this review.

## Findings

| ID | Severity | Fix Difficulty | Area | Broken Behavior | Repro Evidence | Likely Source |
| --- | --- | --- | --- | --- | --- | --- |
| R1 | High | Medium | Top toolbar, narrow widths | Toolbar controls overlap at phone widths. At `320px`, Filters overlaps the panel toggles and refresh overlaps Upload. At `360px`, Filters/refresh still collide with panel toggles. At `390px`, refresh overlaps the left-panel toggle. | Open browse screen at `320x700`, `360x700`, or `390x700` with scan-stable banner visible. Local screenshots: `/tmp/lenslet-resize-audit/320x700_initial.png`, `/tmp/lenslet-resize-audit/360x700_initial.png`, `/tmp/lenslet-resize-audit/390x700_initial.png`. | `frontend/src/shared/ui/Toolbar.tsx`; `frontend/src/styles.css` `@media (max-width: 900px)` rules for `.toolbar-shell`, `.toolbar-left`, `.toolbar-right`, `.toolbar-slot-refresh`, `.toolbar-panels`. |
| R2 | High | Medium | Mobile search row | Opening mobile search can render the search row over the status banner/grid instead of cleanly increasing the toolbar area. | At `320x740`, click the top-right search icon. Subagent screenshot: `/tmp/lenslet_resize_scan_1779663905/320_search_open.png`. Local sweep also showed search/status overlap at `640x760`, `760x760`, `900x760`, and `760x430`. | `frontend/src/shared/ui/Toolbar.tsx` mobile search row; `frontend/src/styles.css` `.app-shell { grid-template-rows: var(--toolbar-h) minmax(0, 1fr); }` and mobile `.toolbar-shell { position: relative; height: auto !important; }`. |
| R3 | High | Medium | Right inspector on mobile/narrow widths | The right inspector can remain open on phone widths and squeeze the grid into an unusable sliver. At `390px`, inspector actions such as `Load meta` and `Find similar` extend outside the viewport. At `480px`, inspector text/buttons visibly clip. | Select an item at `390x700` or `480x760`, then toggle the right panel. Local screenshots: `/tmp/lenslet-resize-audit/390x700_right_toggled.png`, `/tmp/lenslet-resize-audit/480x760_right_toggled.png`. | `frontend/src/lib/breakpoints.ts` permits right column widths below practical content minimums when space is constrained; `frontend/src/features/inspector/Inspector.tsx` uses fixed preview width `w-[220px]`; inspector section controls assume wider columns. |
| R4 | Medium | Medium | Viewer overlay on small/short viewports | Viewer overlays reserve sidebar columns, so with the right inspector open the viewer is squeezed instead of taking the available viewport. A right-inspector sliver remains visible/interactable. | At `390x520`, select an item, open right inspector, then open viewer. Also reproduced at `760x430`. Subagent screenshots: `/tmp/lenslet_resize_audit_1779664142/390x520_viewer.png`, `/tmp/lenslet_resize_audit_1779664142/760x430_viewer.png`. | `frontend/src/features/viewer/Viewer.tsx` uses `left-[var(--left)] right-[var(--right)]`; `frontend/src/app/AppShell.tsx` keeps sidebar reservations active under overlay mode. |
| R5 | Medium | Medium | Compare overlay on phone widths | Compare mode opens inside the sidebar-reserved grid area, while the bottom mobile drawer remains visible and competes with compare controls. | At `390x520`, select two items, open the left rail, and start compare. Subagent screenshot: `/tmp/lenslet_resize_audit_1779664142/390x520_compare.png`. | `frontend/src/features/compare/CompareViewer.tsx` uses `left-[var(--left)] right-[var(--right)]`; `frontend/src/shared/ui/toolbar/ToolbarMobileDrawer.tsx` remains active under compare overlay. |
| R6 | Medium | Medium | Sidebar width constraints | With both sidebars reopened at `760px`, the right inspector can be squeezed to about `200px`; under forced shrink to `620px`, it can collapse to about `60px` while controls still render. Fixed inspector content then clips or overflows. | At `760px`, reopen both sidebars, select one/multiple items, open inspector sections. Subagent screenshots: `/tmp/lenslet-resize-focus/w760_both_single_sections.png`, `/tmp/lenslet-resize-focus/w760_both_multi_sections.png`, `/tmp/lenslet-resize-focus/w760_right_drag_max_view_620.png`. | `frontend/src/lib/breakpoints.ts` `constrainSidebarWidths`; `frontend/src/features/inspector/Inspector.tsx`; `frontend/src/features/inspector/sections/BasicsSection.tsx` star row. |
| R7 | Medium | Small | Inspector fixed content | Inspector single-item preview and star rows are not responsive to the actual column width. Stars overflow at short heights or squeezed widths, and action buttons clip in narrow columns. | Local sweep saw star row overflow at `480x760` and `1024x480` after item selection/right panel toggle. Screenshot: `/tmp/lenslet-resize-audit/1024x480_item_selected.png`. | `frontend/src/features/inspector/Inspector.tsx` fixed `w-[220px]` preview; `frontend/src/features/inspector/sections/BasicsSection.tsx` fixed-width star controls/row. |
| R8 | Medium | Small | Bottom mobile drawer | Later bottom-drawer controls are hidden behind horizontal scrolling, with hidden scrollbars and no visual overflow affordance. Select, Theme, and Upload can start offscreen at `320px`/`360px`. | Open browse screen at `320x700` or `360x700`. Local screenshots: `/tmp/lenslet-resize-audit/320x700_initial.png`, `/tmp/lenslet-resize-audit/360x700_initial.png`. | `frontend/src/shared/ui/toolbar/ToolbarMobileDrawer.tsx`; `frontend/src/styles.css` `.mobile-drawer-row { overflow-x: auto; }` and hidden scrollbar rules. |
| R9 | Low | Small | Filter menu under short heights | Filter dropdown overlaps the scan-stable status banner. It remains usable and in viewport, but the stacking is visually noisy on short screens. | Open filter menu at `390x520` or `760x430` while status banner is visible. Subagent screenshots: `/tmp/lenslet_resize_audit_1779664142/390x520_filter-menu.png`, `/tmp/lenslet_resize_audit_1779664142/760x430_filter-menu.png`. | `frontend/src/shared/ui/toolbar/ToolbarFilterMenu.tsx`; `.dropdown-panel` styles in `frontend/src/styles.css`. |
| R10 | Low | Medium | Metrics sidebar at narrow tablet widths | With both sidebars open at `760px`, the metrics panel summary becomes cramped; metric values intrude into neighboring labels/controls. | At `760px`, reopen both sidebars, switch left rail to Metrics/Filters, select 3 items. Subagent screenshot: `/tmp/lenslet-resize-focus-extra/w760_metrics_both_open.png`. | `frontend/src/features/metrics/MetricsPanel.tsx`, especially fixed label/value widths such as `w-28 shrink-0`. |

## Fix Order

1. Fix the narrow-toolbar grid first (`R1`, `R2`), because it affects every phone-width session and causes direct button overlap.
2. Define mobile/narrow overlay policy (`R3`, `R4`, `R5`, `R6`): viewer/compare should likely ignore sidebars on narrow widths, and inspector should not be allowed to remain as a clipped sliver.
3. Make inspector internals responsive (`R7`) once the column policy is settled.
4. Improve lower-priority affordances (`R8`, `R9`, `R10`) after the primary layout collisions are gone.

## Notes

- The grid itself did not show document-level horizontal overflow in the tested width slices.
- Filter, theme, item-action, and sort menus generally stayed inside the viewport in narrow-width scans.
- Browser zoom-specific testing was time-limited. The strongest zoom-adjacent risks are the same as the narrow-width findings: fixed toolbar slots, fixed inspector content, and sidebar-reserved overlays.
