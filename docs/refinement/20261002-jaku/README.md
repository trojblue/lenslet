# Lenslet refinement project

Started 2026-10-02. Base: `122df55`. Branch: `feat/jaku-frontend-refinement`.

## Objective

Improve frontend usability, aesthetics and speed using the local Jaku skills at
`/fsx/yada/dev_docs/jaku_skills`. Preserve Lenslet's compact image-review workflow
and the canonical [presentation contract](../../DESIGN_SYSTEM.md). Replace shared
causes rather than layering isolated visual patches. The preceding motion refresh
is the starting point.

User scope clarification: ranking is excluded. All investigation and implementation
effort targets the main gallery, search, folders, Inspector, metrics, Viewer and
Compare. Shared infrastructure may incidentally benefit ranking; no ranking-specific
audit, design or feature work is planned.

## Working method

The main session owns prioritization, integration, commits and final validation.
Specialist agents first collect evidence, then receive exclusive implementation
scopes. Source changes use the existing React, CSS/Tailwind and Python architecture.
No new UI framework or animation dependency is planned.

| Workstream | Owners and evidence |
| --- | --- |
| Accessibility | Jaku `better-accessibility`; [audit](audits/accessibility.md) |
| Layout and usability | Jaku `better-layout`; [audit](audits/layout.md) |
| Typography and colors | Jaku `better-typography`, `better-colors`; [audit](audits/visual.md) |
| Writing and polish | Jaku `better-writing`, `better-ui`; [audit](audits/writing-polish.md) |
| Frontend performance | Measured startup, rendering and interaction costs; [audit](audits/performance.md) |
| Delivery and test infrastructure | Asset/media delivery and reliable browser gates; [audit](audits/delivery.md) |

Jaku `better-interface` coordinates domain severity and the consolidated review.
Its 15-finding cap applies to the consolidated review; supporting investigations
retain evidence. The procedure skills `variant`, `break`, `explain-interface` and
`interface-review` are evaluated for relevance, not used to create speculative
variants or unrelated throwaway pages. UI UX Pro Max and UI UX Architect are
excluded at the user's request.

## Phases

1. Establish source and rendered baselines, domain coverage and speed measurements.
2. Consolidate root causes and assign disjoint implementation batches.
3. Fix foundational accessibility/layout problems and measured performance costs.
4. Refine shared typography, color, surfaces and product copy.
5. Review the integrated interface across themes, viewports and input methods.
6. Build and mirror shipping assets; run tests, browser acceptance, continuity,
   performance checks and repository lint; record limitations honestly.

## Verification contract

- Synthetic datasets only; user datasets remain read-only.
- Preserve settled content, drafts, decoded identity and immediate utility surfaces.
- Measure speed before/after on the same fixture and procedure. Separate production
  bundle costs from dev tooling, network variability and cold/warm cache behavior.
- Browser checks include desktop, 320/390px layouts, keyboard and reduced motion.
- Shared primitive changes require full frontend tests and TypeScript.
- Rebuild and mirror packaged assets before final browser acceptance.
- Existing failing probes must be diagnosed, not weakened to obtain a pass.
- Only the main session builds/mirrors shared output and commits integration batches.

## Status

Completed on 2026-10-02. The main-gallery implementation, independent review,
production build and required acceptance/continuity gates passed. Ranking was not
changed intentionally; its generated chunk was regenerated with shared dependencies.

The 40,000-image / 10,000-folder paired benchmark reduced median first-grid time
from 4.576s to 0.477s and mean scrolling frame gap from 295.36ms to 18.11ms.
See [performance evidence](audits/performance.md) for cache conditions and limits.

[execution.md](execution.md) records implementation batches and the final validation
matrix. [review.md](review.md) consolidates findings, remedies and coverage limits.
The reports remain a dated evidence record; `docs/DESIGN_SYSTEM.md` governs behavior.
