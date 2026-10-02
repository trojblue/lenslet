# Main gallery visual audit — 2026-10-02

Scope: typography and color in main gallery, folder navigation, sort menu, Settings, metrics controls, and Inspector. Ranking excluded. Applied Jaku `better-typography`, `better-colors`, and `better-interface` evidence/escalation rules. Read repository AGENTS.md and canonical DESIGN_SYSTEM.md; preserve density, local font loading, opaque utility panels, and settled async presentation.

## Confirmed findings

| Severity | Location | Before | After / shared scope | Why |
| --- | --- | --- | --- | --- |
| HIGH | `frontend/src/theme/runtime.ts:25`, `frontend/src/styles.css:1557`, `frontend/src/features/folders/FolderTree.tsx:338` | Original's solid accent doubles as text. Selected Sort “Date added” measures 3.79:1; selected Root 3.84:1 on its composited accent wash. | Separate accent foreground role using existing lighter accent hue; route main foreground consumers through it. Folder active text uses primary text. | Required 4.5:1 normal control text fails; color role reused across fill and foreground causes systemic failure. |
| HIGH | `frontend/src/features/folders/FolderTree.tsx:365` | Count inherits selected foreground and adds opacity50. Approximate composited ratios Original1.84, Teal2.57, Charcoal2.35. | Explicit muted foreground at full opacity; tabular numbers. Performance owner integrates with FolderTree work. | Folder counts carry useful navigation data and opacity makes them illegible. |
| HIGH | `frontend/src/theme/runtime.ts:24`, `frontend/src/styles.css:1634` | Muted text “Load PNG metadata when selecting an image” on active Settings wash measures4.13:1. | Raise muted foreground lightness in Original/Teal; remeasure all presets. | Shared quiet text role needs to remain readable on selected surfaces. |
| MEDIUM | `frontend/src/styles.css:1637` | Settings subtitles use 1.25 line-height; source launch summary wraps three lines in the inspected310px menu. | Use1.4 for wrapped explanatory text. | Three-line descriptions require comfortable leading even in dense UI. |

No arbitrary palette/font redesign proposed. All three supported themes (Original, Teal, Charcoal) are dark; light mode does not exist and was not claimed as inspected. Current system fonts avoid blocking remote font requests. Gallery filename clamps retain complete title text; changing toolbar counts already have tabular numerals.

## Evidence and verification

Local isolated server: `python -m lenslet.cli /tmp/lenslet-motion-demo-20261002-ua1fsjed --port7113 --no-write` (actual CLI uses separate `--port 7113`). Chromium1440×960,390×844; generated18-image dataset. Evidence outside repository: `/tmp/lenslet-jaku-visual/{Original,Teal,Charcoal,sort,settings,metrics,mobile}.png`, `contrast.json`, `states.json`, measurement scripts. Color collector resolves computed CSS colors through canvas and composites ancestor backgrounds; opacity-heavy count measurement is approximate because group-opacity composition can affect its own background. The exact failing selected text pairs have no element opacity. Background gradients behind opaque panels do not affect these pairs.

Mobile Safari automatic input zoom, forced colors, APCA, arbitrary real-world image-overlay contrast and complete Inspector/Compare long-text coverage: Not verified in this phase. Other agents own keyboard, responsive geometry, writing, and media behavior. This is not a holistic verdict for excluded states.

Verdict before fixes: **Block** (confirmed required text contrast failures).

## Implementation and revalidation

Implemented shared `--accent-text` / Tailwind `text-accent-text` using the existing brighter accent value for Original and the existing solid accent for Teal/Charcoal. Main selected controls, Compare tags, sync labels and Inspector highlights consume the foreground role. Original/Teal quiet text is now `#aba49b`; Charcoal is `#a4b2c5`. No background palette or font family changed. Settings subtitles use1.4 line-height; numeric fields and Inspector values use tabular numerals. FolderTree fix is delegated to the performance owner; LeftSidebar foreground consumers to the layout owner.

Production build isolated to `/tmp/lenslet-jaku-visual/dist` (served with browser request routing against7113; shared generated assets untouched). Repeated browser measurement on1440×960, with Settings subtitle explicitly scrolled into view:

| Rendered text pair | Original | Teal | Charcoal |
| --- | --- | --- | --- |
| Selected Sort label | 5.17:1 | 6.90:1 | 5.70:1 |
| Selected Settings subtitle | 5.66:1 | 4.89:1 | 4.93:1 |

All exceed4.5:1. Exact measured colors, fonts and backgrounds: `../evidence/visual-contrast.json`. Screenshots `/tmp/lenslet-jaku-visual/after-sort-{Original,Teal,Charcoal}.png`, `after-settings-{Original,Teal,Charcoal}.png`, `after-inspector.png` were recaptured from the isolated production build. Earlier Vite captures had incomplete utility CSS and are superseded.

`npm --prefix frontend test -- --run src/theme/__tests__ src/shared/ui/__tests__/Dropdown.test.tsx`:5 files16 tests passed (the Dropdown path did not add a matching test file; theme tests are the coverage). `cd frontend && npx tsc --noEmit`:passed. New3-preset contrast regression tests cover primary, secondary, muted and accent foregrounds on panel/surface and their selected alpha washes.

Inspector with selected `quick_01_meta.png` was inspected: filename, Quick View, JSON metadata and numeric rows readable; native full-text title/copy/scroll mechanisms preserved. Inactive star shapes measured3.59:1 and meet the non-text3:1 threshold; disabled Find similar is exempt from normal control contrast. No change made for either.

Verdict for implemented color/typography scope: **Approve**. FolderTree contrast remains a tracked dependency until performance integration; this does not approve untouched mobile/Compare error states or claim general WCAG conformance.
