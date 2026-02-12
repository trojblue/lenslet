# UI Coherence Refinement Plan (Warm Background + Cool Blue)

This plan focuses on reducing UI clutter and restoring visual coherence after recent feature additions, while preserving the existing warm background + cool blue accent direction outlined in `docs/20260110_ui_ux_warmth_performance.md`.

## Purpose / Big Picture

Lenslet’s UI has grown quickly (sync indicator, richer metrics, inspector upgrades, banners). The goal of this pass is to make the interface feel intentional again: fewer visual “styles,” consistent spacing, and a single clear hierarchy. This is a dark‑only tool UI with warm neutrals and a cool blue accent. Performance remains a top constraint.

## Inputs and References

- Baseline warm theme and performance guardrails: `docs/20260110_ui_ux_warmth_performance.md`
- Recent UI additions: sync indicator + status card, metrics refinements, inspector expansions
- UI/UX guidance (ui-ux-pro-max search): data‑dense + minimal dark dashboards, minimize glow/visual noise, maintain touch target spacing (>= 8px gaps), preserve readability in dark mode

## Current Audit (What Feels Cluttered / Inconsistent)

Observed in current code:

1) **Metrics panel density + control consistency**
   - `frontend/src/features/metrics/MetricsPanel.tsx`: input controls for numeric range use default browser spinner; text sizes and spacing differ across sub‑panels.
   - Multiple micro‑sizes (`text-[11px]`, `text-xs`, `text-sm`) and padding choices make the panel feel busy.
   - Histogram card + range controls + selected metrics all stack with similar visual weight; hard to scan.

2) **Form controls and inputs**
   - Inputs/selects across the app are inconsistent: some use `.input`, some custom `h-8 px-2.5`, others default `select` styles.
   - Number inputs (metrics + dimensions) inherit native spinners, which stand out against the custom dark UI.

3) **Toolbar + status surfaces**
   - Toolbar now hosts nav + panel toggles + sync indicator + search; the hierarchy feels flat.
   - The new sync card is strong visually; banners in StatusBar can still compete for attention.

4) **Inspector information density**
   - Inspector has multiple sections, but headings, spacing, and inline controls vary in size and weight.
   - JSON highlighting uses hard‑coded colors that do not align with theme tokens.

5) **General style drift**
   - Rounded corner sizes vary (`rounded-md`, `rounded-lg`, `rounded-xl`) without clear pattern.
   - Some text headings use uppercase tracking, some don’t; card headers feel inconsistent.

## Design Direction (Keep Existing Theme, Remove Visual Noise)

- Keep warm background neutrals with cool blue accent; avoid new color families.
- Prioritize data‑dense readability: tighter vertical rhythm, but with consistent “air” between blocks.
- Reduce surface contrast jumps; unify card/panel styles.
- Ensure interactive elements are visually consistent and clearly tappable.

## Strategy

### 1) Define a small UI foundation (tokens + base classes)
Goal: Make new UI pieces look like part of the same system.

Plan:
- Create base CSS utilities for:
  - **Card containers** (padding, border, radius, background)
  - **Section headings** (size, tracking, color)
  - **Inputs / selects / number fields** (height, radius, background)
  - **Inline labels and metadata rows** (muted + monospace pattern)
- Standardize radius usage: pick one primary radius (e.g., 10px) + one secondary.
- Add consistent spacing scale for panels (e.g., 8px, 12px, 16px).

### 2) Metrics panel cleanup (highest clutter density)
Goal: Reduce visual noise and align controls with the rest of the UI.

Plan:
- Replace native number spinners with custom styling (hide default spinners, use consistent field appearance).
- Tighten typography: move all panel subtitles to the same size and weight.
- Introduce a compact “metrics control row” layout with aligned label/control pairs.
- Update histogram labels and range controls to share one typography scale.
- Reduce repeated headers (e.g., “Metric”/“Selected metrics” spacing) by standardizing section headings.

### 3) Inspector alignment
Goal: Make the inspector look like a cohesive panel rather than a stack of different sections.

Plan:
- Normalize section heading style + spacing.
- Convert JSON highlighting colors to theme tokens.
- Align key/value rows with consistent spacing and use shared components where possible.
- Ensure copy‑to‑clipboard affordances have consistent hover treatment.

### 4) Toolbar + banner hierarchy
Goal: Maintain quick access while restoring clarity.

Plan:
- Reduce visual competition: adjust sync indicator card and banner weights so the toolbar feels primary.
- Ensure search, panel toggles, and sync indicator share a common sizing baseline.
- Minimize redundant status messaging (sync card + recent update banner) via spacing and subdued tone.

### 5) Final coherence pass
Goal: One system, not multiple stacked feature layers.

Plan:
- Scan for inconsistent text sizes/spacing in:
  - `Toolbar.tsx`, `StatusBar.tsx`, `SyncIndicator.tsx`
  - `MetricsPanel.tsx`, `Inspector.tsx`
- Replace ad‑hoc class sets with the new base utility classes.
- Verify mobile layout and ensure spacing between touch targets >= 8px.

## Implementation Plan (Phased)

**Phase A — Foundations (CSS tokens + base classes)**
- Add consistent card/section/input classes in `frontend/src/styles.css`.
- Establish radius + spacing constants (document in CSS comments or `theme.css`).

**Phase B — Metrics Panel Refinement**
- Replace number input spinners and unify control styling.
- Reduce header redundancy and align histogram section typography.
- Introduce compact layout for range controls.

**Phase C — Inspector Refinement**
- Replace hardcoded JSON colors with theme tokens.
- Normalize spacing and heading hierarchy.
- Align copy affordances and monospace blocks.

**Phase D — Toolbar + Status**
- Normalize size and spacing for toolbar controls.
- Subdue banners and ensure they don’t overpower the toolbar.

**Phase E — QA and Performance**
- Verify no new expensive effects or layout thrash.
- Check large dataset scrolling and selection remain smooth.

## Acceptance Criteria

- Metrics panel feels compact, tidy, and consistent with other panels.
- Inputs across the app share the same visual styling (including number fields).
- Inspector sections read like a single designed panel, not stitched components.
- Toolbar and banners no longer compete visually; hierarchy is clear.
- Warm background + cool blue accent remain intact.

## Affected Files (Expected)

- `frontend/src/styles.css`
- `frontend/src/theme.css`
- `frontend/src/features/metrics/MetricsPanel.tsx`
- `frontend/src/features/inspector/Inspector.tsx`
- `frontend/src/shared/ui/Toolbar.tsx`
- `frontend/src/app/components/StatusBar.tsx`
- `frontend/src/shared/ui/SyncIndicator.tsx`

## Notes

- Keep all changes lightweight: no new heavy animations or layout‑expensive effects.
- Avoid broad refactors; focus on local cleanup and shared styling utilities.
- This plan is intentionally UI‑only and should not affect backend behavior.
