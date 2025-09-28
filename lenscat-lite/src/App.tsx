import React, { useEffect, useMemo, useRef, useState } from 'react'
import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import Toolbar from './components/Toolbar'
import FolderTree from './components/FolderTree'
import Grid from './components/Grid'
import Viewer from './components/Viewer'
import Inspector from './components/Inspector'
import { useFolder } from './api/folders'
import { useSearch } from './api/search'
import { api } from './api/client'
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
  const [selectedPaths, setSelectedPaths] = useState<string[]>([])
  const [viewer, setViewer] = useState<string | null>(null)
  const [requestedZoom, setRequestedZoom] = useState<number | null>(null)
  const [currentZoom, setCurrentZoom] = useState<number>(100)
  const [leftW, setLeftW] = useState<number>(160)
  const [rightW, setRightW] = useState<number>(240)
  const [sortKey, setSortKey] = useState<'name'|'added'>('added')
  const [sortDir, setSortDir] = useState<'asc'|'desc'>('desc')
  const [starFilters, setStarFilters] = useState<number[] | null>(null)
  const [localStarOverrides, setLocalStarOverrides] = useState<Record<string, number | null>>({})
  const appRef = useRef<HTMLDivElement | null>(null)
  const viewerHistoryPushedRef = useRef(false)
  const leftWRef = useRef(leftW)
  const rightWRef = useRef(rightW)
  useEffect(() => { leftWRef.current = leftW }, [leftW])
  useEffect(() => { rightWRef.current = rightW }, [rightW])
  const ALLOWED_PATH = /^[\/@a-zA-Z0-9._\-\/]{1,512}$/
  function sanitizePath(raw: string | null | undefined): string {
    try {
      const decoded = decodeURI(raw || '')
      const withLeading = decoded.startsWith('/') ? decoded : `/${decoded}`
      const squashed = withLeading.replace(/\/{2,}/g, '/')
      if (!ALLOWED_PATH.test(squashed)) return '/'
      return squashed
    } catch {
      return '/'
    }
  }
  // load from localStorage after mount; ignore if access is blocked
  useEffect(() => {
    try {
      const ls = window.localStorage
      const lv = Number(ls.getItem('leftW'))
      if (Number.isFinite(lv) && lv > 0) setLeftW(lv)
      const rv = Number(ls.getItem('rightW'))
      if (Number.isFinite(rv) && rv > 0) setRightW(rv)
    } catch {}
  }, [])
  const { data, refetch } = useFolder(current)
  const searching = query.trim().length > 0
  const search = useSearch(searching ? query : '')

  const items = useMemo(()=> {
    // Determine base list: search results when searching, otherwise folder items
    const base = searching ? (search.data?.items ?? []) : (data?.items ?? [])
    // merge live star overrides so filtered items disappear immediately after edits
    const merged = base.map(it => ({ ...it, star: (localStarOverrides[it.path]!==undefined ? localStarOverrides[it.path] : it.star) }))
    const arr = [...merged]
    if (sortKey === 'name') {
      arr.sort((a,b)=> a.name.localeCompare(b.name))
    } else {
      // addedAt may be missing; fallback to name for stability
      arr.sort((a,b)=> {
        const ta = a.addedAt ? Date.parse(a.addedAt) : 0
        const tb = b.addedAt ? Date.parse(b.addedAt) : 0
        if (ta === tb) return a.name.localeCompare(b.name)
        return ta - tb
      })
    }
    if (sortDir === 'desc') arr.reverse()
    // Apply star filter
    const filtered = arr.filter(it => {
      if (!starFilters || !starFilters.length) return true
      const val = it.star ?? 0
      // Treat 0 as None; only match when 0 is in filters
      return starFilters.includes(val)
    })
    return filtered
  }, [searching, search.data, data, sortKey, sortDir, starFilters, localStarOverrides])

  // Clear selection and viewer when entering a search
  useEffect(() => {
    if (searching) {
      setSelectedPaths([])
      setViewer(null)
    }
  }, [searching])

  // Load persisted sort on mount
  useEffect(() => {
    try {
      const ls = window.localStorage
      const sk = ls.getItem('sortKey') as any
      const sd = ls.getItem('sortDir') as any
      const sf = ls.getItem('starFilters')
      if (sk === 'name' || sk === 'added') setSortKey(sk)
      if (sd === 'asc' || sd === 'desc') setSortDir(sd)
      if (sf) { try { const arr = JSON.parse(sf); if (Array.isArray(arr)) setStarFilters(arr.filter((n:any)=>[0,1,2,3,4,5].includes(n))) } catch {} }
    } catch {}
  }, [])

  // Persist sort whenever it changes
  useEffect(() => {
    try {
      const ls = window.localStorage
      ls.setItem('sortKey', sortKey)
      ls.setItem('sortDir', sortDir)
      ls.setItem('starFilters', JSON.stringify(starFilters || []))
    } catch {}
  }, [sortKey, sortDir, starFilters])

  const startResizeLeft = (e: React.MouseEvent) => {
    e.preventDefault()
    const app = appRef.current
    if (!app) return
    const rect = app.getBoundingClientRect()
    const onMove = (ev: MouseEvent) => {
      const x = ev.clientX - rect.left
      const min = 160
      const max = Math.max(min, rect.width - rightW - 200)
      const nw = Math.min(Math.max(x, min), max)
      setLeftW(nw)
    }
    const onUp = () => {
      window.removeEventListener('mousemove', onMove)
      window.removeEventListener('mouseup', onUp)
      try { window.localStorage.setItem('leftW', String(leftWRef.current)) } catch {}
    }
    window.addEventListener('mousemove', onMove)
    window.addEventListener('mouseup', onUp)
  }

  const startResizeRight = (e: React.MouseEvent) => {
    e.preventDefault()
    const app = appRef.current
    if (!app) return
    const rect = app.getBoundingClientRect()
    const onMove = (ev: MouseEvent) => {
      const x = ev.clientX - rect.left
      const fromRight = rect.width - x
      const min = 240
      const max = Math.max(min, rect.width - leftW - 200)
      const nw = Math.min(Math.max(fromRight, min), max)
      setRightW(nw)
    }
    const onUp = () => {
      window.removeEventListener('mousemove', onMove)
      window.removeEventListener('mouseup', onUp)
      try { window.localStorage.setItem('rightW', String(rightWRef.current)) } catch {}
    }
    window.addEventListener('mousemove', onMove)
    window.addEventListener('mouseup', onUp)
  }

  // Prefetch neighbors for the open viewer (previous and next)
  useEffect(() => {
    if (!viewer) return
    const paths = items.map(i=> i.path)
    const idx = paths.indexOf(viewer)
    if (idx === -1) return
    const prevs = [paths[idx - 1], paths[idx - 2]].filter(Boolean) as string[]
    const nexts = [paths[idx + 1], paths[idx + 2]].filter(Boolean) as string[]
    for (const p of prevs) { try { api.prefetchFile(p) } catch {} }
    for (const p of nexts) { try { api.prefetchFile(p) } catch {} }
    // Prefetch their thumbnails too (very cheap)
    for (const p of [...prevs, ...nexts]) { try { api.prefetchThumb(p) } catch {} }
  }, [viewer, items])

  // On folder load, prefetch fullsize for the first 5 items (respect size cap)
  useEffect(() => {
    if (!data || !Array.isArray(data.items)) return
    const firstFive = data.items.slice(0, 5)
    for (const it of firstFive) { try { api.prefetchFile(it.path) } catch {} }
  }, [data?.path])

  // Initialize current folder from URL hash and keep in sync
  useEffect(() => {
    try {
      const raw = window.location.hash.startsWith('#') ? window.location.hash.slice(1) : window.location.hash
      const initial = sanitizePath(raw)
      setCurrent(initial)
    } catch {}
    const onHash = () => {
      try {
        const raw = window.location.hash.startsWith('#') ? window.location.hash.slice(1) : window.location.hash
        const norm = sanitizePath(raw)
        // Any folder hash navigation should exit fullscreen
        setViewer(null)
        setCurrent(prev => (prev === norm ? prev : norm))
      } catch {}
    }
    window.addEventListener('hashchange', onHash)
    return () => window.removeEventListener('hashchange', onHash)
  }, [])

  const openFolder = (p: string) => {
    // Close fullscreen viewer when navigating to another folder
    setViewer(null)
    const safe = sanitizePath(p)
    setCurrent(safe)
    try {
      const nextHash = `#${encodeURI(safe)}`
      if (window.location.hash !== nextHash) window.location.hash = nextHash
    } catch {}
  }

  // Manage viewer history entry so browser Back closes fullscreen first
  const openViewer = (p: string) => {
    setViewer(p)
    if (!viewerHistoryPushedRef.current) {
      try { window.history.pushState({ viewer: true }, '', window.location.href); viewerHistoryPushedRef.current = true } catch {}
    }
  }

  const closeViewer = () => {
    setViewer(null)
    if (viewerHistoryPushedRef.current) {
      viewerHistoryPushedRef.current = false
      try { window.history.back() } catch {}
    }
  }

  useEffect(() => {
    const onPop = () => {
      if (viewer) {
        viewerHistoryPushedRef.current = false
        setViewer(null)
      }
    }
    window.addEventListener('popstate', onPop)
    return () => window.removeEventListener('popstate', onPop)
  }, [viewer])

  const [isDraggingOver, setDraggingOver] = useState(false)
  const [ctx, setCtx] = useState<{ x:number; y:number; kind:'tree'|'grid'; payload:any } | null>(null)

  useEffect(() => {
    const el = appRef.current
    if (!el) return
    const onDragOver = (e: DragEvent) => {
      if (!e.dataTransfer) return
      if (Array.from(e.dataTransfer.types).includes('Files')) {
        e.preventDefault()
        setDraggingOver(true)
      }
    }
    const onDragLeave = (e: DragEvent) => {
      setDraggingOver(false)
    }
    const onDrop = async (e: DragEvent) => {
      if (!e.dataTransfer) return
      e.preventDefault()
      setDraggingOver(false)
      const files = Array.from(e.dataTransfer.files || [])
      if (!files.length) return
      // Only allow in a leaf folder (has items or no dirs)
      const isLeaf = (data?.dirs?.length ?? 0) === 0
      if (!isLeaf) return
      for (const f of files) {
        try {
          await api.uploadFile(current, f)
          await refetch()
        } catch {}
      }
    }
    el.addEventListener('dragover', onDragOver)
    el.addEventListener('dragleave', onDragLeave)
    el.addEventListener('drop', onDrop)
    return () => {
      el.removeEventListener('dragover', onDragOver)
      el.removeEventListener('dragleave', onDragLeave)
      el.removeEventListener('drop', onDrop)
    }
  }, [current, data?.dirs, refetch])

  useEffect(() => {
    const onGlobalClick = () => setCtx(null)
    const onEsc = (e: KeyboardEvent) => { if (e.key === 'Escape') setCtx(null) }
    window.addEventListener('click', onGlobalClick)
    window.addEventListener('keydown', onEsc)
    return () => { window.removeEventListener('click', onGlobalClick); window.removeEventListener('keydown', onEsc) }
  }, [])

  return (
    <div className="app" ref={appRef} style={{ ['--left' as any]: `${leftW}px`, ['--right' as any]: `${rightW}px` }}>
      <Toolbar
        onSearch={setQuery}
        viewerActive={!!viewer}
        onBack={closeViewer}
        zoomPercent={viewer ? currentZoom : undefined}
        onZoomPercentChange={(p)=> setRequestedZoom(p)}
        sortKey={sortKey}
        sortDir={sortDir}
        onSortKey={setSortKey}
        onSortDir={setSortDir}
        starFilters={starFilters}
        onToggleStar={(v)=>{
          setStarFilters(prev => {
            const next = new Set(prev || [])
            if (next.has(v)) next.delete(v); else next.add(v)
            return Array.from(next)
          })
        }}
        onClearStars={()=> setStarFilters([])}
        starCounts={(() => {
          const merged = (data?.items ?? []).map(it => ({ ...it, star: (localStarOverrides[it.path]!==undefined ? localStarOverrides[it.path] : it.star) }))
          const counts: Record<string, number> = { '0':0, '1':0, '2':0, '3':0, '4':0, '5':0 }
          for (const it of merged) {
            const v = (it.star ?? 0)
            counts[String(v)] = (counts[String(v)] || 0) + 1
          }
          return counts
        })()}
      />
      <FolderTree current={current} roots={[{label:'Root', path:'/'}]} data={data} onOpen={openFolder} onResize={startResizeLeft}
        onContextMenu={(e, p)=>{ e.preventDefault(); setCtx({ x:e.clientX, y:e.clientY, kind:'tree', payload:{ path:p } }) }}
      />
      <div className="main">
        <Grid items={items} selected={selectedPaths} onSelectionChange={setSelectedPaths} onOpenViewer={(p)=> { openViewer(p); setSelectedPaths([p]) }}
          onContextMenuItem={(e, path)=>{ e.preventDefault(); const paths = selectedPaths.length ? selectedPaths : [path]; setCtx({ x:e.clientX, y:e.clientY, kind:'grid', payload:{ paths } }) }}
        />
      </div>
      <Inspector path={selectedPaths[0] ?? null} selectedPaths={selectedPaths} items={items} onResize={startResizeRight} onStarChanged={(paths, val)=>{
        setLocalStarOverrides(prev => {
          const next = { ...prev }
          for (const p of paths) next[p] = val
          return next
        })
      }} />
      {viewer && (
        <Viewer
          path={viewer}
          onClose={closeViewer}
          onZoomChange={(p)=> setCurrentZoom(Math.round(p))}
          requestedZoomPercent={requestedZoom}
          onZoomRequestConsumed={()=> setRequestedZoom(null)}
          onNavigate={(delta)=>{
            const paths = items.map(i=> i.path)
            const idx = paths.indexOf(viewer)
            if (idx === -1) return
            const next = Math.min(paths.length - 1, Math.max(0, idx + delta))
            const np = paths[next]
            if (np && np !== viewer) { setViewer(np) }
          }}
        />
      )}
      {isDraggingOver && (
        <div className="drop-overlay">Drop images to upload</div>
      )}
      {ctx && (
        <div className="ctx" style={{ left: ctx.x, top: ctx.y }} onClick={e=> e.stopPropagation()}>
          {ctx.kind === 'tree' && (
            <>
              <div className="ctx-item disabled" onClick={(e)=>{ e.stopPropagation() }}>Export (disabled)</div>
            </>
          )}
          {ctx.kind === 'grid' && (
            <>
              {/* Move to trash */}
              <div className={`ctx-item${current.endsWith('/_trash_') ? ' disabled' : ''}`} onClick={async ()=>{
                if (current.endsWith('/_trash_')) return
                const trash = `/_trash_`
                for (const p of ctx.payload.paths as string[]) { try { await api.moveFile(p, trash) } catch {} }
                // invalidate and optimistic update
                try { await refetch() } catch {}
                setCtx(null)
              }}>Move to trash</div>
              <div className="ctx-sep" />
              {/* Permanent delete (only inside _trash_) */}
              {current.endsWith('/_trash_') && (
                <div className="ctx-item ctx-danger" onClick={async ()=>{
                  try { await api.deleteFiles(ctx.payload.paths as string[]) } catch {}
                  try { await refetch() } catch {}
                  setCtx(null)
                }}>Permanent delete</div>
              )}
              {current.endsWith('/_trash_') && (
                <div className="ctx-item" onClick={async ()=>{
                  // Recover: read sidecar for each and move back to original_position if present
                  const toRecover = ctx.payload.paths as string[]
                  for (const p of toRecover) {
                    try {
                      const sc = await api.getSidecar(p)
                      const dest = (sc as any).original_position ? ((sc as any).original_position as string).split('/').slice(0,-1).join('/') : '/'
                      const targetDir = dest || '/'
                      await api.moveFile(p, targetDir)
                    } catch {}
                  }
                  try { await refetch() } catch {}
                  setCtx(null)
                }}>Recover</div>
              )}
            </>
          )}
        </div>
      )}
    </div>
  )
}
