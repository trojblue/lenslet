Below is a tiny, opinionated boilerplate you can paste into a new repo. It’s React + Vite + TypeScript, TanStack Query, and @tanstack/react-virtual for the grid. No global store, no UI kit, no CSS-in-JS. Just enough structure to stop developer sprawl.

---

## Project Structure
```
lenscat-lite/
├─ package.json
├─ tsconfig.json
├─ vite.config.ts
├─ index.html
├─ src/
│  ├─ main.tsx
│  ├─ App.tsx
│  ├─ styles.css
│  ├─ lib/
│  │  ├─ types.ts
│  │  ├─ fetcher.ts
│  │  ├─ lru.ts
│  │  ├─ keyboard.ts
│  │  └─ util.ts
│  ├─ api/
│  │  ├─ client.ts
│  │  ├─ folders.ts
│  │  ├─ items.ts
│  │  └─ search.ts
│  ├─ components/
│  │  ├─ FolderTree.tsx
│  │  ├─ Grid.tsx
│  │  ├─ Thumb.tsx
│  │  ├─ Inspector.tsx
│  │  └─ Toolbar.tsx
│  ├─ hooks/
│  │  ├─ useSelection.ts
│  │  └─ useInspector.ts
│  └─ theme.css
└─ README.md
```

---

## package.json (minimal deps)
```json
{
  "name": "lenscat-lite",
  "private": true,
  "version": "0.1.0",
  "type": "module",
  "scripts": {
    "dev": "vite",
    "build": "vite build",
    "preview": "vite preview"
  },
  "dependencies": {
    "react": "^18.3.1",
    "react-dom": "^18.3.1",
    "@tanstack/react-query": "^5.51.1",
    "@tanstack/react-virtual": "^3.1.1"
  },
  "devDependencies": {
    "typescript": "^5.5.4",
    "vite": "^5.4.8",
    "@types/react": "^18.3.5",
    "@types/react-dom": "^18.3.0",
    "eslint": "^9.9.0"
  }
}
```

## tsconfig.json
```json
{
  "compilerOptions": {
    "target": "ES2021",
    "useDefineForClassFields": true,
    "lib": ["ES2021", "DOM", "DOM.Iterable"],
    "module": "ESNext",
    "skipLibCheck": true,
    "moduleResolution": "Bundler",
    "resolveJsonModule": true,
    "isolatedModules": true,
    "noEmit": true,
    "jsx": "react-jsx",
    "strict": true
  },
  "include": ["src"]
}
```

## vite.config.ts
```ts
import { defineConfig } from 'vite'
import react from '@vitejs/plugin-react'
export default defineConfig({ plugins: [react()] })
```

## index.html
```html
<!doctype html>
<html lang="en">
  <head>
    <meta charset="UTF-8" />
    <meta name="viewport" content="width=device-width, initial-scale=1.0" />
    <title>Lenscat-lite</title>
  </head>
  <body>
    <div id="root"></div>
    <script type="module" src="/src/main.tsx"></script>
  </body>
</html>
```

---

## src/theme.css (minimal Eagle-ish theme)
```css
:root {
  --bg: #1e1e1e;
  --panel: #252525;
  --hover: #2a2a2a;
  --text: #eeeeee;
  --muted: #aaaaaa;
  --accent: #3a8fff;
  --border: rgba(255,255,255,0.08);
}
* { box-sizing: border-box }
html,body,#root { height: 100%; background: var(--bg); color: var(--text); }
body { margin: 0; font: 14px/1.4 system-ui, -apple-system, Segoe UI, Roboto, sans-serif; }

.app { display: grid; grid-template-columns: 260px 1fr 360px; grid-template-rows: 48px 1fr; height: 100%; }
.toolbar { grid-column: 1 / -1; grid-row: 1; display: flex; align-items: center; gap: 8px; padding: 8px 12px; border-bottom: 1px solid var(--border); background: var(--panel); }
.sidebar { grid-column: 1; grid-row: 2; overflow: auto; border-right: 1px solid var(--border); background: var(--panel); }
.main { grid-column: 2; grid-row: 2; position: relative; }
.inspector { grid-column: 3; grid-row: 2; border-left: 1px solid var(--border); background: var(--panel); overflow: auto; }

/* Grid cells */
.grid { height: 100%; overflow: auto; padding: 12px; }
.cell { position: relative; background: var(--hover); border: 1px solid var(--border); border-radius: 8px; overflow: hidden; width: 100%; aspect-ratio: 1 / 1; contain: content; content-visibility: auto; contain-intrinsic-size: 200px 200px; }
.cell:hover { outline: 1px solid var(--accent); transform: translateZ(0); }
.thumb { width: 100%; height: 100%; object-fit: cover; display: block; }
.meta { position: absolute; left: 6px; bottom: 6px; padding: 2px 6px; background: rgba(0,0,0,0.5); border-radius: 6px; color: var(--text); font-size: 12px; }

/* Tree */
.tree { padding: 8px; }
.tree-item { padding: 6px 8px; border-radius: 6px; cursor: pointer; }
.tree-item.active { background: rgba(58,143,255,0.2); border-left: 2px solid var(--accent); }
.tree-item:hover { background: #2a2a2a; }

/* Inspector */
.panel { padding: 12px; border-bottom: 1px solid var(--border); }
.label { color: var(--muted); font-size: 12px; text-transform: uppercase; letter-spacing: 0.06em; getBoundingClientRect().height: 6px; }
.input, .textarea { width: 100%; background: #1b1b1b; color: var(--text); border: 1px solid var(--border); border-radius: 8px; padding: 8px; }
.textarea { min-height: 100px; resize: vertical; }
.url { font-family: ui-monospace, SFMono-Regular, Menlo, Consolas, monospace; color: var(--muted); word-break: break-all; }
```

## src/styles.css
```css
@import './theme.css';
```

---

## src/lib/types.ts
```ts
export type Mime = 'image/webp' | 'image/jpeg' | 'image/png'
export type Item = { path: string; name: string; type: Mime; w: number; h: number; size: number; hasThumb: boolean; hasMeta: boolean; hash?: string }
export type DirEntry = { name: string; kind: 'branch' | 'leaf-real' | 'leaf-pointer' }
export type FolderIndex = { v: 1; path: string; generatedAt: string; items: Item[]; dirs: DirEntry[]; page?: number; pageCount?: number }
export type Sidecar = { v: 1; tags: string[]; notes: string; exif?: { width?: number; height?: number; createdAt?: string }; hash?: string; updatedAt: string; updatedBy: string }
export type PointerCfg = { version: number; kind: 'pointer'; target: { type: 's3' | 'local'; bucket?: string; prefix?: string; region?: string; path?: string }; label?: string; readonly?: boolean }
```

## src/lib/fetcher.ts (abortable fetch helper)
```ts
export function fetchJSON<T>(url: string, opts: RequestInit = {}) {
  const ctrl = new AbortController()
  const promise = fetch(url, { ...opts, signal: ctrl.signal }).then(r => {
    if (!r.ok) throw new Error(`HTTP ${r.status} for ${url}`)
    return r.json() as Promise<T>
  })
  return { promise, abort: () => ctrl.abort() }
}

export function fetchBlob(url: string, opts: RequestInit = {}) {
  const ctrl = new AbortController()
  const promise = fetch(url, { ...opts, signal: ctrl.signal }).then(r => {
    if (!r.ok) throw new Error(`HTTP ${r.status} for ${url}`)
    return r.blob()
  })
  return { promise, abort: () => ctrl.abort() }
}
```

## src/lib/lru.ts (tiny in-memory LRU for thumbs)
```ts
export class LRU<K, V> {
  private map = new Map<K, V>()
  constructor(private cap = 300) {}
  get(k: K) { const v = this.map.get(k); if (v) { this.map.delete(k); this.map.set(k, v) } return v }
  set(k: K, v: V) {
    if (this.map.has(k)) this.map.delete(k)
    this.map.set(k, v)
    if (this.map.size > this.cap) { const first = this.map.keys().next().value; this.map.delete(first) }
  }
}
```

## src/lib/keyboard.ts (cheap shortcuts)
```ts
type Handler = (e: KeyboardEvent) => void
export function onKey(key: string, handler: Handler) {
  const h = (e: KeyboardEvent) => { if (e.key === key) handler(e) }
  window.addEventListener('keydown', h)
  return () => window.removeEventListener('keydown', h)
}
```

## src/lib/util.ts
```ts
export const fmtBytes = (n: number) => {
  const u = ['B','KB','MB','GB']; let i = 0; while (n >= 1024 && i < u.length-1) { n/=1024; i++ } return `${n.toFixed(1)} ${u[i]}`
}
```

---

## src/api/client.ts (thin client, no abstraction circus)
```ts
import { fetchJSON, fetchBlob } from '../lib/fetcher'
import type { FolderIndex, Sidecar } from '../lib/types'

const BASE = import.meta.env.VITE_API_BASE ?? ''

export const api = {
  getFolder: (path: string, page?: number) => fetchJSON<FolderIndex>(`${BASE}/folders?path=${encodeURIComponent(path)}${page!=null?`&page=${page}`:''}`).promise,
  getSidecar: (path: string) => fetchJSON<Sidecar>(`${BASE}/item?path=${encodeURIComponent(path)}`).promise,
  putSidecar: (path: string, body: Sidecar) => fetchJSON<Sidecar>(`${BASE}/item?path=${encodeURIComponent(path)}`, { method: 'PUT', headers: { 'content-type': 'application/json' }, body: JSON.stringify(body) }).promise,
  getThumb: (path: string) => fetchBlob(`${BASE}/thumb?path=${encodeURIComponent(path)}`).promise
}
```

## src/api/folders.ts (query hooks)
```ts
import { useQuery } from '@tanstack/react-query'
import { api } from './client'

export function useFolder(path: string) {
  return useQuery({ queryKey: ['folder', path], queryFn: () => api.getFolder(path), staleTime: 5_000 })
}
```

## src/api/items.ts
```ts
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import { api } from './client'
import type { Sidecar } from '../lib/types'

export function useSidecar(path: string) {
  return useQuery({ queryKey: ['item', path], queryFn: () => api.getSidecar(path) })
}

export function useUpdateSidecar(path: string) {
  const qc = useQueryClient()
  return useMutation({
    mutationFn: (next: Sidecar) => api.putSidecar(path, next),
    onSuccess: (data) => { qc.setQueryData(['item', path], data) }
  })
}
```

## src/api/search.ts
```ts
import { useQuery } from '@tanstack/react-query'
import { fetchJSON } from '../lib/fetcher'
import type { Item } from '../lib/types'
const BASE = import.meta.env.VITE_API_BASE ?? ''
export function useSearch(q: string) {
  return useQuery({ enabled: !!q, queryKey: ['search', q], queryFn: () => fetchJSON<{ items: Item[] }>(`${BASE}/search?q=${encodeURIComponent(q)}`).promise })
}
```

---

## src/hooks/useSelection.ts (simple selection state)
```ts
import { useState } from 'react'
export function useSelection() {
  const [selected, set] = useState<string | null>(null)
  return { selected, select: set }
}
```

## src/hooks/useInspector.ts
```ts
import { useMemo } from 'react'
import { useSidecar } from '../api/items'
export function useInspector(path: string | null) {
  const q = useSidecar(path ?? '')
  return useMemo(() => ({ path, sidecar: q.data, loading: q.isLoading, error: q.error as Error | null }), [path, q.data, q.isLoading, q.error])
}
```

---

## src/components/Toolbar.tsx
```tsx
import React from 'react'
export default function Toolbar({ onSearch }: { onSearch: (q: string) => void }) {
  return (
    <div className="toolbar">
      <input placeholder="Search filename, tags, notes…" onChange={e=>onSearch(e.target.value)} className="input" style={{width: 360}} />
    </div>
  )
}
```

## src/components/FolderTree.tsx
```tsx
import React from 'react'
import type { FolderIndex } from '../lib/types'

export default function FolderTree({ current, roots, onOpen }:{ current: string; roots: { label: string; path: string }[]; onOpen:(p:string)=>void }){
  return (
    <div className="sidebar">
      <div className="tree">
        {roots.map(r => (
          <div key={r.path} className={`tree-item ${current===r.path?'active':''}`} onClick={()=>onOpen(r.path)}>
            {r.label}
          </div>
        ))}
      </div>
    </div>
  )
}
```

## src/components/Thumb.tsx
```tsx
import React, { useEffect, useState } from 'react'
import { api } from '../api/client'

const blobUrlCache = new Map<string, string>()

export default function Thumb({ path, name, onClick }:{ path:string; name:string; onClick:()=>void }){
  const [url, setUrl] = useState<string | null>(blobUrlCache.get(path) ?? null)
  useEffect(() => {
    let alive = true
    if (!url) {
      const { promise } = api.getThumb(path)
      promise.then(b => { if (!alive) return; const u = URL.createObjectURL(b); blobUrlCache.set(path, u); setUrl(u) })
             .catch(()=>{})
    }
    return () => { alive = false }
  }, [path])
  return (
    <div className="cell" style={{ height: rowH - gap }} onClick={onClick}>
      {url ? <img className="thumb" src={url} alt={name} loading="lazy" decoding="async" /> : null}
      <div className="meta">{name}</div>
    </div>
  )
}
```

## src/components/Grid.tsx
```tsx
import React, { useMemo, useRef } from 'react'
import { useVirtualizer } from '@tanstack/react-virtual'
import type { Item } from '../lib/types'
import Thumb from './Thumb'

export default function Grid({ items, onOpen }:{ items: Item[]; onOpen:(p:string)=>void }){
  const parentRef = useRef<HTMLDivElement | null>(null)
  const columnWidth = 220 // includes padding/gap; adjust with CSS
  const gap = 12
  const columns = Math.max(1, Math.floor((parentRef.current?.clientWidth ?? 800) / (columnWidth + gap)))
  const rowCount = Math.ceil(items.length / columns)

  const rowVirtualizer = useVirtualizer({
    count: rowCount,
    getScrollElement: () => parentRef.current,
    estimateSize: () => columnWidth + gap,
    overscan: 4
  })

  const rows = rowVirtualizer.getVirtualItems()

  return (
    <div className="grid" ref={parentRef}>
      <div style={{ height: rowVirtualizer.getTotalSize(), width: '100%', position: 'relative' }}>
        {rows.map(row => {
          const start = row.index * columns
          const slice = items.slice(start, start + columns)
          return (
            <div key={row.key} style={{ position: 'absolute', top: 0, left: 0, transform: `translateY(${row.start}px)`, display: 'grid', gridTemplateColumns: `repeat(${columns}, 1fr)`, gap }}>
              {slice.map(it => (
                <Thumb key={it.path} path={it.path} name={it.name} onClick={()=>onOpen(it.path)} />
              ))}
            </div>
          )
        })}
      </div>
    </div>
  )
}
```

## src/components/Inspector.tsx
```tsx
import React, { useEffect, useMemo, useState } from 'react'
import { useSidecar, useUpdateSidecar } from '../api/items'
import { fmtBytes } from '../lib/util'

export default function Inspector({ path, item }:{ path: string | null; item?: { size:number; w:number; h:number; type:string; } }){
  const enabled = !!path
  const { data, isLoading } = useSidecar(path ?? '', )
  const mut = useUpdateSidecar(path ?? '')
  const [tags, setTags] = useState<string>('')
  const [notes, setNotes] = useState<string>('')

  useEffect(() => { if (data) { setTags((data.tags||[]).join(', ')); setNotes(data.notes||'') } }, [data?.updatedAt])

  if (!enabled) return <div className="inspector" />
  return (
    <div className="inspector">
      <div className="panel">
        <div className="label">Details</div>
        <div style={{display:'grid', gridTemplateColumns:'1fr 1fr', gap:8}}>
          <div>Type<br/><span className="url">{item?.type}</span></div>
          <div>Size<br/><span className="url">{item? fmtBytes(item.size): '-'}</span></div>
          <div>Dims<br/><span className="url">{item? `${item.w}×${item.h}`: '-'}</span></div>
        </div>
      </div>
      <div className="panel">
        <div className="label">Tags (comma-separated)</div>
        <input className="input" value={tags} onChange={e=>setTags(e.target.value)} onBlur={()=> mut.mutate({ ...(data||{v:1,tags:[],notes:''}), tags: tags.split(',').map(s=>s.trim()).filter(Boolean), updatedAt: new Date().toISOString(), updatedBy: 'web' })} />
      </div>
      <div className="panel">
        <div className="label">Notes</div>
        <textarea className="textarea" value={notes} onChange={e=>setNotes(e.target.value)} onBlur={()=> mut.mutate({ ...(data||{v:1,tags:[],notes:''}), notes, updatedAt: new Date().toISOString(), updatedBy: 'web' })} />
      </div>
      <div className="panel">
        <div className="label">Source URL</div>
        <div className="url">{path}</div>
      </div>
    </div>
  )
}
```

## src/App.tsx
```tsx
import React, { useMemo, useState } from 'react'
import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import Toolbar from './components/Toolbar'
import FolderTree from './components/FolderTree'
import Grid from './components/Grid'
import Inspector from './components/Inspector'
import { useFolder } from './api/folders'
import './styles.css'

const qc = new QueryClient()

export default function AppRoot(){
  return (
    <QueryClientProvider client={qc}>
      <App/>
    </QueryClientProvider>
  )
}

function App(){
  const [current, setCurrent] = useState<string>('/')
  const [query, setQuery] = useState('')
  const [selected, setSelected] = useState<string | null>(null)
  const { data } = useFolder(current)

  const items = useMemo(()=> data?.items ?? [], [data])

  return (
    <div className="app">
      <Toolbar onSearch={setQuery} />
      <FolderTree current={current} roots={[{label:'Root', path:'/'}]} onOpen={setCurrent} />
      <div className="main">
        <Grid items={items} onOpen={(p)=>{ setSelected(p) }} />
      </div>
      <Inspector path={selected} item={items.find(i=>i.path===selected) ?? undefined} />
    </div>
  )
}
```

## src/main.tsx
```tsx
import React from 'react'
import { createRoot } from 'react-dom/client'
import App from './App'
createRoot(document.getElementById('root')!).render(<App />)
```

---

## README.md (operational notes)
```md
# Lenscat-lite (Frontend Boilerplate)
Fast, minimal gallery UI. Bring your own FastAPI.

## Why this is not bloat
- No global store, no UI kit, no CSS-in-JS.
- Query cache + virtual grid only.
- CSS variables for theming.
- Abortable fetch helper, 30 lines total infra.

## Env
- `VITE_API_BASE` -> backend base URL

## Perf checklist
- Thumbnails only in grid (server should serve `<file>.thumbnail`).
- Use folder manifests (`_index.json`) for aspect boxes to avoid CLS.
- Overscan small (4 rows), AbortController cancels offscreen fetches.

## Extend
- Add more sources by extending backend; UI stays the same.
- Drop-in Tauri later by swapping `api/client.ts` with host bridge.
```

---

**Use this as a floor, not a ceiling.** It compiles fast, it doesn’t lecture you, and it’s extremely hard to “accidentally” turn into a 60MB SPA. Add what you need, and nothing else.

