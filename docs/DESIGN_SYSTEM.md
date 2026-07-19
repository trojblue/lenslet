# Lenslet Design System: Presentation Continuity

This is the canonical design contract for Lenslet rendering stability. It is
intentionally narrow: existing components, colors, spacing, and typography
remain the visual system. The contract governs how those components present
changing state. Feature plans may add evidence and implementation detail, but
must not weaken these rules without updating this document explicitly.

The evidence and finding IDs referenced below come from
`docs/20260718_frontend_ui_instability_observations.md`. Findings described as
evidence-gated receive behavior code only after their focused trace reproduces
the problem.

The post-remediation audit in
`docs/20260719_frontend_ui_continuity_residual_audit.md` extends the evidence
from outer geometry to descendant content and decoded pixels. That audit is
diagnostic: this document remains the durable source of truth.

The rule-to-evidence map is: R1 covers UI-01, UI-02, UI-07, UI-15, and UI-17;
R2 covers UI-03 and UI-04; R3 covers UI-06, UI-13, and UI-14; R4 covers UI-09
and UI-10; R5 covers UI-12 and the utility-surface findings UI-20 through UI-23
plus UI-25;
R6 covers UI-11; R7 covers UI-13 through UI-17 plus UI-19 through UI-23 and
UI-25; and
R8 covers UI-18 and UI-24. UI-28 follows R2 settled-identity ownership. UI-05,
UI-18, UI-24, UI-26, and UI-27 are explicitly evidence-gated by the execution
plan. R9 applies the same settled-identity ownership to every asynchronous
target-owned surface, including Metrics, Derived, Inspector, tabs, hover
preview, Viewer, Compare, and ranking.

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

### R4 — Presentation-critical truth is available before paint

Validated persisted settings, viewport-dependent structure, active query
requirements, and target identity must be read by the first render that uses
them. This includes state inside lazy subtrees such as Inspector. URL and
shared-view state keep their existing precedence. An effect may perform I/O,
persist, or subscribe, but it must not restore visible state, discover a query
dependency, notify a parent of data required for the first visible render, or
otherwise repair an already-painted frame.

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

### R7 — Async states retain one control role, content slot, and outer shell

Pending, empty, error, and ready states for a field keep the same outer
rectangle and semantic control role. Async hydration must not replace an input
with a dropdown or a compact message with an unbounded plot. Intentional
scrolling belongs inside the stable shell. Stable geometry alone is
insufficient: ordinary refresh and navigation must not clear settled values,
hide actions, replace real rows with skeletons, or insert a mandatory loading
body before the next presentation is ready.

### R8 — Decoded media and visible labels share one identity

New labels may appear only with decoded pixels for the same resource identity.
If old media is retained while a target loads, its old labels are retained too
and the presentation is explicitly transitioning. Superseded or failed loads
cannot promote, and object URLs/caches remain bounded and retired. Retained
media keeps its presentation-owned transform and stable opacity; target
navigation must not dim, hide, reset, or refit the old pixels before atomic
promotion. Every navigable media surface decodes before reveal and respects
reduced motion.

### R9 — Requested and presented identities are separate

Every asynchronous target-owned surface tracks what the user requested
separately from what is currently presented. During a compatible transition
from settled identity A to target B, the visible surface remains one complete
snapshot of A until B has the minimum data and decoded resources needed for an
atomic promotion. Labels, selector values, rows, actions, counts, control
values, media, and transforms belong to the same presented identity.

A painted frame may therefore be wholly settled A or wholly settled B. It may
not combine B's label with A's values, B's filename with an empty thumbnail,
or a target-owned loading shell with otherwise retained settled content.
Retained controls are inert where acting on A would be unsafe and expose an
appropriate busy state. Rapid A-to-B-to-C transitions may promote only C.

An incompatible source, table, workspace, or session change is a hard reset
and does not retain A. A truly first-ever presentation may use a stable neutral
shell because no settled snapshot exists. Empty and error presentations remain
terminal target-owned results under R3.

## Approved timing contracts

Timing tokens control when fallback or status copy may become visible. They do
not authorize clearing settled content, mounting a blank frame, hiding an
action, replacing rows with skeletons, dimming retained media, or promoting an
undecoded image. If a compatible settled presentation exists, it remains the
presentation throughout the silent interval.

- Browse presentation keeps the previously settled identity while a compatible
  target is pending. For the first 800 milliseconds, no loading copy is shown;
  after that threshold a neutral status may appear only in its reserved slot
  without clearing the retained presentation. Retained browse actions are inert
  and expose `aria-busy`. Terminal success, empty, or error commits atomically.
  Incompatible source, table, workspace, or session changes invalidate
  retention immediately.
- Inspector Metadata projects target-owned pending synchronously when autoload
  is enabled while retaining one complete presented Inspector identity. Fast
  requests swap directly to settled content. Neutral visible loading copy is
  withheld until 1,000 milliseconds and occupies a reserved status location;
  this exception does not change the 800-millisecond token used by other
  approved fallback suppression.
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

Stable content slots follow the same rule. Count columns, action columns,
filename areas, async capability rows, and editable values keep their role and
footprint across pending and settled states. A neutral dash or an inert prior
value may replace content in place; removing the column or row does not satisfy
the contract.

## Visibility is not lifecycle

Switching a tab, collapsing a tool rail, closing a disclosure, or hiding a
responsive surface changes presentation visibility. It must not implicitly
discard unsaved drafts, field selection, expansion, scroll position, query
registration, or the last settled presentation. Reset occurs only on an
explicit user reset or a documented incompatible scope boundary.

When a hidden tool becomes visible, its query requirements and cached
presentation are available on its first visible frame. Mounting the tool may
not be the event that discovers active fields through a child-to-parent passive
effect.

## Accessibility and verification

Stable presentation must preserve keyboard operation, focus continuity,
programmatic names, ARIA state, and accessible full text. Color or opacity alone
must not communicate state. Reduced-motion users receive no essential motion,
and removing entrance motion must not remove focus or state feedback.

Painted browser frames are authoritative for continuity. Named card, panel, and
next-control anchors may move by at most one CSS pixel unless a ticket records
an intentional internal-scroll exception. Geometry is necessary but not
sufficient. A continuity trace must also inspect the relevant descendant row
identities and values, action presence and computed visibility, placeholder or
fallback states, control values, and media `currentSrc`, `complete`,
`naturalWidth`, computed opacity, transform, and decoded pixels.

Cold A-to-unvisited-B, warm revisit, rapid A-to-B-to-C, tab return, compatible
scope navigation, and fast/medium/slow success plus terminal empty/error are
the minimum transition matrix for a changed asynchronous surface. A one-frame
blank, false fallback, mixed identity, missing action/value, or undecoded media
promotion fails. Final-DOM assertions, screenshots after settling, and unit
tests support but do not replace a failing painted-frame trace.
