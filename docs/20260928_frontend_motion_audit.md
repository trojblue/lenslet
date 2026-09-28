# Frontend motion audit and refresh

Date: 2026-09-28. Branch: `feat/frontend-motion-refresh`.
Baseline: `d11142a`. This is an implementation record and maintained backlog;
[DESIGN_SYSTEM.md](DESIGN_SYSTEM.md) remains the presentation contract.

## Guidance and scope

The installed `npx transitions-dev add --free` material is a collection of 32
Markdown recipes in `/fsx/yada/dev/transitions/`, installed beside this repository,
not a `SKILL.md` package inside it. The audit uses those local recipes, particularly
`accordion.md`, `toggle.md`, `menu-dropdown.md`, and `card-resize.md`.
No runtime animation dependency or second `t-*` styling system is needed.

Reviewed the shared stylesheet, Tailwind utilities, Dropdown, Toolbar,
ThemeSettingsMenu, folder tree, thumbnail cards, Inspector sections, Metrics,
Viewer, Compare, ranking, and the existing browser continuity gates. Source
findings below are distinguished from browser evidence in the validation log.
This is a motion and interaction audit, not a claim of exhaustive screen-reader,
contrast, or cross-browser certification.

The refresh should make frequent actions feel consistent and reversible. It
must preserve immediate menu readability, decoded media identity, fixed status
slots, keyboard behavior, and user drafts. Recipe durations are examples, not
requirements: reuse Lenslet's short interaction durations and one shared easing
curve. Do not copy decorative blur, particles, counter reels, or entrance delays
into a data-review tool merely because a recipe exists.

## Findings and work queue

| ID | Priority / status | Evidence and affected owner | Change and reason |
| --- | --- | --- | --- |
| M01 | High / implemented | `styles.css` uses unrelated 100/120/140/160/200ms transitions; Tailwind utilities use their own defaults. Toolbar search adds `transition-all duration-200` over the common input. | Define one shared motion vocabulary and replace existing declarations/utilities at their owners. Explicit properties keep layout and focus feedback predictable. |
| M02 | High / implemented | `InspectorSection.tsx` defers opening through an effect and rAF, removes children after 140ms; CSS interpolates `max-height: 0 → 9999px` plus opacity and translation. | Replace with the recipe's intrinsic CSS-grid disclosure in this common section component. Keep descendants mounted, opaque, and inert when closed. Preserve drafts, local expansion, and scroll; reverse directly on rapid toggles. |
| M03 | Medium / implemented | `ranking.css` has three `transition: all` rules. SortableRankingCard sets inline `transition: none`, defeating the card's visual feedback as well as movement. Hover movement is not limited to fine pointers. | Explicitly transition surface feedback while leaving drag transforms immediate; use the shared easing/timing. Gate decorative hover movement and keep fullscreen actions available on touch. |
| M04 | Medium / implemented | Global reduced-motion rule covers `*` but not pseudo-elements; slider-thumb feedback lives on a pseudo-element. Sync-card entrance is declared then canceled in `utilitySurfaces.css`; three entrance keyframes remain. | Put reduced-motion coverage in the common motion layer, include pseudo-elements, remove superseded entrance declarations/keyframes, and test the built CSS. |
| M05 | Medium / investigate | ThumbCard uses a 160ms decoded-image fade, while Viewer/Compare use atomic promotion. Recycled cards also maintain local `loaded` state. | Trace cold/warm scrolling and recycled identities before changing thumbnail reveal ownership. Preserve the existing decode gate; do not add a skeleton crossfade. This has data/pixel-identity risk beyond a styling refresh. |
| M06 | Medium / candidate | Sidebar tabs and attribute segments change active backgrounds without a shared segmented-control component. | A shared sliding indicator could clarify selection. First consolidate the component and verify variable-width labels, overflow, hidden tabs, first paint, and reduced motion. Never slide or fade the async tab body. |
| M07 | Low / candidate | Modals and transient confirmations have separate shells/lifetimes across Similarity, export, Viewer, and ranking. | Consider a shared dialog/presence owner only after focus, Escape, exit interruption, and media continuity are specified. A mount-only zoom patch would create another motion style. |
| M08 | Low / retain | ThemeSettingsMenu already has track/knob transitions and state-driven transforms. | Use common timing/easing without the recipe's keyframe bounce; this keeps interruption continuous and avoids mount animations. |
| M09 | Low / retain | Frequent Dropdown/context/theme/sync panels already use opaque first frames and stable shells. | Preserve R5. Improve trigger feedback through shared tokens, not recipe entrance fades. |
| M10 | Low / investigate | Permanent `will-change: transform` occurs on virtual rows and media; ranking fullscreen uses an 80ms linear transform transition. | Measure compositor memory and pointer-follow latency before changing these performance-sensitive paths. Do not infer a problem from the declaration alone. |

## Coverage of all installed recipes

“Candidate” means an improvement worth revisiting, not an observed defect or a
commit promised by this low-risk pass. “Keep” means retain Lenslet's current
behavior. “Skip” means the pattern does not suit the present product or contract.

| Recipe | Lenslet surface / disposition | Reason or next step |
| --- | --- | --- |
| accordion | Inspector sections — implement M02 | Intrinsic height and retained children replace the existing common disclosure. Omit blur/fade. |
| avatar-group-hover | Presence/filter chips — skip | Neighbor lift and bounce distract from dense controls and can move targets. |
| banner-stacking | StatusBar/banners — candidate M07 | Requires a shared notification queue; preserve reserved status rows. |
| card-resize | Inspector — adapt M02; grid — keep | Intrinsic disclosure sizing fits; animating virtualized card dimensions would interfere with layout/scroll anchoring. |
| card-tilt | Gallery/ranking cards — skip | Keep image pixels undistorted and drag targets stable; M03 improves surface feedback instead. |
| checkbox-check | Attribute filters/multi-select — keep | Checked state should be immediately legible. A delayed stroke offers little benefit for repeated classification. |
| error-state-shake | Inputs/errors — skip | Persistent actionable error copy matters; shake and timed auto-reversion could obscure unresolved errors. |
| icon-swap | Sidebar/menu triggers — candidate | If adopted, share one icon slot and preserve accessible names; avoid blurred interim icons. |
| input-clear-dissolve | Toolbar search — skip | Clear immediately; per-word rAF effects and a 1s dissolve delay repeated filtering. Narrow common input transitions under M01. |
| learn-more-hover | Links — keep | No important matching CTA; do not introduce a one-off arrow style. |
| like-button | Rating stars — skip | Ratings are annotation controls, not celebrations; retain immediate color/state feedback. |
| matrix-loader | Loading status — keep | Existing reserved status copy suffices. Never imply activity without an actual pending request. |
| menu-dropdown | Shared Dropdown/context/theme menus — keep M09 | Recipe opacity-zero entrance conflicts with R5. Reuse easing only. |
| modal | Dialogs/overlays — candidate M07 | Needs shared lifecycle/focus ownership before animation. |
| notification-badge | Selection/presence badges — keep | Stable, immediately readable counts are more useful than a sliding/blurred badge. |
| number-pop-in | Counts/metric values — skip | No partial digits or staggered query-owned values during atomic promotion. |
| page-side-by-side | Browse/Viewer/Compare — skip | Sliding or blurring media conflicts with presentation-owned pixels and transforms. |
| panel-reveal | Sidebars/mobile drawer — candidate | Requires layout/scroll/focus validation; preserve mounted state and opaque content. |
| plus-menu-morph | Add-field controls — skip | Trigger and popup are separate; morphing the trigger changes useful anchor geometry. |
| reasoning-stream | No agent transcript — skip | No matching product surface. |
| shimmer-text | Pending metadata/status — skip | Avoid continuous decorative movement and duplicate text in dense review UI. |
| skeleton-reveal | Async Inspector/Metrics/media — skip | R7/R9 require settled content retention, not skeleton replacement or blur. |
| spinning-counter | Counts — skip | Reel fanfare obscures values and adds latency to frequent filtering. |
| streaming-text | Metadata/notes — skip | These are complete editable values, not streamed generated paragraphs. |
| success-check | Copy/export feedback — candidate M07 | A common fixed icon/status slot could help; preserve text confirmation and immediate truth. |
| tabs-sliding | Sidebar/attribute tabs — candidate M06 | Move a shared selection indicator only, not tab content or query-owned values. |
| text-states-swap | StatusBar/save labels — keep | Fixed slots already avoid reflow; blurred outgoing/incoming labels can mix target identities. |
| texts-reveal | Empty/error/help text — skip | Readable first frames are preferable to staggered reveal in a utility app. |
| thinking-states | No agent execution stream — skip | Do not synthesize narration for ordinary network requests. |
| toast | Confirmations — candidate M07 | Consolidate lifecycle first; no isolated entrance patch. |
| toggle | ThemeSettingsMenu — adapt M08 | Common state-driven transition, no load-time or repeated bounce keyframes. |
| tooltip | Native titles/hover preview — candidate | A future accessible tooltip owner must support keyboard, touch, clamping, and dismissal. Preview media continues to decode before display. |

## Implementation and validation log

- Audit commit: record the inventory, contract decisions, and prioritized queue.
- M01/M04: shared motion tokens, property-specific transitions, reduced-motion
  coverage; validate full Vitest, TypeScript, build, toolbar painted frames.
- M02: common disclosure replacement; validate browser frames from the click
  onward, short/long sections, first open, rapid reversal, persisted closed
  state, retained input/scroll, focus exclusion, and reduced motion. Run the
  existing Inspector continuity probe with cold targets and decoded media.
- M03: ranking feedback cleanup; validate real ranking controls, resizing,
  dragging, touch action visibility, and reduced motion.
- Finish with rebuilt/mirrored packaged assets, acceptance, relevant jitter
  scenarios, repository lint, and recorded outcomes here.

Browser evidence belongs under `docs/20260928_motion_evidence/`; bulky raw traces
may stay in `/tmp/lenslet-motion-audit/`. Before modifying a browser harness,
record the owning defect and expected reduction here. The proposed focused
motion probe addresses M02's unmount/snap and M03/M04's pointer/motion-policy
gaps; it must exercise actual components rather than only assert stylesheet text.

### Shared motion foundation

Implemented M01/M04 at the existing CSS/Tailwind owners; M08 now shares the
feedback tokens. Removed search's all-property override and the dead menu
entrance rules. Packaged assets rebuilt and mirrored.

Validation: 121 Vitest files / 692 tests passed, TypeScript passed, build passed,
repository lint passed (existing size warnings). Live Dropdown, theme settings,
and presence/count painted-frame checks passed, including opaque first frames;
computed buttons use 120ms and the shared curve, and reduced motion yields 0s.
The complete toolbar probe reached an export-menu disappearance, subsequently
reproduced against the untouched baseline (details below). Initial browser setup required
installing Chromium and its system libraries; no product workaround was added.

### Intrinsic Inspector disclosures

M02 is implemented in the common section component. The focused frame test also
exposed visibility-gated parsed metadata and comparison matrices in `Inspector`;
those presentations now follow data identity rather than disclosure visibility.
Closed descendants stay inert, section buttons link to their bodies, and focus
returns to the trigger when a closing body contains it.

The baseline Notes body stayed near 215px for roughly 100ms while fading, then
collapsed and detached its textarea. The replacement has multiple intermediate
height frames, stays opaque, and keeps the same textarea, draft, scroll, rows,
actions, and decoded preview pixels. Short/long sections, reverse-at-50ms,
comparison rows, persisted closed first frames, and reduced motion passed.
See [baseline trace](20260928_motion_evidence/baseline-disclosure.json) and
[verified frame summaries](20260928_motion_evidence/disclosures.json).
Reproduce with `python -m scripts.browser.motion_refresh` after rebuilding.

The complete Inspector jitter probe passed, including cold unvisited targets,
rapid selection, delayed/failed responses, hidden/tab lifecycle, and media
identity checks. Full Vitest (692 tests), TypeScript, build, and lint passed.
Packaged assets were regenerated for this commit.

The toolbar export-menu failure also reproduces with the untouched `d11142a`
bundle served separately: `_capture_folder_and_context_surfaces` loses
`.context-menu-panel` during its export/viewport sequence. This is recorded as
an existing gate failure, not a successful full-toolbar result. The focused
Dropdown/theme/presence checks pass with the refreshed bundle.

### Ranking feedback

M03 is implemented at `ranking.css` and the common sortable card. Card feedback
now transitions border/shadow only, so drag transforms stay immediate; the old
inline blanket suppression is gone. Explicit property lists replace all three
`transition: all` declarations. Decorative button/resize/slider movement applies
only to fine hover pointers without reduced motion. Touch users can see and tap
fullscreen actions without a hover gesture.

Live Chromium checks passed at desktop 1440×960 and touch 390×844, plus reduced
motion: hover did not move card rectangles, keyboard focus revealed fullscreen,
decoded fullscreen pixels were opaque, drag placed a card into rank 1, and tray
resize changed its height from 480 to 525px. Reduced-motion card and slider-thumb
transitions resolved to 0s. See [ranking results](20260928_motion_evidence/ranking.json)
and [touch screenshot](20260928_motion_evidence/ranking-touch.png).
The retained Inspector presentation is shown in
[this screenshot](20260928_motion_evidence/inspector.png); static images illustrate
layout only, while the frame traces establish motion behavior.

To review manually, launch `lenslet rank` with a small local fixture, hover/select
and drag a card, resize the unassigned tray, then repeat fullscreen entry with a
touch viewport and reduced motion. All validation used generated fixture images.
Full Vitest (692 tests), TypeScript, build, and repository lint passed; packaged
assets regenerated for this commit. Full acceptance and remaining continuity
results follow below.

## Final result and remaining validation debt

Completed M01–M04 and M08's token alignment, in separate implementation commits:

- `15fbc90` — shared motion vocabulary and reduced-motion policy.
- `efd970e` — intrinsic Inspector disclosures and retained parsed presentations.
- `01d422b` — ranking feedback, immediate drag transforms, and touch actions.

No runtime dependency was added. Every implementation commit rebuilds and mirrors
`src/lenslet/frontend/`. A final checksum dry run of `rsync` found no differences
from `frontend/dist/`. The audit/backlog above is the place to record future
motion work; candidate items need their stated evidence before implementation.

| Validation on final code | Result |
| --- | --- |
| `npm --prefix frontend test -- --run` | 121 files, 692 tests passed |
| `frontend/node_modules/.bin/tsc --noEmit -p frontend/tsconfig.json` | Passed |
| `npm --prefix frontend run build` + bundle mirror | Passed |
| `python scripts/lint_repo.py` | Passed; existing size warnings remain |
| `python -m scripts.browser.gui_smoke.acceptance` | Passed |
| `python -m scripts.browser.gui_jitter.probe --scenario inspector` | Passed |
| `python -m scripts.browser.gui_jitter.probe --scenario metrics` | Passed |
| `python -m scripts.browser.motion_refresh` | Passed normal/reduced motion, reversal, retained descendants/drafts/scroll/pixels, focus exclusion, and persisted closed first frame |
| Ranking interaction checks | Passed desktop, touch, reduced motion, drag/drop, resize, keyboard fullscreen, decoded fullscreen |
| `gui_jitter --scenario toolbar` | Existing export-menu disappearance; reproduced on baseline. Focused Dropdown/theme/presence checks passed |
| `gui_jitter --scenario grid` | Existing Compare color assertion failure; reproduced on baseline. Other reported grid/media/hover/ranking checks passed |

The grid failure is a fixture-state mismatch: `exercise_browse_continuity`
switches the backend to `source_alt`, then the later Compare probe still uses
`COMPARE_EXPECTED_RGB` for the original `source`. For `quick_01_meta.png`, it
expects approximately `(36,126,74)` but receives the alternate fixture's
`(188,42,117)`. Baseline and refreshed bundles have the same mismatch; both
report zero mixed-identity frames. This does not constitute a successful complete
grid gate. Restore fixture source state or make the expected palette source-aware
in a dedicated harness change. Similarly, make the toolbar export/viewport probe
own its pending-export lifetime before relying on its geometry assertions.
Neither probe was weakened or bypassed in the repository.

[Validation summary](20260928_motion_evidence/validation.json) preserves the
outcomes and baseline comparison. Full raw logs/traces are in
`/tmp/lenslet-motion-audit/` for this session. Verification used Chromium;
Firefox/WebKit and physical touch-device performance remain unverified.
