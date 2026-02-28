---
name: Ranking Frontend Rewrite
overview: Replace the bloated lenslet ranking frontend (897-line RankingApp.tsx + 443-line ranking.css + 7 model files = ~2,300 lines) with a clean implementation ported from the working ranking-tool reference (~875 lines), using @dnd-kit for drag-and-drop and Tailwind for styling, while keeping the existing backend and API contracts intact.
todos:
  - id: add-deps
    content: Install @dnd-kit/core, @dnd-kit/sortable, @dnd-kit/utilities, clsx, tailwind-merge, lucide-react in frontend/
    status: pending
  - id: extract-components
    content: Create ImageCard.tsx, RankColumn.tsx, Lightbox.tsx under features/ranking/components/, ported from ranking-tool reference
    status: pending
  - id: rewrite-app
    content: Rewrite RankingApp.tsx using @dnd-kit DndContext, Tailwind layout, ported from ranking-tool App.tsx but adapted for lenslet API types
    status: pending
  - id: delete-css
    content: Delete ranking.css and replace all styles with Tailwind utility classes
    status: pending
  - id: simplify-models
    content: Delete model/keyboard.ts, model/layout.ts, model/palette.ts and their tests; inline minimal logic into RankingApp.tsx
    status: pending
  - id: cleanup-dead
    content: Delete data/fixtures/ranking_smoke_result.json and any other dead ranking artifacts
    status: pending
  - id: validate
    content: Run tsc, tests, build, lint, and manual browser check
    status: pending
isProject: false
---

# Ranking Frontend Rewrite from Reference

## Problem

Two codex iterations produced a ranking UI that:

- Does not fit on a single screen and has wobbly layout (reported by user)
- Uses raw HTML5 Drag and Drop API (no smooth drag overlay, janky ghost images)
- Has 443 lines of custom CSS with fragile grid layout and complex `color-mix()` chains
- Has a monolithic 897-line `RankingApp.tsx`
- Over-engineered model layer across 7 files (keyboard.ts, layout.ts, palette.ts, session.ts, board.ts, saveSeq.ts, and their tests)

Meanwhile, the reference [ranking-tool/src](ranking-tool/src) achieves the same functionality in ~875 lines of frontend code, fits on screen, and actually works -- using @dnd-kit + Tailwind + 4 small components.

## What to Keep (unchanged)

- **Backend** ([src/lenslet/ranking/](src/lenslet/ranking/)): Well-structured, ~627 lines, robust persistence. No changes.
- **Backend tests** ([tests/test_ranking_backend.py](tests/test_ranking_backend.py), [tests/test_ranking_cli.py](tests/test_ranking_cli.py)): Keep as-is.
- **API adapter** ([frontend/src/features/ranking/api.ts](frontend/src/features/ranking/api.ts)): Clean 35-line adapter mapping to `/rank/*` endpoints. Keep.
- **Types** ([frontend/src/features/ranking/types.ts](frontend/src/features/ranking/types.ts)): Backend contract types. Keep.
- **Board model** ([frontend/src/features/ranking/model/board.ts](frontend/src/features/ranking/model/board.ts)): Pure state logic with good tests. Keep. The functions `buildBoardState`, `moveImageToRank`, `moveImageToRankWithAutoAdvance`, `finalRanksFromBoard`, `isBoardComplete` are sound.
- **CLI integration** ([src/lenslet/cli.py](src/lenslet/cli.py)): `lenslet rank` subcommand. Keep.

## What to Rewrite

### 1. Add @dnd-kit dependencies

Install `@dnd-kit/core`, `@dnd-kit/sortable`, `@dnd-kit/utilities`, `clsx`, `tailwind-merge`, and `lucide-react` in [frontend/](frontend/).

The reference uses these for smooth drag-and-drop with visual overlay, sortable contexts per column, and clean utility-class merging. This replaces the janky native HTML5 DnD.

### 2. Rewrite RankingApp.tsx + extract components

Replace the 897-line monolith [frontend/src/features/ranking/RankingApp.tsx](frontend/src/features/ranking/RankingApp.tsx) with a lean main component (~300-400 lines) plus extracted components, following the reference architecture:

- `**RankingApp.tsx`** (~350 lines): State management, DndContext, layout, keyboard handler. Port directly from [ranking-tool/src/App.tsx](ranking-tool/src/App.tsx), adapting for lenslet's API types (image objects with `image_id`/`url`/`source_path` vs plain URL strings).
- `**components/ImageCard.tsx**` (~80 lines): Sortable card with `useSortable` hook, focus ring, enlarge button, badge label. Port from [ranking-tool/src/components/ImageCard.tsx](ranking-tool/src/components/ImageCard.tsx).
- `**components/RankColumn.tsx**` (~45 lines): Droppable column with `SortableContext`. Port from [ranking-tool/src/components/RankColumn.tsx](ranking-tool/src/components/RankColumn.tsx).
- `**components/Lightbox.tsx**` (~115 lines): Fullscreen overlay with pan/zoom/keyboard. Port from [ranking-tool/src/components/Lightbox.tsx](ranking-tool/src/components/Lightbox.tsx).

Key adaptation: The reference uses raw URL strings as image IDs (e.g., `"https://picsum.photos/..."`). Lenslet uses `image_id` strings and resolves URLs through `RankingImage.url`. The rewrite maps between these at the API boundary using `imageById` lookup, similar to the current approach but cleaner.

### 3. Delete ranking.css, use Tailwind

Delete [frontend/src/features/ranking/ranking.css](frontend/src/features/ranking/ranking.css) (443 lines). The reference achieves the same layout (and better) with Tailwind utility classes directly in JSX. Lenslet already has Tailwind 4 configured via `@import "tailwindcss"` in `styles.css`.

Layout approach from the reference that works:

- Unranked area: white card at top with resizable height, flex-wrap grid of image cards
- Rank columns: horizontal flex row at bottom, each column is a vertical droppable
- Resize handle: simple pointer-capture button (no complex splitter abstraction)

### 4. Simplify model layer

**Keep:**

- [model/board.ts](frontend/src/features/ranking/model/board.ts) (179 lines) + its test -- pure state logic that works

**Delete:**

- `model/keyboard.ts` (70 lines) + test -- inline the ~20 lines of key routing directly in the keydown handler (reference pattern)
- `model/layout.ts` (40 lines) + test -- replace with 2 constants inline (reference uses `UNASSIGNED_DEFAULT_HEIGHT = 200` and `UNASSIGNED_MIN_HEIGHT = 120`)
- `model/palette.ts` (26 lines) + test -- replace with alpha labels (A, B, C...) like the reference, or keep as optional dot colors inline
- `model/session.ts` (92 lines) + test -- the reference manages sessions with simple `useState` + `useEffect`. Keep `buildInitialSessions` and `computeDurationMs` but inline into `RankingApp.tsx` or a slim utils file

### 5. Clean up dead files and leftover docs

- Delete [data/fixtures/ranking_smoke_result.json](data/fixtures/ranking_smoke_result.json) -- references deleted smoke script
- The two ralph workspace directories under `docs/ralph/` (`20260228_ranking_mode_execution_plan/`, `20260228_ranking_mode_interaction_layout_iteration/`) are historical logs -- leave as-is or delete per preference
- The plan docs themselves (`docs/20260228_ranking_mode_execution_plan.md`, `docs/20260228_ranking_mode_interaction_layout_iteration_plan.md`) are historical -- leave as archive

## Dependency on existing patterns

The rewrite should maintain:

- `AppModeRouter.tsx` integration (health endpoint determines browse vs ranking mode)
- `api.ts` / `types.ts` API contracts (backend unchanged)
- `board.ts` state model (`RankingBoardState` shape with `unranked`, `rankColumns`, `selectedImageId`)
- Save payload shape (`RankingSaveRequest`)

## Size target


| Area               | Before             | After (target)                     |
| ------------------ | ------------------ | ---------------------------------- |
| RankingApp.tsx     | 897 lines          | ~350 lines                         |
| Components         | 0 files            | 3 files, ~240 lines                |
| ranking.css        | 443 lines          | 0 (Tailwind)                       |
| Model files        | 5 files, 320 lines | 1 file (board.ts), 179 lines       |
| Model tests        | 5 files, 395 lines | 1 file (board.test.ts), ~154 lines |
| **Frontend total** | **~2,300 lines**   | **~950 lines**                     |


## Validation

After rewrite:

1. `cd frontend && npx tsc --noEmit` -- type check
2. `cd frontend && npm run test -- src/features/ranking` -- board model tests pass
3. `cd frontend && npm run build && rsync -a --delete dist/ ../src/lenslet/frontend/` -- build succeeds
4. `python scripts/lint_repo.py` -- lint passes
5. Manual: `lenslet rank data/fixtures/ranking_dataset.json --port 7071` -- verify layout fits on screen, drag-and-drop is smooth, keyboard shortcuts work, lightbox works

