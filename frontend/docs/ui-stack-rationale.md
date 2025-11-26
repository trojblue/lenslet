# UI Stack Rationale: Tailwind CSS + Radix UI

This document explains **why** we may adopt Tailwind CSS and Radix UI in this project and **how** to do it in a way that keeps the app lean, fast, and minimal.

The goal is to improve developer experience, consistency, and accessibility without turning the project into a heavy, over‑abstracted frontend.

---

## Why Tailwind CSS

Tailwind CSS is a utility-first CSS framework. It does **not** prescribe a visual style; it provides composable utility classes (spacing, layout, typography, colors) that we can tune to our existing look.

Benefits:
- Faster iteration: layout, spacing, and small visual tweaks can be done in JSX instead of jumping between CSS files.
- Consistency: shared spacing/typography scales reduce one-off values and “magic numbers”.
- Less custom CSS: over time, most handcrafted rules and one-off classes can disappear.

Risks / constraints:
- ClassName bloat: JSX lines can get long if we are not disciplined.
- The “Tailwind look”: if we keep default colors and radii, UI can drift toward generic Tailwind UI aesthetics.

Mitigations:
- Configure Tailwind tokens (colors, font sizes, radii, shadows) to match our existing design instead of using defaults.
- Keep a thin layer of component-level primitives (e.g., `Button`, `Input`, `Panel`) that encapsulate common Tailwind class combinations to avoid repetition.
- Avoid adding Tailwind plugins unless they clearly pay for themselves; prefer core utilities.

---

## Why Radix UI

Radix UI provides **headless**, accessible components for common interactive patterns: dialogs, dropdown menus, popovers, tooltips, sliders, etc.

Benefits:
- Accessibility out of the box: ARIA roles, keyboard navigation, focus management, escape handling, and portaling are handled for us.
- Headless by design: no bundled styling or opinionated layouts, so we retain full control over the visual design.
- Composability: primitives can be used to build more complex patterns (e.g., nested menus, non-trivial dialogs) without re-implementing low-level behavior.

Risks / constraints:
- Extra JSX structure: components like dialogs and dropdown menus use nested primitives, which can make markup a bit more verbose.
- Dependency surface: we depend on Radix’s APIs and release cycle for these primitives.

Mitigations:
- Use Radix **selectively**: only where accessibility and complex behavior are hard to get right by hand (dialogs, menus, popovers, tooltips, sliders), not everywhere.
- Wrap Radix primitives in thin local components (e.g., `AppDialog`, `AppContextMenu`) so that usage across the app is consistent and changes can be centralized.

---

## Principles for Keeping the Project Lean

If we adopt Tailwind and Radix, we want to preserve the original goals of this project:
- Minimal infra and small bundle.
- Clear, explicit behavior over framework magic.
- Easy to extend without committing to a heavy design system.

Guiding principles:
- **No design system big-bang rewrite.** Tailwind and Radix should be introduced incrementally, starting with high-impact surfaces.
- **Prefer composable primitives over many bespoke components.** Keep a small set of shared building blocks and reuse them.
- **Avoid new UI kits.** Tailwind + Radix should replace the need for a full component library (no MUI/Chakra/etc.).
- **Measure impact.** When possible, compare bundle size, performance, and perceived responsiveness before and after changes.

---

## Tailwind: Migration Strategy

The Tailwind migration should focus on **utility-first styling** and **gradual CSS reduction**, not a full reskin.

High‑level steps:
- Add Tailwind to the build (Vite + PostCSS) and configure a minimal `tailwind.config` that mirrors our current typography, colors, and spacing.
- Introduce Tailwind primarily for:
  - Layout (flex/grid, gaps, responsive breakpoints).
  - Spacing and sizing (margin, padding, width/height).
  - Typography (font sizes, weights, line-height, truncation).
  - Common “frame” elements (panels, toolbars, headers, overlays).
- Migrate styles incrementally:
  - When touching a component, consider replacing local CSS rules with Tailwind classes.
  - Avoid re-creating complex components just for the sake of Tailwind; stick to opportunistic migration.
- Retain a small amount of global CSS for:
  - CSS variables (e.g., theme tokens).
  - Truly global rules (body background, base font, scroll behaviors).

What should change conceptually:
- Shift from many named CSS classes to more direct, utility-based styling in JSX.
- Use a limited set of “design tokens” defined in Tailwind config rather than ad hoc values.
- Define a couple of low-level UI primitives (button-like controls, panels, form fields) built with Tailwind and reuse them instead of bespoke styling each time.

---

## Radix UI: Migration Strategy

Radix should be introduced where it brings clear value in behavior and accessibility.

High‑level steps:
- Identify interactive patterns that are hard to implement correctly by hand:
  - Dialogs / modals.
  - Menus and context menus.
  - Popovers/tooltips with proper focus handling.
  - Sliders or range controls, if needed.
- For each pattern, replace the bespoke implementation with Radix primitives while preserving:
  - The existing interaction model (keyboard shortcuts, context menu triggers, etc.).
  - The visual appearance (via our own Tailwind or CSS classes).
- Wrap Radix primitives in app-specific components:
  - Example: an `AppDialog` that wires up `Dialog.Root`, `Dialog.Trigger`, `Dialog.Content`, and applies a consistent layout and animation via Tailwind.
  - Example: an `AppContextMenu` that uses `ContextMenu.Root` and `ContextMenu.Item` but keeps current menu item semantics and shortcuts.

What should change conceptually:
- Move focus/escape/ARIA logic from custom event handlers into Radix primitives.
- Treat Radix as the source of truth for interactive accessibility patterns, while keeping our own visual styling layer.
- Keep the use of Radix localized and well-documented so it is easy to understand and adjust.

---

## Combining Tailwind + Radix

Tailwind and Radix complement each other:
- Tailwind handles layout and visual styling.
- Radix provides accessible structure and behavior.

Patterns to aim for:
- Use Radix primitives for complex interactions, styling them via Tailwind utility classes on the rendered elements.
- Create a small set of reusable components (e.g., dialog shell, menu, tooltip) that combine Radix behavior with Tailwind styling.
- Avoid exposing low-level Radix primitives everywhere; most of the app should use the thin wrappers to keep markup readable and consistent.

---

## Long-Term Goals

If the migration is successful, the UI layer should:
- Have fewer custom CSS rules and more consistent styling via Tailwind.
- Use Radix for any non-trivial interactive component where accessibility matters.
- Remain small, understandable, and easy to extend without feeling like a heavy design system.

Future contributors should:
- Reach for Tailwind utilities and shared primitives first when changing the UI.
- Use Radix-based wrappers for dialogs, menus, and popovers instead of rolling their own behaviors.
- Respect the original minimal, performance-focused philosophy of the project while benefiting from more modern, ergonomic tooling.

