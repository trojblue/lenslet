export type Mime = 'image/webp' | 'image/jpeg' | 'image/png'
export type Item = { path: string; name: string; type: Mime; w: number; h: number; size: number; hasThumb: boolean; hasMeta: boolean; hash?: string; addedAt?: string | null }
export type DirEntry = { name: string; kind: 'branch' | 'leaf-real' | 'leaf-pointer' }
export type FolderIndex = { v: 1; path: string; generatedAt: string; items: Item[]; dirs: DirEntry[]; page?: number; pageCount?: number }
export type Sidecar = { v: 1; tags: string[]; notes: string; exif?: { width?: number; height?: number; created_at?: string }; hash?: string; original_position?: string; star?: number | null; updated_at: string; updated_by: string }
export type PointerCfg = { version: number; kind: 'pointer'; target: { type: 's3' | 'local'; bucket?: string; prefix?: string; region?: string; path?: string }; label?: string; readonly?: boolean }
