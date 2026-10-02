# Consolidated interface review

Scope: Lenslet gallery, navigation, Inspector, metrics, Viewer and Compare;
shared styling, controls and frontend delivery. React 18, Vite, CSS/Tailwind and
existing Lucide icons. Conventions: repository `AGENTS.md`, `DEVELOPMENT.md` and
`docs/DESIGN_SYSTEM.md`.

Ranking is excluded by the user's scope clarification.

## Coverage

| Domain | Evidence inspected | Result |
| --- | --- | --- |
| Accessibility | Shared controls, modal/menu ownership, Viewer/Compare, Similarity fields, Inspector metadata; keyboard and AX probes | Implemented; integrated keyboard/menu checks passed |
| Layout | Gallery/Viewer at 11 widths from 320 to 1920px, phone and short-height tool panes, zoomed menus | Implemented; responsive and continuity checks passed |
| Writing | Error/empty/loading branches, conflicts, metric recovery and metadata actions | Shared recovery and copy fixes implemented |
| Typography | Numeric values, wrapped Settings descriptions, narrow controls and long labels | Tabular numbers, readable leading and mobile input sizing |
| Colors | Actual selected foreground/background pairs in Original, Teal and Charcoal | Previously failing pairs now at least 4.5:1 in measured states |
| UI polish | Shared motion, theme changes, control geometry, surface boundaries | Preserved motion system; theme transition storm removed |

## Findings

The table records the confirmed baseline findings and implemented remedies. It is
supported by the final validation matrix below. Domain reports retain
source locations, screenshots and narrower coverage limits. Speed and delivery
findings are in the [performance](audits/performance.md),
[metrics](audits/metrics-performance.md), [media](audits/media-cache.md) and
[delivery](audits/delivery.md) reports.

| Severity | Domain | Location | Before | After | Why |
| --- | --- | --- | --- | --- | --- |
| HIGH | Layout | `frontend/src/app/layout/responsiveLayoutPolicy.ts:157` | Phone and short-height pane controls could not reveal tools | Explicit transient sheets reuse the mounted pane | Folders, Metrics, Derived and Inspector must remain reachable |
| HIGH | Accessibility | `frontend/src/accessibility.css:3` | Component input resets erased keyboard focus | Shared visible native focus, including forced colors | Search and other controls need a visible keyboard location |
| HIGH | Accessibility | `frontend/src/shared/hooks/useModalFocusTrap.ts:115` | Modal background, portaled menus and Escape had inconsistent ownership | Shared topmost scope, reversible inert state, explicit popup ownership and return focus | Keyboard and pointer access must match actual modal presentation |
| HIGH | Accessibility | `frontend/src/features/compare/CompareViewer.tsx:619`; `frontend/src/features/inspector/sections/MetadataSection.tsx:95` | Split/resize and metadata-copy actions had pointer-only paths | Keyboard split/rail controls, native JSON-key buttons and focusable metadata region | Core inspection actions must work without a pointer |
| HIGH | Accessibility | `frontend/src/features/embeddings/SimilarityModal.tsx:253` | Form fields lacked connected labels and field-owned validation | Bound labels, invalid state, described errors and focus | Similarity search must expose understandable controls and recovery |
| HIGH | Colors | `frontend/src/theme/runtime.ts:26` | Solid accent reused as text, muted text and counts fell below required contrast | Readable accent-text role, measured muted tokens and full-opacity counts | Selected controls and navigation data must remain legible |
| HIGH | Layout | `frontend/src/app/menu/ContextMenu.tsx:39` | Menu maximum height followed layout viewport at high zoom | Fixed positioning and visible-viewport height with internal scrolling | Last menu actions must remain reachable at high zoom |
| HIGH | Writing | `frontend/src/features/metrics/components/FacetStatus.tsx:18` | Failed facets and folders offered no direct recovery | Retry through existing query owners; clear nonretryable media guidance | A temporary failure must not strand the workflow |
| MEDIUM | Layout | `frontend/src/app/layout/responsivePanels.css:49` | Touch slots overlapped; scope title collapsed; warning dismiss could scroll away | Actual target footprints, useful title allocation and bounded status copy | Dense chrome still needs clear, separate controls |
| MEDIUM | Layout | `frontend/src/shared/ui/Toolbar.tsx:555` | Search query survived a breakpoint while its input displayed empty | Desktop and mobile inputs share immediate query text | The visible field must represent the active query |
| MEDIUM | Writing | `frontend/src/app/model/loadingState.ts:79`; Inspector conflict sections | Empty states confused causes; conflict labels hid consequences | Query-aware empty guidance and consistent Save mine / Use latest actions | Users need to understand state and the effect of their next action |
| MEDIUM | UI polish | `frontend/src/theme/runtime.ts:178` | One theme switch fired 205 cosmetic transitions | Atomic token swap temporarily suppresses transitions | Theme changes should settle together while normal interaction motion remains |

## Verification

Final integration passed 719 tests across 124 frontend test files, TypeScript,
full browser acceptance, all four standard painted-frame scenarios (toolbar,
grid, Inspector and Metrics), normal/reduced-motion probes, the focused gallery
regression probe, and the 40k-image large-tree gate. The virtual tree also passed
the cold-response-completing-while-hidden test from the earliest return frame.
See [execution.md](execution.md) for the build-specific evidence matrix.

Verdict: the confirmed findings above are addressed and the tested main-gallery
flows are ready for review. Independent source/browser review found no unresolved
confirmed regression. Actual screen-reader speech and Safari-specific rendering
have not been tested. Chromium AX and keyboard checks are supporting evidence,
not substitutes. Performance measurements use synthetic local fixtures; remote
storage latency and large photographic images need separate workload measurements.
