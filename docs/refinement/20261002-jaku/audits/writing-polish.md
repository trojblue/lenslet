# Writing and UI polish audit

Scope: main gallery, search, folder tree, Inspector, Metrics/Derived, Viewer and Compare. Ranking is excluded following the user's scope clarification. Source inspection covers settled, loading, error and empty branches; visual runtime inspection covers the settled desktop gallery and theme switch only. Narrow layouts, hit areas, keyboard/focus and contrast are owned by the other domain audits, not claimed here.

Sources: repository AGENTS.md, docs/DESIGN_SYSTEM.md; jaku `better-writing`, `better-ui` and its surfaces/icons/animations/enter-exit/icon-transitions/performance references; consolidated severity from `better-interface`. React/Tailwind and existing shared controls/motion tokens remain the design system. Recipe-specific springs, blur/scale icon entrances and universal press transforms are not warranted for Lenslet's dense frequent controls; preserving opaque utility panels and decoded media has priority.

## Findings

| ID / Severity | Location | Before | After / bounded scope | Why |
| --- | --- | --- | --- | --- |
| WP-01 HIGH | `frontend/src/features/metrics/components/MetricHistogramCard.tsx:184`, `MetricCategoryCard.tsx:113`, `CategoricalCard.tsx:132`, `DerivedMetricMiniHistogram.tsx:27` | Failed facets only say “Could not load values”; panel owners expose no retry. | Refetch the existing metrics-population query through one callback to Metrics/Derived and expose a stable, accessible recovery action adjacent to error presentation. Preserve drafts, selected fields and settled content while retrying. | Errors name no recovery path; a transient request failure strands an analysis tool. Shared recovery ownership avoids per-card fetches. |
| WP-02 HIGH | `frontend/src/features/folders/FolderTree.tsx:391` | Expanded failed folder says “Failed to load folders” without action. | Use the existing folder query's refetch in the failed child slot. | A failed navigation branch gives no way forward. Forwarded to tree owner. |
| WP-03 HIGH | `frontend/src/lib/mediaResourceState.ts:111`, `frontend/src/features/viewer/Viewer.tsx:318`, `frontend/src/features/compare/CompareViewer.tsx:544` | Decode failures say only “Could not decode this image”; nonretryable branch omits Retry. | Explain that the file may be unsupported/damaged and suggest another image or converting/checking the source. Keep retryability factual; do not add a retry that cannot recover. | Shared nonretryable errors explain failure without helping the reader recover. Copy-only central improvement. |
| WP-04 MEDIUM | `frontend/src/theme/runtime.ts:152` | Applying a preset changes every CSS variable while existing color transitions remain active. | Suppress transitions synchronously around the centralized token swap, flush computed style, restore next frame. No change to ordinary interaction motion. | One theme action fires 205 cosmetic transitions on the settled demo gallery, creating an inconsistent whole-page transition. |
| WP-05 MEDIUM | `frontend/src/app/model/loadingState.ts:70`, `:79` | “Showing the previous window until the backend response arrives.”; empty folder and filtered query share “No images match the current filters.” | Say “Updating results. Your current view stays visible.”; model whether filters/search are active so a genuinely empty folder is identified accurately and filtered/search empties offer clear/reset. | Implementation jargon and ambiguous empty causes harm comprehension. Requires query-context ownership; do not guess from item count. |
| WP-06 MEDIUM | `frontend/src/features/inspector/sections/NotesSection.tsx:55`, `BasicsSection.tsx:169` | Conflict actions mix “Apply again”, “Retry”, “Keep theirs”. | Use consequence-specific labels consistent between rating and notes, e.g. “Save my edits” / “Use latest edits”, after checking exact conflict patch scope. | Concurrent-edit decisions should make the chosen version clear. Requires state-owner review; copy must not claim a narrower overwrite than actual behavior. |
| WP-07 LOW | `frontend/src/features/metrics/MetricsPanel.tsx:114`, `frontend/src/features/inspector/Inspector.tsx:457` | “No metrics or categoricals found”; “Load meta”. | “No numeric or categorical fields found in this dataset”; “Load metadata” if existing action slot accommodates it. | Internal shorthand slows comprehension. Keep technical field terms accurate and avoid broad capitalization churn. |

## Verified and retained

- Gallery query failure already has a real Retry action; filter chips expose Clear all. Inspector preview failure already has Retry preview; comparison metadata has Reload. These should be reused as patterns, not rebuilt.
- Shared 120/160/200ms tokens, explicit transition properties, reduced-motion rules and interruptible mounted Inspector disclosures already provide coherent motion. No second motion system is proposed.
- Dropdown/theme icons use currentColor. Some SVG stroke widths vary, but this is not enough evidence of a visible defect; no library migration or broad icon rewrite is justified.
- Existing card borders communicate structure/selection; no blanket replacement with shadows is proposed. Image outlines and optical nudges are not established defects without surface-specific evidence.

Runtime command: `python /tmp/lenslet-jaku-writing/theme_probe.py`, Chromium 1440×960, existing synthetic read-only demo at localhost:7095. Waited one second for settling, opened Settings (Original), selected Charcoal, captured transitionrun events. Result: 205 transitions (42 background-color, 152 border colors, 10 color, 1 box-shadow). Evidence: `/tmp/lenslet-jaku-writing/theme-result.json`, `/tmp/lenslet-jaku-writing/gallery-charcoal.png`. Other runtime failure branches and slowed animations: **Not verified**. No source/build/git changes were made during this audit phase.

Verdict: **Block** for the inspected recovery gaps. This does not imply complete accessibility/layout/contrast coverage.

## Implementation tracking

Root authorized WP-04 shared theme suppression and WP-01 real Metrics/Derived recovery. Main application callback threading is coordinated with the layout agent; tree recovery is forwarded to the tree/performance agent. Validation and disposition will be updated after implementation.

### Implemented in the shared source paths

- WP-01: `FacetStatus` reuses the fixed error body in metric/categorical cards and exposes **Retry values**. MetricsPanel and DerivedScorePanel accept one refetch callback from the existing metrics-population query. Derived uses its existing status slot and retains its terminal error while a retry is pending. No page reload, new per-card query, draft reset or added transient layout row. Integrated failure/recovery browser evidence is assigned to the shared refinement probe.
- WP-02: tree owner implemented a query-scoped Retry on the existing failed child row; see performance/tree audit for verification.
- WP-03: centralized decode-error summary now reads “The browser could not read this image. Open another image, or check the source file.” Retryability remains unchanged.
- WP-04: centralized theme application suppresses CSS transitions only for the token swap and restores existing interaction feedback on the next frame. Rapid swaps share one temporary style and cancel superseded cleanup.
- WP-05: grid status now distinguishes empty unfiltered folders, filtered results, text-search results and similarity results. Each message names an appropriate existing exit; updating copy describes the retained view without backend jargon. AppShell supplies actual active-filter state; asynchronous presentation ownership is unchanged.
- WP-06: both conflict surfaces use **Save mine** / **Use latest**. The notes banner states “Use latest discards your edits”; button titles explain replacement/discard scope. Workflow inspection confirmed Save mine replays only pending conflict fields, while Use latest replaces the local notes/tags/rating draft with latest saved values. Existing request/conflict probe selectors were updated to match the new labels.
- WP-07: **Load metadata** replaces shorthand; empty Metrics copy uses **numeric or categorical fields**.

### Focused verification after implementation

- `npm --prefix frontend test -- src/theme/__tests__/runtime.test.ts src/features/metrics/__tests__/MetricsPanel.test.tsx src/features/metrics/components/__tests__/StableMetricCards.test.tsx src/features/metrics/components/__tests__/MetricRangePanel.test.tsx src/app/model/__tests__/loadingState.test.ts src/features/inspector/sections/__tests__/metadataSections.test.tsx src/lib/__tests__/mediaResourceState.test.ts`: **50 tests passed across seven files**.
- `cd frontend && npx tsc --noEmit`: **passed**.
- Source runtime Vite at localhost:7114, proxying the synthetic read-only gallery: theme switch now produces **zero page token transitions** (one unrelated hover transition on the settings trigger). `/tmp/lenslet-jaku-writing/theme-result-after.json`.
- Rapid Charcoal→Teal→Original in one task: one suppression style during swap, zero afterward, zero transitionrun events; `.btn` timing restored to `0.12s, 0.12s`. `/tmp/lenslet-jaku-writing/theme-rapid-after.json`.
- Actual Inspector section rendering at 280px width: Notes conflict slot client/scroll height **80/80px**; rating conflict slot **48/48px**; buttons remain inside their reserved shells. Evidence scripts and screenshots under `/tmp/lenslet-jaku-writing/`.

The initial **Block** describes the pre-implementation audit. Copy/theme findings are addressed; final approval for Metrics recovery and integrated gallery behavior depends on the main session's rebuilt acceptance/painted-frame checks. No ranking source was changed.

### Integrated conflict correction

The full packaged Inspector gate exposed a real rating-conflict overflow that the isolated 280px section check missed: the actual Inspector content inset left less inline space, and the flex-wrapping label/button group pushed both action buttons outside the fixed 48px slot. The slot itself and following sections stayed fixed, so the outer-geometry-only observation was insufficient.

`BasicsSection` now lays out that status with a two-column grid: a wrapping, compact label and one unwrapped action group. The existing 48px reserve, complete **Save mine** / **Use latest** labels and shared button styles remain. The actual `exercise_inspector_conflict_regions` probe, using a fresh synthetic gallery and real intercepted HTTP409 annotation responses against current source, passed with both `controlsBounded` and `contentBounded` true, no section shifts, and no violations at an actual 280px Inspector width. Notes conflict and failed multi-sidecar editing also passed. Evidence: `evidence/conflict-recovery.json`. Focused metadata-section tests: 12 passed. The final packaged gate must be rerun after build5.
