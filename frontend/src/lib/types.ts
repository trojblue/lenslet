export type Mime = 'image/webp' | 'image/jpeg' | 'image/png'

export type Item = {
  path: string
  name: string
  type: Mime
  w: number
  h: number
  size: number
  hasThumb: boolean
  hasMeta: boolean
  hash?: string | null
  addedAt?: string | null
  star?: StarRating | null
  comments?: string | null
  url?: string | null
  source?: string | null
  metrics?: Record<string, number | null>
}

export type DirEntry = {
  name: string
  kind: 'branch' | 'leaf-real' | 'leaf-pointer'
}

export type FolderIndex = {
  v: 1
  path: string
  generatedAt: string
  items: Item[]
  dirs: DirEntry[]
  page?: number
  pageSize?: number
  pageCount?: number
  totalItems?: number
}

export type Sidecar = {
  v: 1
  tags: string[]
  notes: string
  exif?: { width?: number; height?: number; createdAt?: string }
  hash?: string | null
  original_position?: string | null
  star?: StarRating | null
  version: number
  updated_at: string
  updated_by: string
}

export type SidecarPatch = {
  base_version?: number
  set_star?: StarRating | null
  set_notes?: string
  set_tags?: string[]
  add_tags?: string[]
  remove_tags?: string[]
}

export type ItemUpdatedEvent = {
  path: string
  version: number
  tags: string[]
  notes: string
  star: StarRating | null
  updated_at: string
  updated_by: string
  metrics?: Record<string, number | null>
}

export type MetricsUpdatedEvent = {
  path: string
  version: number
  metrics: Record<string, number | null>
  updated_at: string
  updated_by: string
}

export type PresenceEvent = {
  gallery_id: string
  viewing: number
  editing: number
}

export type HealthResponse = {
  ok: boolean
  labels?: {
    enabled: boolean
    log?: string | null
    snapshot?: string | null
  }
  presence?: {
    lifecycle_v2_enabled?: boolean
    active_clients?: number
    active_scopes?: number
    stale_pruned_total?: number
    invalid_lease_total?: number
    replay_miss_total?: number
  }
}

export type SearchResult = { items: Item[] }

export type EmbeddingSpec = {
  name: string
  dimension: number
  dtype: string
  metric: string
}

export type EmbeddingRejected = {
  name: string
  reason: string
}

export type EmbeddingsResponse = {
  embeddings: EmbeddingSpec[]
  rejected: EmbeddingRejected[]
}

export type EmbeddingSearchRequest = {
  embedding: string
  query_path?: string | null
  query_vector_b64?: string | null
  top_k?: number
  min_score?: number | null
}

export type EmbeddingSearchItem = {
  row_index: number
  path: string
  score: number
}

export type EmbeddingSearchResponse = {
  embedding: string
  items: EmbeddingSearchItem[]
}

export type FileOpResponse = {
  ok: boolean
  error?: string
  path?: string
  dest?: string
}

export type RefreshResponse = {
  ok: boolean
  note?: string
}

export type ImageMetadataResponse = {
  path: string
  format: 'png' | 'jpeg' | 'webp'
  meta: Record<string, unknown>
}

export type ViewMode = 'grid' | 'adaptive'

export type SortSpec =
  | { kind: 'builtin'; key: 'added' | 'name' | 'random'; dir: 'asc' | 'desc' }
  | { kind: 'metric'; key: string; dir: 'asc' | 'desc' }

export type FilterClause =
  | { stars: number[] }
  | { starsIn: { values: number[] } }
  | { starsNotIn: { values: number[] } }
  | { nameContains: { value: string } }
  | { nameNotContains: { value: string } }
  | { commentsContains: { value: string } }
  | { commentsNotContains: { value: string } }
  | { urlContains: { value: string } }
  | { urlNotContains: { value: string } }
  | { dateRange: { from?: string; to?: string } }
  | { widthCompare: { op: '<' | '<=' | '>' | '>='; value: number } }
  | { heightCompare: { op: '<' | '<=' | '>' | '>='; value: number } }
  | { metricRange: { key: string; min: number; max: number } }

export type FilterAST = {
  and: FilterClause[]
}

export type ViewState = {
  filters: FilterAST
  sort: SortSpec
  selectedMetric?: string
}

export type ViewPool = { kind: 'folder'; path: string }

export type SavedView = {
  id: string
  name: string
  pool: ViewPool
  view: ViewState
}

export type ViewsPayload = {
  version: number
  views: SavedView[]
}

export type ContextMenuState =
  | { kind: 'tree'; x: number; y: number; payload: { path: string } }
  | { kind: 'grid'; x: number; y: number; payload: { paths: string[] } }

export type StarRating = 0 | 1 | 2 | 3 | 4 | 5 | null
