# UI/UX Warmth + Performance Pass (Dark-Only ML Dataset Viewer)

This ExecPlan is a living document. The sections `Progress`, `Surprises & Discoveries`, `Decision Log`, and `Outcomes & Retrospective` must be kept up to date as work proceeds.

If a PLANS.md file is checked into the repo, this document must be maintained in accordance with it.

## Purpose / Big Picture

Make the UI feel less cold while preserving the “tool” vibe and keeping performance as the top priority. This is a dark-only product; avoid light mode complexity. The emphasis is on subtle warmth, stronger hierarchy, and smoother workflows (filters/selection/viewer) without adding expensive visual effects.

User-visible proof: the UI feels calmer and more cohesive, key actions are easier to discover, and performance is unchanged (virtualized grid stays snappy on 1k–100k items).

## Progress

- [ ] (2026-01-10) Plan drafted; implementation not started.

## Surprises & Discoveries

- None yet. Update this section with concrete evidence if unexpected behavior appears.

## Decision Log

- Decision: Dark-only design (no light mode).
  Rationale: Reduce complexity; align with tool usage and performance focus.
  Date/Author: 2026-01-10 / Assistant + User

- Decision: Prefer CSS token tuning and minimal layout tweaks over new heavy components.
  Rationale: Preserve performance and avoid large refactors while improving feel.
  Date/Author: 2026-01-10 / Assistant + User

- Decision: No heavy effects (no blur, glass, or large shadows); avoid expensive animations.
  Rationale: Performance-first; keep GPU overhead minimal.
  Date/Author: 2026-01-10 / Assistant + User

## Outcomes & Retrospective

- Not started. Update after execution.

## Context and Orientation

Key UI surfaces:
- Toolbar: `frontend/src/shared/ui/Toolbar.tsx`
- App layout + state: `frontend/src/app/AppShell.tsx`
- Viewer: `frontend/src/features/viewer/Viewer.tsx`
- Theme tokens: `frontend/src/theme.css`
- Core styles: `frontend/src/styles.css`
- Grid: `frontend/src/features/browse/components/VirtualGrid.tsx`
- Inspector panel: `frontend/src/features/inspector/Inspector.tsx`

Current baseline:
- Dark theme with solid panels and borders.
- Toolbar is dense; filters are in a dropdown.
- Viewer uses an emoji close icon.
- Virtual grid handles large datasets; must remain performant.

## Plan of Work

### Phase 1: Theme warmth & visual hierarchy (CSS-only, low risk)

Goal: Reduce “cold” feel with warmer neutrals, refined contrast, and subtle depth without adding performance costs.

Work:
1) Update tokens in `frontend/src/theme.css`:
   - Slightly warm the background and panel neutrals.
   - Increase text hierarchy contrast (primary vs secondary vs muted).
   - Add a warm accent token (used sparingly for selection/primary actions).
2) Adjust button + surface states in `frontend/src/styles.css`:
   - Consistent hover/active states with soft contrast shifts.
   - Slightly rounded corners where needed for a calmer feel.
3) Add a subtle background gradient or vignette on the app shell (no blur).

Acceptance:
- UI feels less harsh; contrast remains clear.
- No layout changes; zero impact on rendering performance.

### Phase 2: Toolbar clarity & filter visibility (layout alignment)

Goal: Improve scanning and reduce control density without refactoring core behavior.

Work:
1) Toolbar regrouping in `frontend/src/shared/ui/Toolbar.tsx`:
   - Left: dataset name/breadcrumb + item count.
   - Center: search.
   - Right: sort/layout + filters + view controls.
2) Add a persistent filter chip row under the toolbar in `frontend/src/app/AppShell.tsx`:
   - Show active filters and one-click clear.
   - Keep chips lightweight (no heavy animations).

Acceptance:
- Users can see active filters without opening a dropdown.
- Toolbar feels less cramped while retaining current actions.

### Phase 3: Viewer polish (consistency + flow)

Goal: Keep the viewer fast but more refined.

Work:
1) Replace emoji close with SVG icon in `frontend/src/features/viewer/Viewer.tsx`.
2) Optional: small “prev/next” affordances with minimal UI (no filmstrip).
3) Tighten focus/hover feedback for viewer controls.

Acceptance:
- Viewer feels consistent with the rest of the UI and remains responsive.

### Phase 4: Inspector structure (readability, not complexity)

Goal: Improve metadata scanning without adding heavy UI.

Work:
1) Group inspector sections (Basics, EXIF, Metrics, Notes) in `frontend/src/features/inspector/Inspector.tsx`.
2) Optional: collapsible cards with simple CSS transitions (opacity/height).

Acceptance:
- Large metadata panels are easier to scan.
- No extra data fetching or heavy animations.

### Phase 5: Performance guardrails & QA

Goal: Ensure UI changes do not affect performance or memory.

Work:
1) Verify grid virtualization behavior remains unchanged.
2) Avoid new render-heavy states; keep new UI state local and minimal.
3) Check for layout thrash in toolbar/chips/inspector.

Acceptance:
- Scrolling and selection performance unchanged.
- No new layout jank on large datasets.

## Validation and Acceptance

- UI feels warmer without becoming “decorative.”
- Active filters are visible and easy to clear.
- Viewer controls are consistent and non-distracting.
- No performance regressions in the grid or viewer.

## Idempotence and Recovery

- Theme changes should be reversible via token edits only.
- Layout changes should not affect stored user preferences.
- No changes to server behavior or storage.

## Interfaces and Dependencies

Frontend-only:
- `frontend/src/theme.css`, `frontend/src/styles.css`
- `frontend/src/shared/ui/Toolbar.tsx`
- `frontend/src/app/AppShell.tsx`
- `frontend/src/features/viewer/Viewer.tsx`
- `frontend/src/features/inspector/Inspector.tsx`

No backend changes expected.

## Future Expansion Guardrails (Do / Don’t)

Do:
- Keep changes lightweight and reversible.
- Maintain strong hierarchy and clear action affordances.

Don’t:
- Don’t add glass/blur or heavy shadows.
- Don’t introduce light mode or new data fetching logic.

---

Change note (required for living plans): This plan targets a dark-only UI warmth pass with minimal layout refinements while preserving performance.
