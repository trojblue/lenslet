# Embedding Similarity Phase 2 Plan (Product + UX)

**Document status**: Revised after repo audit (2026-02-02)

---

## Executive Summary

Phase 2 should tighten the existing similarity workflow without breaking the gallery's core keyboard navigation. Lenslet is a lightweight, local-first triage tool; similarity stays as its own mode with a modal and a banner. The plan focuses on clarity and speed, not new modes or heavy backend work.

**Key changes from Phase 1 (revised)**:
1. Keep the modal for advanced inputs; make "Find similar" fast with good defaults and prefilled selection.
2. Improve similarity banner context and add a keyboard-safe exit (Esc).
3. Optional, read-only similarity score display in the grid (no new sorting or filter integration).
4. Surface embeddings availability and errors in existing UI (Inspector + modal), not a new sidebar panel.

**Non-goals for Phase 2**:
- New global shortcuts that conflict with WASD navigation.
- Treating similarity_score as a first-class metric with sorting and filters.
- New endpoints for encoding uploads/URLs or duplicate clustering (future work).

---

## Purpose / Big Picture

Phase 1 delivered backend similarity search and a basic "Find similar" UI. Phase 2 should make similarity faster to use while preserving Lenslet's core model: quick local browsing, minimal UI, and predictable keyboard controls.

**Goal:** Make "Find similar" feel fast and clear without changing how people navigate the grid.

---

## Design Principles

1. **Respect existing keyboard navigation**: WASD and arrow keys are already used for grid and viewer navigation; do not reassign them.
2. **Similarity remains a distinct mode**: preserve similarity ranking; keep sort/search disabled to avoid confusion.
3. **Explicit context**: always show embedding, query label, top_k, min_score, and result count while similarity is active.
4. **Reversible actions**: one-step exit returns the prior selection and scroll position.
5. **Minimal backend changes**: focus on frontend/UI polish in Phase 2.

---

## User Stories (Revised)

1. **Quick similarity exploration**
   - Select image -> Click "Find similar" -> See top results ranked by similarity.
   - Click another result -> Click "Find similar" again -> Continue exploring.
   - Exit similarity via button or Esc -> Return to original view.

2. **Quality check with filters**
   - Start similarity search -> Apply rating/metric filters.
   - Filters refine the similarity results, but ranking stays similarity-based.

---

## Information Architecture (Revised)

### Current State (Phase 1)
- "Find similar" button in Inspector opens SimilarityModal.
- Similarity mode replaces the grid, disables sort/search, and shows a banner.

### Target State (Phase 2)
- **Modal stays**: it is the advanced entry point for vector input and top_k/min_score.
- **Quick path stays**: Inspector button remains the primary trigger; no new global shortcut in Phase 2.
- **Banner improved**: clearer context, optional score range, and Esc exits similarity.
- **Optional score display**: show similarity score on each grid item when in similarity mode.

---

## Proposed Phase 2 Scope (Concrete)

### 1) Similarity Flow Polish (Priority: High)

**What changes**
- Keep SimilarityModal; prefill selected image path and last-used settings.
- Add Esc-to-exit when similarity is active (no keyboard conflicts).

**Why**
- Reduces friction without breaking grid navigation.

**Implementation notes**
- `AppShell.tsx`: if `similarityActive` and Esc pressed, call `clearSimilarity()`.
- `SimilarityModal.tsx`: persist last-used embedding/top_k/min_score in localStorage (optional).

### 2) Similarity Banner Improvements (Priority: Medium)

**What changes**
- Keep existing banner but tighten the information layout.
- Optional: show score range derived from `similarityState.items`.

**Implementation notes**
- `AppShell.tsx`: compute min/max score for banner display.

### 3) Read-only Score Display (Priority: Medium-Low)

**What changes**
- Show a small similarity score badge on grid items while similarity is active.
- Do not integrate with sorting or filters in Phase 2.

**Implementation notes**
- Keep a `path -> score` map in `AppShell.tsx` and pass to the grid for display.
- Avoid modifying metric pipelines or sorters.

### 4) Embeddings Availability Messaging (Priority: Medium-Low)

**What changes**
- Reuse the existing Inspector and modal messaging for "No embeddings detected" and skipped columns.
- Avoid creating a new Embeddings sidebar panel in Phase 2.

---

## API / Backend Changes

- **None required for Phase 2.**
- Continue using existing `GET /embeddings` and `POST /embeddings/search`.
- Encoding uploads/URLs and duplicate clustering are out of scope.

---

## Codebase Mapping (Revised)

### Frontend files likely touched

- `frontend/src/app/AppShell.tsx`
  - Similarity state, banner rendering, and global key handler (Esc to exit similarity).
- `frontend/src/features/embeddings/SimilarityModal.tsx`
  - Prefill from selection, optional persistence of last-used settings.
- `frontend/src/features/browse/components/VirtualGrid.tsx`
  - Optional similarity score badge when similarity is active.

### Backend files

- No changes required for Phase 2.

---

## Phased Delivery Plan (Adjusted)

### Phase 2.0 - Flow polish

**Tasks**
1. Add Esc-to-exit similarity when `similarityActive` is true.
2. Prefill modal with selected image and last-used parameters.

**Validation**
- Start similarity -> press Esc -> similarity exits and previous selection is restored.
- Open modal -> selected image is prefilled; last-used settings persist.

### Phase 2.1 - Banner + score display

**Tasks**
1. Add optional score range to similarity banner.
2. Add read-only similarity score badge in the grid.

**Validation**
- Similarity banner shows correct score range.
- Grid items show scores only during similarity mode.

---

## Risks & Mitigations

- **Keyboard conflicts**: avoid new global shortcuts; keep WASD/arrow navigation intact.
- **UI clutter**: score display is optional and only visible in similarity mode.

---

## Acceptance Criteria (Revised)

- "Find similar" works from the Inspector and keeps the modal for advanced inputs.
- Similarity banner shows clear context (embedding, query label, top_k/min_score, result count).
- Esc exits similarity and restores the prior selection.
- Optional similarity score display is visible in the grid without changing sorting/filter behavior.

---

## Out of Scope (Phase 2)

- Query history, query JSON copy, and permalinks.
- Upload/URL-based encoding and new `/embeddings/encode` endpoint.
- Duplicate clustering workflow and `/embeddings/duplicates` endpoint.
