# Lenslet Presentation Continuity Contract

This document defines Lenslet's rendering-stability rules. It is intentionally
narrow: existing components, colors, spacing, and typography remain the visual
system. The contract governs how those components present changing state.

The evidence and finding IDs referenced below come from
`docs/20260718_frontend_ui_instability_observations.md`. Findings described as
evidence-gated receive behavior code only after their focused trace reproduces
the problem.

The rule-to-evidence map is: R1 covers UI-01, UI-02, UI-07, UI-15, and UI-17;
R2 covers UI-03 and UI-04; R3 covers UI-06, UI-13, and UI-14; R4 covers UI-09
and UI-10; R5 covers UI-12 and the utility-surface findings UI-20 through UI-23
plus UI-25;
R6 covers UI-11; R7 covers UI-13 through UI-17 plus UI-19 through UI-23 and
UI-25; and
R8 covers UI-18 and UI-24. UI-28 follows R2 settled-identity ownership. UI-05,
UI-18, UI-24, UI-26, and UI-27 are explicitly evidence-gated by the execution
plan.

## State and geometry rules

### R1 — Transient content does not create layout rows

Status, diagnostics, counts, selection details, cursor values, and actions must
replace content inside a permanently reserved slot or use an overlay. They must
not mount a new row that moves the control or the next card. Long content stays
available through an accessible title, description, disclosure, or bounded
internal scrolling rather than expanding a primary anchor without limit.

### R2 — One settled identity owns a browse presentation

Membership, the visible window, query-owned totals and rating aggregates, and
metric-rail readiness commit together. A target query may not publish its
empty defaults beside retained membership from a previous settled query.
Same-identity mutable annotations remain live and are not copied into the
settled snapshot.

### R3 — Pending, absent, empty, and failed are distinct

A requested target is pending until it reaches a terminal result. Pending must
not be presented as absent, idle, empty, zero, or failed. A true empty or error
state appears only when the active target settles with that result. Inspector
Metadata with autoload disabled may truthfully present `Load meta` and
`PNG metadata not loaded yet`; autoload-enabled targets may not.

### R4 — Persisted and responsive truth is available before paint

Validated persisted settings and viewport-dependent structure must be read by
the first render that uses them. URL and shared-view state keep their existing
precedence. An effect may persist or subscribe to state, but it must not repair
the first visible frame.

### R5 — Frequent utility surfaces are fully painted when visible

Dropdowns, menus, and other frequent utility panels must not mount from
opacity zero. Their first visible frame is opaque, clamped to the viewport, and
uses a stable trigger and content shell. Motion that remains must respect
`prefers-reduced-motion` and must not be required to understand state.

### R6 — App-owned controls own frequent popup presentation

Frequently used select-like controls use Lenslet's app-owned Dropdown so the
closed trigger and open surface share geometry, theme, keyboard behavior, and
ARIA semantics. Native controls remain only where the plan explicitly keeps
them or where a focused reproduction does not justify a cutover.

### R7 — Async states retain one control role and outer shell

Pending, empty, error, and ready states for a field keep the same outer
rectangle and semantic control role. Async hydration must not replace an input
with a dropdown or a compact message with an unbounded plot. Intentional
scrolling belongs inside the stable shell.

### R8 — Decoded media and visible labels share one identity

New labels may appear only with decoded pixels for the same resource identity.
If old media is retained while a target loads, its old labels are retained too
and the presentation is explicitly transitioning. Superseded or failed loads
cannot promote, and object URLs/caches remain bounded and retired.

## Approved timing contracts

- Browse presentation keeps the previously settled identity for at most
  800 milliseconds while a compatible target is pending. Retained browse
  actions are inert and expose `aria-busy`. Incompatible source, table,
  workspace, or session changes invalidate retention immediately.
- Inspector Metadata projects target-owned pending synchronously when autoload
  is enabled. Fast requests swap directly to settled content. Neutral visible
  loading copy is withheld until 1,000 milliseconds; this exception does not
  change the 800-millisecond token used by other approved fallback suppression.
- Any new visible timing token requires explicit approval and measured browser
  evidence.

## Stable slot contract

A stable slot has an invariant outer size for its supported states. Content may
be disabled, visually quiet, replaced in place, clipped with accessible full
text, or internally scrollable. `display: none`, conditional margins, wrapping
new flow rows, and zero-height “reserves” do not satisfy this contract.

The metrics cards therefore keep card-local Clear in an always-present action
slot, remove redundant `Active:` copy, and keep histogram range/cursor guidance
in one fixed-height no-wrap information slot. The gallery top stack uses one
real reserved line rather than flow-inserting transient bands.

## Accessibility and verification

Stable presentation must preserve keyboard operation, focus continuity,
programmatic names, ARIA state, and accessible full text. Color or opacity alone
must not communicate state. Reduced-motion users receive no essential motion,
and removing entrance motion must not remove focus or state feedback.

Painted browser frames are authoritative for continuity. Named card, panel, and
next-control anchors may move by at most one CSS pixel unless a ticket records an
intentional internal-scroll exception. Final-DOM assertions, screenshots after
settling, and unit tests support but do not replace a failing painted-frame
trace.
