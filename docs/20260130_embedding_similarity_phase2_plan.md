# Embedding Similarity Phase 2 Plan (Product + UX)

**Document status**: Revised with codebase analysis (2026-01-30)

---

## Executive Summary

Phase 2 transforms embedding search from a modal-based feature into a seamless, keyboard-driven workflow. The core insight: **similarity search should feel like navigating, not querying**.

**Key changes from Phase 1**:
1. `S` key triggers instant search (no modal) → reduces friction from 3 clicks to 1 keystroke
2. `similarity_score` becomes a real metric → sortable, filterable, exportable
3. Embeddings panel surfaces status/errors inline → no hidden failures
4. Query context stays visible → always know what you're looking at

**Non-goals for Phase 2**:
- GPU acceleration controls (Phase 3)
- UMAP visualization (Phase 3)
- Multi-model comparison (nice-to-have, not MVP)

---

## Purpose / Big Picture

Phase 1 delivered backend similarity search and a basic "Find similar" UI. Phase 2 must make embedding search feel like a first-class scientific tool: clear provenance, composable with filters, reproducible, and fast enough to iterate without surprises.

**Goal:** The bar is "would I personally use this daily for curation/exploration". That requires:
- Zero-friction "find similar" from any image (one click or keyboard shortcut)
- Similarity as context, not a modal interruption
- Results that feel like "filtered by similarity" rather than "different mode"
- Confidence that results are reproducible and comparable across sessions


## Design Principles (Scientific HCI)

1. **Explicit state**: Always show embedding column, metric, query source, and key params (`top_k`, `min_score`). Never hide what's happening.
2. **Reproducible actions**: Copy/share query parameters as JSON; optional permalink in URL hash.
3. **Composability**: Similarity adds a score column; filters and sorts still work. Think of it as "add `similarity_score` to all items" not "switch to similarity mode".
4. **Reversibility**: Clear similarity with one click; restore previous selection and scroll position.
5. **Progressive disclosure**: One-click "Find similar" for the 90% case; advanced panel for power users.
6. **Local-first**: No data leaves the machine unless explicitly enabled (URL fetch off by default).
7. **Low-friction iteration**: Clicking a result and hitting "S" should immediately search from that image. This is how you explore embedding space.


## User Stories (Refined)

### Primary Personas

- **Explorer (most common)**: "I want to select an image and see what's similar. Then I want to click one of those results and see what's similar to *that*. Rapid iteration is key."
- **Quality reviewer**: "I need to find near-duplicates or check if a new image already exists in the dataset. Speed and accuracy matter."
- **Curator**: "I want to cluster similar images, tag them in bulk, and export the list for downstream processing."
- **Analyst**: "I want to reproduce a query exactly, share it with a colleague, and compare results across different embedding columns."

### Concrete Scenarios

1. **Quick similarity exploration** (90% of usage)
   - Select image → Press `S` (or right-click → "Find similar") → See top 50 results ranked by similarity
   - Click another image in results → Press `S` again → See its neighbors
   - Continue exploring until satisfied → Press `Esc` or click "Exit similarity" → Back to original view

2. **Quality check with filters**
   - Start similarity search → Apply rating filter (only unrated) → Apply metric filter (quality > 0.8)
   - Results are similarity-ranked but constrained to matching items
   - Tag the good ones in bulk

3. **Near-duplicate detection**
   - Open "Find duplicates" panel → Set threshold 0.97 → Run
   - See clusters of near-duplicates with representative thumbnail
   - Click cluster → Expand to see all members → Bulk-tag or delete extras

4. **Reproducible query sharing**
   - Run similarity search → Click "Copy query" → Get JSON with all parameters
   - Send to colleague → They paste into "Load query" → Identical results


## Information Architecture (Concrete)

### Current State (Phase 1)
- "Find similar" button in Inspector → Opens `SimilarityModal` → Runs search → Replaces grid
- Similarity mode: dedicated state, disables sort/search, shows banner

### Target State (Phase 2)

**A) Replace modal with inline trigger + panel**
- **Trigger**: Keyboard shortcut `S` + context menu + Inspector button (existing)
- **Inline execution**: Default embedding, top_k=50, min_score=0.2 — no modal needed
- **Advanced panel**: Expandable section in Inspector or left sidebar for tuning

**B) Similarity as "enhanced filter" conceptually**
- When active: items gain `similarity_score` as a sortable/filterable virtual metric
- Default sort: by `similarity_score` desc (since that's the point)
- Filters remain active and combinable
- Sort can be changed (though similarity_score desc is usually what you want)

**C) Query context in toolbar (persistent chip)**
- Shows: `Similar to: cat.jpg | clip | 50 results`
- One-click to clear, one-click to copy query JSON
- Stays visible until explicitly cleared

**D) Embeddings status in left sidebar**
- New section under Metrics: "Embeddings"
- Shows available columns, active column, backend status (NumPy/FAISS)
- Error states: "FAISS not installed" with install hint, "No embeddings found" with guidance


## Proposed Phase 2 Scope (Concrete)

### 1) One-Key Similarity Search (Priority: Critical)

**The killer feature**: Press `S` with an image selected → instant similarity results.

**Implementation**
- Keyboard shortcut `S` when Inspector is showing an image
- Uses default embedding (first available), top_k=50, min_score=0.2
- No modal, no confirmation — just runs immediately
- If no embeddings available: show toast "No embeddings available. See docs."

**Why this matters**: The current modal creates friction. Every click/dialog reduces exploration velocity. The goal is to make "find similar" as fast as pressing an arrow key.

**Code change**: Add `useEffect` in `AppShell` to listen for `S` key when `selectedPaths.length === 1` and `embeddingsAvailable`. Call `handleSimilaritySearch` directly with defaults.

### 2) Embeddings Status Panel (Priority: High)

**Location**: New section in left sidebar, below Metrics panel

**What it shows**
```
┌─ Embeddings ─────────────────────────┐
│ ● clip (512d, cosine)         FAISS  │
│ ○ dino_v2 (768d, cosine)      NumPy  │
│                                      │
│ Rejected:                            │
│   aesthetic_v2: variable-length list │
│                                      │
│ [Change default] [Preload all]       │
└──────────────────────────────────────┘
```

**States**
- `ready`: Embedding loaded, index built (shows backend: FAISS/NumPy)
- `not_loaded`: Available but not yet indexed (lazy load on first query)
- `error`: Failed to load (show reason inline, not just in logs)
- `backend_missing`: NumPy not installed (show `pip install lenslet[embeddings]`)

**Actions**
- Click embedding name to set as default for `S` shortcut
- "Preload all" button to build indexes at idle time
- Tooltip on rejected columns explaining why (e.g., "Variable-length lists not supported")

### 3) Query-by-Image (Refined Sources)

**Source priority (in order of usage frequency)**

1. **Selected image** (90% of queries)
   - Uses existing embedding from parquet row
   - Zero re-encoding, instant results
   - Triggered by `S` key or "Find similar" button

2. **Drag-and-drop / paste image** (new for Phase 2)
   - Drop image onto grid or paste from clipboard
   - Uses `/embeddings/encode` to generate vector on-the-fly
   - Shows "Encoding..." indicator during processing
   - Useful for "does this image exist in my dataset?"

3. **URL input** (disabled by default)
   - Requires `--allow-url-fetch` CLI flag
   - Fetches image, encodes, searches
   - Security concern: off by default, documented risk

4. **Raw vector** (power users only)
   - Paste base64 float32 in advanced panel
   - For integration with external embedders

**API: `POST /embeddings/encode`**

```json
// Request (multipart/form-data)
{
  "file": <binary>,           // OR
  "path": "/local/path.jpg",  // OR
  "url": "https://..."        // (if enabled)
}

// Response
{
  "vector_b64": "...",
  "embedding": "clip",
  "dimension": 512,
  "preprocess": {"resize": 224, "normalize": true}
}
```

### 4) Similarity as Transient Metric (Priority: High)

**Conceptual shift**: Instead of "similarity mode", similarity becomes a virtual column.

**When similarity is active**
- Items gain `similarity_score` (0.0–1.0)
- This appears in the metrics list in the left panel
- Sortable: click "similarity_score" in sort dropdown
- Filterable: drag range slider in metrics panel
- Exportable: CSV includes similarity_score column

**Behavior**
- Default sort: `similarity_score` desc when active
- User can change sort (e.g., sort by rating instead)
- Filters work on top of similarity results (intersect, don't replace)

**Implementation note**: Current `similarityState` in `AppShell.tsx` (line 76-84) already tracks this. Extend to inject `similarity_score` into item objects before passing to `applyFilters` and `applySort`.

### 5) Query Context Chip (Priority: Medium)

**Location**: Toolbar area, similar to filter chips

**When visible**: Any time similarity is active

**Display**
```
┌─────────────────────────────────────────────────┐
│ 🔍 Similar to: cat.jpg  │  clip  │  47 results  │  [×]  │  [⋮]  │
└─────────────────────────────────────────────────┘
```

**Actions**
- Click `×`: Clear similarity, restore previous selection
- Click `⋮` menu:
  - "Copy query JSON" → Clipboard
  - "Search from this result" → Run similarity on current selection
  - "Adjust parameters" → Open advanced panel

**JSON format for copy**
```json
{
  "embedding": "clip",
  "query_source": "path",
  "query_path": "/images/cat.jpg",
  "top_k": 50,
  "min_score": 0.2,
  "timestamp": "2026-01-30T10:30:00Z",
  "version": 1
}
```

### 6) Query History (Priority: Medium-Low)

**Storage**: LocalStorage, keyed by embedding name

**Structure**
```typescript
interface QueryHistoryEntry {
  id: string                  // UUID
  embedding: string
  querySource: 'path' | 'upload' | 'vector'
  queryLabel: string          // "cat.jpg" or "Uploaded image" or "Vector"
  queryThumbUrl?: string      // Data URL for visual preview
  topK: number
  minScore: number | null
  resultCount: number
  timestamp: number
  pinned: boolean
}
```

**UI**: Dropdown in advanced panel showing last 5 queries with thumbnail + label

### 7) Dedupe Workflow (Priority: Medium)

**Entry point**: "Find duplicates" button in Embeddings panel

**Algorithm**
1. User sets threshold (default 0.97 for near-exact)
2. Backend runs pairwise similarity on filtered set
3. Returns clusters using connected-component approach
4. UI shows: cluster ID, representative image, member count, average similarity

**Output**
```json
{
  "clusters": [
    {
      "id": 1,
      "representative": "/images/cat.jpg",
      "members": ["/images/cat.jpg", "/images/cat_copy.jpg", "/images/cat_v2.jpg"],
      "avg_similarity": 0.982
    }
  ],
  "threshold": 0.97,
  "total_duplicates": 127
}
```

**Actions**
- Click cluster → Select all members in grid
- "Keep first, trash rest" → Bulk move to trash
- "Tag as duplicate" → Add tag to all members
- "Export CSV" → Download cluster list for external processing


## API and Backend Changes (Concrete)

### `GET /embeddings` (Existing, Enhanced)

**Current response** (keep as-is)
```json
{
  "embeddings": [
    {"name": "clip", "dimension": 512, "dtype": "float32", "metric": "cosine"}
  ],
  "rejected": [
    {"name": "aesthetic_v2", "reason": "variable-length list"}
  ]
}
```

**Add fields**
```json
{
  "embeddings": [
    {
      "name": "clip",
      "dimension": 512,
      "dtype": "float32",
      "metric": "cosine",
      "backend": "faiss",        // NEW: "faiss" | "numpy" | "not_loaded"
      "row_count": 12847,        // NEW: number of valid embeddings
      "cached": true             // NEW: whether cache exists
    }
  ],
  "backend_available": {         // NEW: overall capability
    "numpy": true,
    "faiss": true,
    "torch": false
  }
}
```

### `POST /embeddings/encode` (New)

**Purpose**: Encode an image into a vector for query-by-upload

**Request (multipart/form-data)**
```
POST /embeddings/encode
Content-Type: multipart/form-data

file: <binary>
embedding: clip           // optional, defaults to first available
```

**Alternative JSON request** (for path-based encoding)
```json
{
  "path": "/local/path/to/image.jpg",
  "embedding": "clip"
}
```

**Response**
```json
{
  "vector_b64": "...",
  "embedding": "clip",
  "dimension": 512,
  "dtype": "float32",
  "preprocessing": {
    "resize": 224,
    "normalize": true,
    "model": "openai/clip-vit-base-patch32"  // if known
  }
}
```

**Error cases**
- 400: "No embedding model available for encoding" (if no encoder configured)
- 400: "Image could not be decoded"
- 403: "URL fetching is disabled" (if URL provided without `--allow-url-fetch`)
- 413: "Image too large" (configurable max size, default 10MB)

**Note**: Phase 2.1 can start with path-based only; file upload is a nice-to-have.

### `POST /embeddings/search` (Enhanced)

**Current parameters** (keep)
- `embedding`: string (required)
- `query_path`: string | null
- `query_vector_b64`: string | null
- `top_k`: int (max 1000)
- `min_score`: float | null

**Add parameters**
```json
{
  "include_self": false,         // exclude query image from results
  "return_full_items": false     // if true, return full item objects not just paths
}
```

**Enhanced response**
```json
{
  "embedding": "clip",
  "items": [
    {
      "row_index": 12,
      "path": "/images/cat.jpg",
      "score": 1.0
    }
  ],
  "query_provenance": {          // NEW: for reproducibility
    "source": "path",            // "path" | "vector" | "upload"
    "query_path": "/images/original.jpg",
    "embedding": "clip",
    "metric": "cosine",
    "top_k": 50,
    "min_score": 0.2,
    "result_count": 47,
    "backend": "faiss",
    "timestamp": "2026-01-30T10:30:00Z"
  }
}
```

### `POST /embeddings/duplicates` (New, Phase 2.3)

**Purpose**: Find near-duplicate clusters

**Request**
```json
{
  "embedding": "clip",
  "threshold": 0.97,             // min similarity to consider duplicate
  "min_cluster_size": 2,         // at least N items to form cluster
  "max_clusters": 100,           // limit output size
  "scope": "filtered"            // "all" | "filtered" (apply current filters first)
}
```

**Response**
```json
{
  "clusters": [
    {
      "id": 1,
      "representative": "/images/cat.jpg",
      "members": [
        {"path": "/images/cat.jpg", "score": 1.0},
        {"path": "/images/cat_copy.jpg", "score": 0.985}
      ],
      "size": 2,
      "avg_score": 0.9925
    }
  ],
  "total_clusters": 47,
  "total_duplicates": 127,
  "threshold": 0.97,
  "embedding": "clip"
}
```

**Algorithm notes**
- Use greedy clustering: pick highest-scoring ungrouped pair, expand cluster
- Or use scipy's connected_components on similarity graph
- Performance: O(n²) is fine for <10k items; for larger sets, use approximate methods

### Storage / Index

**Embedding registry** (in-memory, computed at startup)
```python
{
  "clip": {
    "spec": EmbeddingSpec(...),
    "backend": "faiss",
    "cached": True,
    "row_count": 12847,
    "index": EmbeddingIndex | None  # lazy loaded
  }
}
```

**Cache format** (existing, no change needed)
- Location: `.lenslet/embeddings_cache/{hash}.npz`
- Contents: normalized matrix + row indices


## UI/UX Behaviors (Concrete)

### Keyboard Shortcuts (Critical for Flow)

| Key | Context | Action |
|-----|---------|--------|
| `S` | Image selected, embeddings available | Run similarity search with defaults |
| `Escape` | Similarity active | Clear similarity, restore previous state |
| `Shift+S` | Image selected | Open advanced similarity panel |
| `Ctrl+Shift+C` | Similarity active | Copy query JSON to clipboard |

**Implementation**: Add to existing keyboard handler in `AppShell.tsx` (around line 1505-1541).

### Similarity Banner (Enhanced)

**Current** (line 1664-1686 in AppShell.tsx)
```
┌─────────────────────────────────────────────────────────────┐
│ Similarity mode  |  Embedding: clip  |  Query: cat.jpg     │
│ Results: 47  |  Top K: 50                                   │
│                                            [Exit similarity]│
└─────────────────────────────────────────────────────────────┘
```

**Enhanced**
```
┌─────────────────────────────────────────────────────────────┐
│ 🔍 Similar to cat.jpg                                       │
│    clip • 47 results • 0.89–1.00 score range               │
│                                                             │
│ [Search from selection (S)]  [Copy query]  [Adjust]  [×]    │
└─────────────────────────────────────────────────────────────┘
```

**Improvements**
- Thumbnail of query image (small, 32×32)
- Score range shown (helps calibrate expectations)
- "Search from selection" button for quick iteration
- Collapsible on small screens

### Embeddings Panel States

**Ready state**
```
┌─ Embeddings ─────────────────────────┐
│ Active: clip (512d) ▼               │
│ Backend: FAISS (fast)               │
│ Items: 12,847 indexed               │
│                                      │
│ [Find similar (S)]  [Find duplicates]│
└──────────────────────────────────────┘
```

**No embeddings state**
```
┌─ Embeddings ─────────────────────────┐
│ ⚠️ No embeddings found               │
│                                      │
│ Your dataset doesn't have embedding  │
│ columns. To add embeddings:          │
│                                      │
│ 1. Use --embed flag when starting    │
│ 2. Add a list column to your parquet │
│                                      │
│ [See documentation]                  │
└──────────────────────────────────────┘
```

**Missing backend state**
```
┌─ Embeddings ─────────────────────────┐
│ ⚠️ NumPy not installed               │
│                                      │
│ Embedding search requires NumPy.     │
│ Install with:                        │
│                                      │
│ pip install lenslet[embeddings]      │
│                                      │
│ For faster search, also install:     │
│ pip install faiss-cpu                │
└──────────────────────────────────────┘
```

### Query Controls (Advanced Panel)

**Collapsed by default, expandable via "Adjust" or Shift+S**

```
┌─ Query Settings ─────────────────────┐
│ Embedding:  [clip ▼]                 │
│ Top K:      [50____]                 │
│ Min score:  [0.2___]  (0.0–1.0)      │
│                                      │
│ ☐ Include query image in results     │
│ ☐ Search filtered items only         │
│                                      │
│ Query source:                        │
│ ○ Selected image                     │
│ ○ Paste vector (base64)              │
│                                      │
│ [Run search]  [Reset defaults]       │
└──────────────────────────────────────┘
```

**Persistence**: Store last-used settings in localStorage, keyed by embedding name.

### Error Handling

**Inline errors in Embeddings panel** (not just toasts)

Example error states:
```
┌─ Embeddings ─────────────────────────┐
│ ❌ Search failed                      │
│                                      │
│ Query image has no embedding.        │
│ This image may be newly added.       │
│                                      │
│ Try selecting a different image.     │
│                                      │
│ [Try again]  [Dismiss]               │
└──────────────────────────────────────┘
```

**Error categories and messages**

| Error | User message | Action |
|-------|-------------|--------|
| Query image not found | "Image not in index. Select a different image." | Show valid alternatives |
| Dimension mismatch | "Vector dimension doesn't match embedding." | Show expected dimension |
| FAISS build failed | "Search index failed. Using slower fallback." | Auto-fallback to NumPy |
| OOM on large dataset | "Dataset too large for memory. Try filtering first." | Suggest filters |

### Similarity Score Display in Grid

**Option A: Overlay badge** (subtle)
- Small score badge (e.g., "0.87") in top-right corner of thumbnail
- Only visible in similarity mode
- Color-coded: green (>0.9), yellow (0.7-0.9), gray (<0.7)

**Option B: Score bar** (more visible)
- Thin colored bar at bottom of thumbnail
- Width proportional to score
- Gradient from gray to accent color

**Recommendation**: Option A for cleaner look, with toggle in settings.


## Reproducibility & Sharing

- **Copy query JSON** (includes query source, params, embedding column, model, metric, vector hash)
- **Permalink** (optional): encode query params into URL fragment
- **Export**: CSV includes similarity_score and query metadata header

**Note:** This is the key to making results credible in a team setting.


## Codebase Mapping (Concrete Implementation Notes)

Based on exploration of the actual codebase, here's how Phase 2 maps to existing files and patterns:

### Backend Files to Modify

| File | Current Role | Phase 2 Changes |
|------|--------------|-----------------|
| `src/lenslet/server.py` | Defines `_register_embedding_routes()` at line 597 | Add `/embeddings/encode`, `/embeddings/duplicates` routes; enhance `/embeddings` response |
| `src/lenslet/server_models.py` | Pydantic models for `EmbeddingSearchRequest`, `EmbeddingSearchResponse` | Add `query_provenance` to response, add `include_self` param |
| `src/lenslet/embeddings/index.py` | `EmbeddingManager` class manages lazy-loaded indexes | Add `get_backend_info()` method for UI status display |
| `src/lenslet/embeddings/detect.py` | `EmbeddingDetection` namedtuple | Already has `available` and `rejected` fields—no changes needed |

### Frontend Files to Modify

| File | Current Role | Phase 2 Changes |
|------|--------------|-----------------|
| `frontend/src/app/AppShell.tsx` | Main shell; `SimilarityState` at line 76-84 | Add `S` key handler (~line 1505-1541), inject similarity_score into items |
| `frontend/src/features/embeddings/SimilarityModal.tsx` | Full-screen modal for search | Make optional/bypass with keyboard shortcut; extract advanced settings panel |
| `frontend/src/features/inspector/Inspector.tsx` | "Find similar" button at line 503-513 | Keep button, connect to quick-search flow |
| `frontend/src/app/components/LeftSidebar.tsx` | `leftTool: 'folders' | 'metrics'` | Add third tool `'embeddings'` or integrate into Metrics panel |
| `frontend/src/shared/ui/Toolbar.tsx` | Sort controls, `sortDisabled` prop | Remove sort disable when similarity active; add similarity_score to sort options |
| `frontend/src/features/browse/model/apply.ts` | `applyFilters()` and `applySort()` | Add `sortBySimilarity()` sorter |
| `frontend/src/lib/types.ts` | `EmbeddingSearchItem` has `score` field | Add `similarity_score` to `Item` type (optional field) |

### Key State Patterns Observed

**Current similarity flow (AppShell.tsx)**:
1. User clicks "Find similar" → `setSimilarityOpen(true)` opens modal
2. Modal calls `handleSimilaritySearch()` → `api.searchEmbeddings(payload)` 
3. Response stored in `similarityState` → triggers `similarityActive = true`
4. Grid shows `similarityItems` instead of `poolItems`
5. Filters apply to `similarityItems` (line 1357-1361)
6. Sort disabled (`sortDisabled={similarityActive}` on Toolbar)

**Target flow for Phase 2**:
1. User presses `S` → direct call to `handleSimilaritySearch()` with defaults (skip modal)
2. Similarity results get `similarity_score` injected into item objects
3. `similarity_score` added to `metricKeys` as transient entry
4. Sort enabled with `similarity_score` as default when active
5. MetricsPanel shows similarity_score slider for filtering

### Existing Patterns to Follow

**Filter AST pattern** (from `frontend/src/features/browse/model/filters.ts`):
- Each filter type is a clause in `FilterAST.and` array
- Getters/setters like `getMetricRangeFilter()`, `setMetricRangeFilter()`
- Could add `getSimilarityFilter()`, `setSimilarityFilter()` for min/max score filtering

**Metric display pattern** (from `MetricsPanel.tsx`):
- Metrics panel iterates over `metricKeys` from items
- Shows histogram and range slider for each key
- Similarity score should appear here when active

**Keyboard handling pattern** (from `AppShell.tsx` line 1505-1541):
- Check `isInputElement(e.target)` to avoid conflicts
- Existing shortcuts: arrow keys (navigate), `Backspace` (parent folder), `Ctrl+A` (select all), `Escape` (clear selection)
- Add: `S` (find similar), `Shift+S` (advanced panel), `Escape` in similarity mode (clear)

### API Client Pattern (from `frontend/src/api/client.ts`)

Current embedding API calls (line 353-366):
```typescript
getEmbeddings: (): Promise<EmbeddingsResponse> => {
  return fetchJSON<EmbeddingsResponse>(`${BASE}/embeddings`).promise
},
searchEmbeddings: (body: EmbeddingSearchRequest): Promise<EmbeddingSearchResponse> => {
  return fetchJSON<EmbeddingsResponse>(`${BASE}/embeddings/search`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(body),
  }).promise
},
```

Add new method:
```typescript
encodeImage: (file: File, embedding?: string): Promise<EmbeddingEncodeResponse> => {
  const fd = new FormData()
  fd.append('file', file)
  if (embedding) fd.append('embedding', embedding)
  return fetchJSON<EmbeddingEncodeResponse>(`${BASE}/embeddings/encode`, {
    method: 'POST',
    body: fd,
  }).promise
},
```


## Phased Delivery Plan (Adjusted)

### Phase 2.0 - One-Key Search + Better Banner (Priority: Do First)

**Goal**: Make similarity search frictionless for the 90% case.

**Tasks**:
1. **Add `S` keyboard shortcut** in `AppShell.tsx`
   - In existing `useEffect` keyboard handler (~line 1505)
   - Check: `!isInputElement(e.target) && selectedPaths.length === 1 && embeddingsAvailable`
   - Action: Call `handleSimilaritySearch()` with defaults `{embedding: embeddings[0].name, query_path: selectedPaths[0], top_k: 50, min_score: 0.2}`
   
2. **Enhance similarity banner** (~line 1664-1686)
   - Add query image thumbnail (32px)
   - Add "Search from selection" button
   - Add "Copy query" button
   - Show score range (min/max from results)

3. **Add `Escape` to clear similarity** in keyboard handler
   - When `similarityActive`, call `clearSimilarity()`

**Validation**: Select image → Press S → See results instantly. Press Escape → Back to normal.

### Phase 2.1 - Similarity as Transient Metric

**Goal**: Similarity score becomes sortable/filterable like any other metric.

**Tasks**:
1. **Inject `similarity_score` into items** in `AppShell.tsx`
   - Modify `similarityItems` useMemo (~line 346-353)
   - Map items with their scores from `similarityState.items`
   
2. **Add `similarity_score` to metricKeys** when active
   - In `metricKeys` useMemo (~line 659-674)
   - Prepend `'similarity_score'` when `similarityActive`
   
3. **Enable sorting** by removing `sortDisabled={similarityActive}`
   - In Toolbar props (~line 1589)
   - Add `sortBySimilarity` to `apply.ts` sorters
   
4. **Show in MetricsPanel** histogram
   - `similarity_score` appears as range slider
   - Filtering by score works like other metrics

**Validation**: Start similarity search → Sort by rating → Filter by score > 0.8 → All work together.

### Phase 2.2 - Embeddings Status UI

**Goal**: Surface embedding availability and errors clearly.

**Tasks**:
1. **Enhance `GET /embeddings` response** in `server.py`
   - Add `backend` field ("faiss" | "numpy" | "not_loaded")
   - Add `row_count` field
   - Add `backend_available` top-level field

2. **Add Embeddings section to LeftSidebar** or MetricsPanel
   - Show available embeddings with status
   - Show rejected columns with reasons
   - Add "Find similar" button (alternative to S key)

3. **Inline error states** in Embeddings panel
   - "No embeddings found" with guidance
   - "NumPy not installed" with install command
   - Search errors shown in-panel, not just toasts

**Validation**: Start server without embeddings → See guidance. Start with embeddings → See list with status.

### Phase 2.3 - Query History + Reproducibility

**Goal**: Make queries reproducible and shareable.

**Tasks**:
1. **Store query history in localStorage**
   - Save last 5 queries per embedding column
   - Structure: `{embedding, queryPath, topK, minScore, resultCount, timestamp}`

2. **Add "Copy query JSON" button** in similarity banner
   - Full query parameters for reproducibility
   - Include version for forward compatibility

3. **Add history dropdown** in advanced panel
   - Show recent queries with thumbnail preview
   - Click to re-run query

**Validation**: Run query → Copy JSON → Clear → Paste into "Load query" → Same results.

### Phase 2.4 - Dedupe Workflow (Optional/Later)

**Goal**: Find and handle near-duplicates efficiently.

**Tasks**:
1. **Add `POST /embeddings/duplicates` endpoint**
   - Accept threshold, min cluster size, max clusters
   - Return clusters with representative + members

2. **Add "Find duplicates" UI**
   - Button in Embeddings panel
   - Modal showing cluster list
   - Actions: select all, tag, trash

**Validation**: Click "Find duplicates" → See clusters → Select cluster → All members selected in grid.

**Note**: This phase is lower priority than 2.0-2.2. Can be deferred to Phase 3 if needed.


## Risks & Mitigations

- **Performance**: Large datasets with CPU-only embeddings may be slow.
  - Mitigation: warn on large queries, provide progress + cancel, allow `top_k` cap.
- **Model mismatch**: Query vector from a different model vs stored embeddings.
  - Mitigation: hard match by column; if mismatch, disable search and explain.
- **Privacy**: URL fetching could pull remote content.
  - Mitigation: URL support off by default; require explicit config flag.


## Acceptance Criteria (Concrete)

- User can run similarity search from selected image and uploaded image without leaving the gallery.
- Similarity works as a filter; filters and sort remain active and combinable.
- The UI shows embedding column, metric, and query source at all times.
- "Copy query JSON" reproduces the result when pasted back.
- Near-duplicate workflow yields clusters with bulk actions.
- Errors for missing deps appear in the Embeddings panel with guidance.


## Out of Scope (Phase 2)

- GPU acceleration UI controls (can be Phase 3)
- Full clustering/UMAP visualization
- Cloud sync or remote index hosting


## Open Questions (With Recommendations)

### Q1: Should URL support be on by default for localhost-only deployments?

**Recommendation**: No. Keep URL fetch disabled by default everywhere.

**Rationale**: Security principle of least privilege. Users who need URL fetch can enable it explicitly with `--allow-url-fetch`. This avoids accidental SSRF issues even in local deployments (e.g., if someone port-forwards or shares a tunnel).

### Q2: Do we allow multiple embedding columns simultaneously, or enforce one active column?

**Recommendation**: One active column at a time, but easy switching.

**Rationale**: 
- Multiple simultaneous searches adds UI complexity (which results to show?)
- The common workflow is: pick a model, explore, maybe switch models to compare
- "Active embedding" dropdown in the banner makes switching fast
- If users want to compare models, they can search, note results, switch, search again

**Implementation note**: Current `similarityState` in `AppShell.tsx` stores single `embedding` string—this matches the one-at-a-time model.

### Q3: Should similarity scoring run on the full dataset or only the filtered subset?

**Recommendation**: Full dataset by default, but with "filtered only" option.

**Rationale**:
- Full dataset search is the expected behavior ("find similar anywhere")
- Backend already searches full index, then frontend filters results
- Adding "search within current filter" option is useful for large datasets
- UI: checkbox "Search filtered items only" in advanced panel

**Current behavior** (from `AppShell.tsx` line 1357-1361): Similarity results are filtered by current filters but scored against full dataset. This is correct—keep it.

### Q4: Should the modal be removed entirely or just bypassed?

**Recommendation**: Keep modal for advanced use, bypass for quick search.

**Rationale**:
- `S` key bypasses modal for 90% case (select image, quick search)
- Modal still needed for: vector input, adjusting top_k/min_score, uploading image
- "Adjust" button in banner opens modal/panel for fine-tuning
- Users who prefer modal workflow can use "Find similar" button in Inspector

### Q5: Where should the Embeddings panel live in the UI?

**Recommendation**: Add as third tab in left sidebar (alongside Folders/Metrics).

**Rationale from codebase**:
- `LeftSidebar.tsx` already has `leftTool: 'folders' | 'metrics'` pattern
- Easy to add `| 'embeddings'` to the union type
- Icon bar has space for third button
- Keeps Metrics panel focused on numeric metrics, Embeddings panel on vector search

**Alternative considered**: Integrate into Metrics panel. Rejected because embeddings are fundamentally different (search, not filter-by-range).

### Q6: How should similarity_score appear in the grid?

**Recommendation**: Small badge overlay (top-right corner), opt-in via settings.

**Rationale**:
- Keeps grid clean by default
- Score is visible when you need it (similarity mode active)
- Color-coded: green >0.9, yellow 0.7-0.9, gray <0.7
- Can be disabled for distraction-free browsing

**Implementation note**: Grid cells are in `VirtualGrid.tsx`. Badge is a simple absolute-positioned element, only rendered when `similarityActive` and item has `similarity_score`.
