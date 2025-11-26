/** Supported image MIME types */
export type Mime = 'image/webp' | 'image/jpeg' | 'image/png'

/** A single gallery item (image file) */
export interface Item {
  path: string
  name: string
  type: Mime
  w: number
  h: number
  size: number
  hasThumb: boolean
  hasMeta: boolean
  hash?: string
  addedAt?: string | null
  star?: number | null
}

/** Directory entry in the folder tree */
export interface DirEntry {
  name: string
  kind: 'branch' | 'leaf-real' | 'leaf-pointer'
}

/** Folder index response from the API */
export interface FolderIndex {
  v: 1
  path: string
  generatedAt: string
  items: Item[]
  dirs: DirEntry[]
  page?: number
  pageCount?: number
}

/** Sidecar metadata for an item */
export interface Sidecar {
  v: 1
  tags: string[]
  notes: string
  exif?: {
    width?: number
    height?: number
    created_at?: string
  }
  hash?: string
  original_position?: string
  star?: number | null
  updated_at: string
  updated_by: string
}

/** Pointer configuration for external sources */
export interface PointerCfg {
  version: number
  kind: 'pointer'
  target: {
    type: 's3' | 'local'
    bucket?: string
    prefix?: string
    region?: string
    path?: string
  }
  label?: string
  readonly?: boolean
}

/** Sort direction */
export type SortDir = 'asc' | 'desc'

/** Sort key options */
export type SortKey = 'name' | 'added'

/** Star rating value (0-5, null for unset) */
export type StarRating = 0 | 1 | 2 | 3 | 4 | 5 | null

/** Context menu item kind */
export type ContextMenuKind = 'tree' | 'grid'

/** Context menu state */
export interface ContextMenuState {
  x: number
  y: number
  kind: ContextMenuKind
  payload: { path?: string; paths?: string[] }
}

/** API response for file operations */
export interface FileOpResponse {
  ok: boolean
  path?: string
}

/** Search results from the API */
export interface SearchResult {
  items: Item[]
}
