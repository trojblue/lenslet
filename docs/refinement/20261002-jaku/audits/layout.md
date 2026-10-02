# Main-gallery layout review

Scope: gallery toolbar, folders/metrics rail, Inspector, Viewer and Compare. Ranking excluded by user direction. Read `better-layout` and both references, consolidated severity from `better-interface`, repository instructions and the presentation-continuity contract. Existing compact tool density is retained.

## Evidence and findings

| Severity | Location | Before | After / bounded scope | Why |
| --- | --- | --- | --- | --- |
| HIGH L1 | `frontend/src/app/layout/responsiveLayoutPolicy.ts:175`, `frontend/src/shared/ui/toolbar/ToolbarMobileDrawer.tsx:216`, `frontend/src/app/AppShell.tsx:1541` | At 320/390px Left/Right switches change stored preference but no pane appears. Folders, Metrics, Derived and Inspector become unreachable. Short-height policy similarly suppresses both panes. | Add transient, explicitly opened overlay presentation for panes that cannot fit inline. Keep existing mounted pane instances and desktop preferences. | Adaptivity must keep essential controls and content available. |
| HIGH L2 | `frontend/src/styles.css:1027`, `frontend/src/styles.css:1066`, `frontend/src/styles.css:1357` | At 320px touch Sync button spans x190–220 and Search x214–258; Viewer Back spans x12–44 and Left x32–76. Larger touch controls overflow fixed narrow slots. | Size shared slots from the actual control footprint; preserve non-overlapping toolbar groups. | Adjacent targets overlap and their boundaries mislead users. |
| MEDIUM L3 | `frontend/src/styles.css:556`, `frontend/src/app/components/StatusBar.tsx:152` | Read-only warning uses intrinsic no-wrap width; at320/390 dismiss starts x418. Entire status rail scrolls horizontally, so the action is reachable but easy to miss. | Bound shared status items, keep action fixed inside available width, provide accessible complete message. | Critical warning/actions belong in stable chrome, with clear disclosure when truncated. |
| MEDIUM L4 | `frontend/src/shared/ui/Toolbar.tsx:159` | At320px Compare leaves the 217px browse drawer painted over its lower image stage despite incompatible disabled browse controls. | Treat Compare as overlay-active for drawer visibility; keep state retained. | Content controls must not cover the active task. |

## Implementation architecture (approved scope)

- Keep `buildResponsiveLayoutModel` as the inline geometry owner. Add explicit per-pane presentation capability derived from usable center space and height; do not turn desktop persisted `open` preferences into automatically open mobile modals.
- Track one transient open pane independently in the shell. A toolbar intent toggles an inline preference when it fits, otherwise opens the corresponding overlay. Responsive pane wrappers remain at fixed React locations, use `display: contents` inline, and expose a bounded opaque sheet with header/close button when active. Existing descendants stay mounted; no portal/reparent or extra pane copy.
- Reuse the shared modal-focus hook maintained by the accessibility agent for Escape, topmost focus trap, background inert and restoration. Close sheet before Compare opens. Keep popovers working via hook-owned portal containment.
- Add responsive styles in their own CSS owner and import from `styles.css`. Shared toolbar slot geometry and status truncation live there; no fresh animation or motion system.
- Add meaningful model tests and live narrow/short-height/desktop verification; retain drafts, expansion and settled media when sheet visibility changes. Root owns integrated build/mirror and broad gates.

## Verification so far

Existing served bundle inspected with Playwright Chromium at320×844,390×844 touch,768×600 and1440×960. Gallery search, folder/Inspector toggle attempts, Viewer, and Compare opened desktop then resized. Screenshots and DOM bounds: `/tmp/lenslet-layout-audit/`; scripts `check.py`, `flows.py`, `stress.py`. Screenshots show the reported overlaps and invisible panes. Read-only banner is a horizontal-scroller discoverability issue, not claimed wholly unreachable. Desktop Inspector/RTL and CSS200% stress inspected separately; CSS zoom is not full browser zoom. True browser200% zoom, translated locale, empty/error matrix and exhaustive long-value fixtures: Not verified yet.

Verdict: **Block** until L1/L2 resolved; uninspected surfaces are not approved.

## Implementation checkpoint

Implemented L1–L4 through existing paths. New `useResponsivePanels` separates transient overlay intent from persisted inline preferences, `ResponsivePanel` preserves subtree identity and reuses `useModalFocusTrap`, and `responsivePanels.css` owns shared responsive geometry. Inspector stays lazy until first visible, then mounted; folder/metric visibility checks use actual inline-or-overlay visibility. Mobile actions read Browse/Inspector. Compare and Similarity launch close the sheet first. Shared keyboard-accessible separators adjust widths by 10px (40px with Shift), with Home/End bounds, and persist using existing keys. Added main landmark/skip link without mutating the gallery hash route. Coarse narrow text inputs use16px to avoid mobile browser autozoom; desktop input density unchanged.

The desktop header also had a confirmed scope/count collision: a zero-width scope text descendant painted beneath sorting controls. Its shared structure now stacks identity above the stable count slot, uses intrinsic center-control width, and avoids reserving a never-available Upload slot. Visibility changes for actual async states still retain their slots.

Post-build Chromium checks passed at320×844,390×844 and760×430: Browse tools opens Folders/Metrics/Derived; Inspector opens with content; Escape restores exact trigger focus; real backdrop click closes the short-height Inspector; document widths equal viewport widths. At1440×960 keyboard resize changes left pane340→350px. No page errors. Evidence: `/tmp/lenslet-layout-audit/after-results.json`, `browse-sheet-{320,390,760}.png`, `inspector-sheet-{320,390,760}.png`. Focused44 Vitest tests passed across responsive policy, width storage/clamping, Toolbar, mobile drawer and StatusBar; TypeScript passed. Latest header follow-up awaiting next integrated build at this checkpoint. Integrated retained-draft/earliest-painted-frame probe is owned by media-cache agent; modal portal verification by accessibility agent.

## Completed verification and follow-up

Build2 toolbar matrix passed at320,390,640,760,900,901,1024,1180,1181,1440 and1920px for both Gallery and Viewer: zero overlapping toolbar controls, zero controls outside viewport, nonzero visible scope text width in every gallery layout. All sheet access/close/focus/backdrop checks above passed again. Evidence: `/tmp/lenslet-layout-audit/header-results.json` and `final-gallery-*.png` / `final-viewer-*.png`. Compare at320px has no browse drawer covering its stage (`final-compare-320.png`).

An additional HIGH finding was reproduced while checking responsive continuity: desktop search `sample` remained the active app query after resizing to390px, but opening mobile search showed an empty field. Both input presentations now receive the immediate parent-owned query via `searchValue`; no separate or debounced draft was introduced. The integrated browser regression is assigned to verify resize, hide/reveal and mode return against the final build. Focused test count is now45, all passing; TypeScript passes.

Dead Upload affordance removed completely from Toolbar/mobile props, rendering and styles after confirming no production caller supplies an upload action. Backend upload capabilities were not changed. Back appears only in Viewer. These are explicit mode/capability controls, not asynchronous pending/settled controls; retained refresh/search/count slot contracts remain. Delivery agent updates the relevant toolbar gate rather than asserting nonexistent controls.

Layout findings L1–L4 and responsive search draft ownership are implemented. **Approve inspected layout scope**, subject to the integrated full-suite/painted-frame gates recorded by the main session. True browser200% zoom (rather than equivalent CSS viewport), browser-native RTL locale behavior and actual iOS Safari autozoom remain **Not verified**; no claim of coverage for these or excluded ranking surfaces.
