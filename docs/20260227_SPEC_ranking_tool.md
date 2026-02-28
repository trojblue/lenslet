

# Image Ranking Calibration Tool

*Internal single-user labeling interface*

------

# 1. System Overview

A lightweight web-based annotation tool for ranking small batches of local images.

Each instance:

- Contains N images (typically 5)
- User assigns them into ranked groups
- Ties are allowed
- Ranking is relative (not semantic hard-coded)
- Results are autosaved
- Single-user
- No authentication
- JSON-based persistence
- React frontend, FastAPI backend

Goal: fast, low-friction calibration tool.

------

# 2. Data Model

## 2.1 Dataset (Input)

Stored as JSON file:

```json
[
  {
    "instance_id": 1,
    "images": [
      "/local/path/img1.jpg",
      "/local/path/img2.jpg",
      "/local/path/img3.jpg",
      "/local/path/img4.jpg",
      "/local/path/img5.jpg"
    ]
  }
]
```

Rules:

- `instance_id` unique
- `images.length = N`
- N determines max possible ranks

------

## 2.2 Ranking Representation

Ties are supported.

Final ranking stored as rank groups:

```json
{
  "instance_id": 1,
  "initial_order": [...],
  "final_ranks": [
    ["img3.jpg"],
    ["img1.jpg", "img4.jpg"],
    ["img2.jpg"],
    ["img5.jpg"]
  ],
  "started_at": "...",
  "submitted_at": "...",
  "duration_ms": 18234
}
```

### Rules

- Each image appears exactly once
- Rank groups are ordered highest → lowest
- Number of groups ≤ number of images
- Empty groups not stored
- Equal ranking = same inner array

Example:
All equal:

```json
"final_ranks": [
  ["img1.jpg", "img2.jpg", "img3.jpg", "img4.jpg", "img5.jpg"]
]
```

------

## 2.3 Results Storage Format

Use append-only JSON Lines file:

```
results.jsonl
```

Each save appends one JSON object per line:

```
{"instance_id":1, ...}
{"instance_id":2, ...}
{"instance_id":1, ...}   // edited version
```

Latest entry per instance overrides previous.

Why JSONL:

- Safer against corruption
- No full-file rewrites
- Easy to parse
- No database required

------

# 3. Frontend Specification (React)

------

## 3.1 Core UI Layout

### Header

- PREV button
- Instance counter (e.g. 42 / 1000)
- Export button
- NEXT button

### Body

- Dominant top "Unranked" workspace with larger cards
- Bottom fixed rank buckets: 1 → N (each bucket is a drop zone)
- Images displayed as draggable cards in both sections
- Desktop mouse pointers can resize top/bottom split with a drag handle
- Narrow/coarse-pointer layouts use a fixed stacked layout (no splitter drag)

Ranks are relative:
Left = higher quality
Right = lower quality

No semantic labels like “Best” or “Worst”.

------

## 3.2 Ranking Behavior

- Images can be dragged between columns
- Multiple images allowed in same column
- Within-column order irrelevant
- All images must belong to some rank before NEXT enabled
- User cannot skip instance

------

## 3.3 Keyboard Controls

Board mode:

- 1–N → move selected image to rank
- Arrow keys → move selection left/right
- q/e → previous/next instance
- Enter → open fullscreen on selected image

Fullscreen mode:

- a/d → previous/next image in initial order
- 1–N → move current fullscreen image to rank
- Escape → close fullscreen and restore board focus to the same image

Deprecated behavior:

- Backspace does not navigate instances.

Behavior rules:

- Selected image visually highlighted
- Assigning an unranked image advances focus to next unranked image in initial dataset order
- Reranking an already ranked image keeps focus on that image
- Focus preserved across re-renders

------

## 3.4 State Model

### Local State

```ts
currentIndex: number
dataset: Instance[]
currentRanking: Record<number, string[]>
startedAt: number
progressCache: Map<instance_id, ranking>
```

------

## 3.5 Autosave

Triggered on:

- Drag end
- Keyboard move
- Navigation (Prev/Next)

Process:

1. Serialize ranking
2. POST to backend
3. Update local progress cache

Autosave must:

- Not block UI
- Handle network errors gracefully
- Retry once if needed

------

## 3.6 Navigation Rules

### NEXT

- Disabled if any image unranked
- Saves before advancing
- Loads saved ranking if revisiting

### PREV

- Always enabled except first instance
- Restores saved ranking if exists

------

## 3.7 Image Loading

- Load only current instance images
- Preload next instance in background
- Use browser caching
- Do not preload entire dataset

Image size assumption:
2–3MB per image

------

## 3.8 Resume Behavior

On page reload:

- Fetch progress from backend
- Resume at last completed instance
- Restore ranking state

------

# 4. Backend Specification (FastAPI)

------

## 4.1 Endpoints

### GET `/dataset`

Returns full dataset JSON.

------

### POST `/save`

Request body:

```json
{
  "instance_id": 42,
  "final_ranks": [...],
  "started_at": "...",
  "submitted_at": "...",
  "duration_ms": 18234
}
```

Action:

- Append JSON line to `results.jsonl`
- Return success

No overwriting.
No DB.
No auth.

------

### GET `/progress`

Returns:

```json
{
  "completed": [1, 2, 3, ...],
  "last_instance_index": 42
}
```

Backend determines latest entry per instance by scanning JSONL.

------

### GET `/export`

- Reads JSONL
- Collapses latest entry per instance
- Returns clean JSON file
- Optional: filter completed only

------

## 4.2 Storage Rules

- Dataset JSON stored separately
- Results JSONL append-only
- Writes must be atomic (use file lock)

------

## 4.3 Failure Handling

If crash during write:

- Only last line potentially incomplete
- On load, ignore malformed last line

------

# 5. Ranking Logic Rules

- Max ranks = number of images in instance
- Empty ranks not stored
- Rank numbers inferred by array order
- All images must exist exactly once

Validation required before save.

------

# 6. Metadata

Stored per instance:

- instance_id
- initial_order
- final_ranks
- started_at
- submitted_at
- duration_ms

Optional future:

- num_moves
- num_rank_changes

------

# 7. Explicit Non-Goals

- No authentication
- No multi-user concurrency
- No assignment logic
- No confidence scoring
- No dynamic filtering
- No large-scale optimization
- No DB

------

# 8. Known Risk Areas

1. Keyboard focus management
2. Tie handling logic
3. Correct restoration on navigation
4. Autosave race conditions
5. JSONL parsing robustness

------

# 9. Minimum Viable Version (V1)

To avoid scope creep:

- Top-unranked + bottom-rank layout
- Drag-and-drop
- Board + fullscreen hotkeys (`1-N`, `q/e`, `Enter`, `a/d`, `Escape`)
- Autosave
- JSONL append
- Export

Everything else is optional polish.
