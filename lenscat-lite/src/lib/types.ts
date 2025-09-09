export type Mime = 'image/webp' | 'image/jpeg' | 'image/png'
export type Item = { path: string; name: string; type: Mime; w: number; h: number; size: number; hasThumb: boolean; hasMeta: boolean; hash?: string }
export type DirEntry = { name: string; kind: 'branch' | 'leaf-real' | 'leaf-pointer' }
export type FolderIndex = { v: 1; path: string; generatedAt: string; items: Item[]; dirs: DirEntry[]; page?: number; pageCount?: number }
export type Sidecar = { v: 1; tags: string[]; notes: string; exif?: { width?: number; height?: number; createdAt?: string }; hash?: string; updatedAt: string; updatedBy: string }
export type PointerCfg = { version: number; kind: 'pointer'; target: { type: 's3' | 'local'; bucket?: string; prefix?: string; region?: string; path?: string }; label?: string; readonly?: boolean }
