import React, { useEffect, useMemo, useRef, useState } from 'react'
import Toolbar from '../shared/ui/Toolbar'
import FolderTree from '../features/folders/FolderTree'
import VirtualGrid from '../features/browse/components/VirtualGrid'
import Viewer from '../features/viewer/Viewer'
import Inspector from '../features/inspector/Inspector'
import { useFolder } from '../shared/api/folders'
import { useSearch } from '../shared/api/search'
import { api } from '../shared/api/client'
import { readHash, writeHash, sanitizePath } from './routing/hash'
import { applyFilters, applySort } from '../features/browse/model/apply'
import { useSidebars } from './layout/useSidebars'
import ContextMenu, { MenuItem } from './menu/ContextMenu'
import { mapItemsToRatings, toRatingsCsv, toRatingsJson } from '../features/ratings/services/exportRatings'
import { useDebounced } from '../shared/hooks/useDebounced'

export default function AppShell(){
  const [current, setCurrent] = useState<string>('/')
  const [query, setQuery] = useState('')
  const [selectedPaths, setSelectedPaths] = useState<string[]>([])
  const [viewer, setViewer] = useState<string | null>(null)
  const [restoreGridToSelectionToken, setRestoreGridToSelectionToken] = useState<number>(0)
  const [requestedZoom, setRequestedZoom] = useState<number | null>(null)
  const [currentZoom, setCurrentZoom] = useState<number>(100)
  const [sortKey, setSortKey] = useState<'name'|'added'>('added')
  const [sortDir, setSortDir] = useState<'asc'|'desc'>('desc')
  const [starFilters, setStarFilters] = useState<number[] | null>(null)
  const [localStarOverrides, setLocalStarOverrides] = useState<Record<string, number | null>>({})
  const appRef = useRef<HTMLDivElement | null>(null)
  const viewerHistoryPushedRef = useRef(false)

  const { leftW, rightW, onResizeLeft, onResizeRight } = useSidebars(appRef)

  // Initialize current folder from URL hash and keep in sync
  useEffect(() => {
    try { setCurrent(sanitizePath(readHash())) } catch {}
    const onHash = () => {
      try {
        const norm = sanitizePath(readHash())
        setViewer(null)
        setCurrent(prev => (prev === norm ? prev : norm))
      } catch {}
    }
    window.addEventListener('hashchange', onHash)
    return () => window.removeEventListener('hashchange', onHash)
  }, [])

  const { data, refetch } = useFolder(current)
  const searching = query.trim().length > 0
  const debouncedQ = useDebounced(query, 250)
  const normalizedQ = useMemo(()=> debouncedQ.trim().replace(/\s+/g, ' '), [debouncedQ])
  const search = useSearch(searching ? normalizedQ : '', current)

  const items = useMemo(()=> {
    const base = searching ? (search.data?.items ?? []) : (data?.items ?? [])
    const merged = base.map(it => ({ ...it, star: (localStarOverrides[it.path]!==undefined ? localStarOverrides[it.path] : it.star) }))
    const filtered = applyFilters(merged, starFilters)
    const sorted = applySort(filtered, sortKey, sortDir)
    return sorted
  }, [searching, search.data, data, sortKey, sortDir, starFilters, localStarOverrides])

  useEffect(() => {
    if (searching) { setSelectedPaths([]); setViewer(null) }
  }, [searching])

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

  useEffect(() => {
    try {
      const ls = window.localStorage
      ls.setItem('sortKey', sortKey)
      ls.setItem('sortDir', sortDir)
      ls.setItem('starFilters', JSON.stringify(starFilters || []))
    } catch {}
  }, [sortKey, sortDir, starFilters])

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
    for (const p of [...prevs, ...nexts]) { try { api.prefetchThumb(p) } catch {} }
  }, [viewer, items])

  // On folder load, prefetch fullsize for the first 5 items (respect size cap)
  useEffect(() => {
    if (!data || !Array.isArray(data.items)) return
    const firstFive = data.items.slice(0, 5)
    for (const it of firstFive) { try { api.prefetchFile(it.path) } catch {} }
  }, [data?.path])

  const openFolder = (p: string) => {
    setViewer(null)
    const safe = sanitizePath(p)
    setCurrent(safe)
    try { writeHash(safe) } catch {}
  }

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
        setRestoreGridToSelectionToken(t => t + 1)
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
      if (Array.from(e.dataTransfer.types).includes('Files')) { e.preventDefault(); setDraggingOver(true) }
    }
    const onDragLeave = () => { setDraggingOver(false) }
    const onDrop = async (e: DragEvent) => {
      if (!e.dataTransfer) return
      e.preventDefault()
      setDraggingOver(false)
      const files = Array.from(e.dataTransfer.files || [])
      if (!files.length) return
      const isLeaf = (data?.dirs?.length ?? 0) === 0
      if (!isLeaf) { try { alert('Uploads are only allowed into empty folders.') } catch {} ; return }
      for (const f of files) { try { await api.uploadFile(current, f); await refetch() } catch {} }
    }
    el.addEventListener('dragover', onDragOver)
    el.addEventListener('dragleave', onDragLeave)
    el.addEventListener('drop', onDrop)
    return () => { el.removeEventListener('dragover', onDragOver); el.removeEventListener('dragleave', onDragLeave); el.removeEventListener('drop', onDrop) }
  }, [current, data?.dirs, refetch])

  useEffect(() => {
    const onGlobalClick = () => setCtx(null)
    const onEsc = (e: KeyboardEvent) => { if (e.key === 'Escape') setCtx(null) }
    window.addEventListener('click', onGlobalClick)
    window.addEventListener('keydown', onEsc)
    return () => { window.removeEventListener('click', onGlobalClick); window.removeEventListener('keydown', onEsc) }
  }, [])

  useEffect(() => {
    const onKey = (e: KeyboardEvent) => {
      const target = e.target as HTMLElement | null
      if (target && target.closest('input, textarea, [contenteditable="true"]')) return
      if (viewer) return
      if (e.key === 'Backspace' || e.key === 'Delete') {
        e.preventDefault()
        const parts = current.split('/').filter(Boolean)
        const up = parts.slice(0, -1).join('/')
        openFolder('/' + up)
      } else if ((e.ctrlKey || e.metaKey) && (e.key.toLowerCase() === 'a')) {
        e.preventDefault(); setSelectedPaths(items.map(i => i.path))
      } else if (e.key === 'Escape') {
        if (selectedPaths.length) { e.preventDefault(); setSelectedPaths([]) }
      } else if (e.key === '/') {
        e.preventDefault(); try { (document.querySelector('.toolbar-right .input') as HTMLInputElement | null)?.focus() } catch {}
      }
    }
    window.addEventListener('keydown', onKey)
    return () => window.removeEventListener('keydown', onKey)
  }, [current, items, selectedPaths, viewer])

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
        onToggleStar={(v)=>{ setStarFilters(prev => { const next = new Set(prev || []); if (next.has(v)) next.delete(v); else next.add(v); return Array.from(next) }) }}
        onClearStars={()=> setStarFilters([])}
        starCounts={(() => {
          const merged = (data?.items ?? []).map(it => ({ ...it, star: (localStarOverrides[it.path]!==undefined ? localStarOverrides[it.path] : it.star) }))
          const counts: Record<string, number> = { '0':0, '1':0, '2':0, '3':0, '4':0, '5':0 }
          for (const it of merged) { const v = (it.star ?? 0); counts[String(v)] = (counts[String(v)] || 0) + 1 }
          return counts
        })()}
      />
      <FolderTree current={current} roots={[{label:'Root', path:'/'}]} data={data} onOpen={openFolder} onResize={onResizeLeft}
        onContextMenu={(e, p)=>{ e.preventDefault(); setCtx({ x:e.clientX, y:e.clientY, kind:'tree', payload:{ path:p } }) }}
      />
      <div className="main">
        <div aria-live="polite" style={{ position:'absolute', left:-9999, top:'auto', width:1, height:1, overflow:'hidden' }}>
          {selectedPaths.length ? `${selectedPaths.length} selected` : ''}
        </div>
        <div className="breadcrumb">
          {(() => {
            const parts = current.split('/').filter(Boolean)
            const segs: { label:string; path:string }[] = []
            let acc = ''
            for (const p of parts) { acc = acc ? `${acc}/${p}` : `/${p}`; segs.push({ label: p, path: acc }) }
            return (
              <>
                <a href={`#${encodeURI('/')}`} onClick={(e)=>{ e.preventDefault(); openFolder('/') }}>Root</a>
                {segs.map((s, i) => (
                  <span key={s.path}>
                    <span style={{ opacity:0.5, margin:'0 6px' }}>/</span>
                    {i < segs.length-1 ? (
                      <a href={`#${encodeURI(s.path)}`} onClick={(e)=>{ e.preventDefault(); openFolder(s.path) }}>{s.label}</a>
                    ) : (
                      <span aria-current="page">{s.label}</span>
                    )}
                  </span>
                ))}
                <span className="copy" role="button" aria-label="Copy path" title="Copy path" onClick={()=>{ try { navigator.clipboard.writeText(current) } catch {} }}>⧉</span>
              </>
            )
          })()}
        </div>
        <VirtualGrid items={items} selected={selectedPaths} restoreToSelectionToken={restoreGridToSelectionToken} onSelectionChange={setSelectedPaths} onOpenViewer={(p)=> { openViewer(p); setSelectedPaths([p]) }}
          highlight={searching ? normalizedQ : ''}
          onContextMenuItem={(e, path)=>{ e.preventDefault(); const paths = selectedPaths.length ? selectedPaths : [path]; setCtx({ x:e.clientX, y:e.clientY, kind:'grid', payload:{ paths } }) }}
        />
        {!!selectedPaths.length && (
          <div className="selection-bar">
            <div>{selectedPaths.length} selected</div>
            <button className="toolbar-back" onClick={()=> setSelectedPaths([])}>Clear</button>
          </div>
        )}
      </div>
      <Inspector path={selectedPaths[0] ?? null} selectedPaths={selectedPaths} items={items} onResize={onResizeRight} onStarChanged={(paths, val)=>{
        setLocalStarOverrides(prev => { const next = { ...prev }; for (const p of paths) next[p] = val; return next })
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
            if (np && np !== viewer) { setViewer(np); setSelectedPaths([np]) }
          }}
        />
      )}
      {isDraggingOver && (
        <div className="drop-overlay">Drop images to upload</div>
      )}
      {ctx && (() => {
        const items: MenuItem[] = ctx.kind === 'tree'
          ? [ { label: 'Export (disabled)', disabled: true, onClick: () => {} } ]
          : (() => {
              const inTrash = current.endsWith('/_trash_')
              const sel = (ctx.payload.paths as string[]) || []
              const arr: MenuItem[] = []
              arr.push({ label: 'Move to trash', disabled: inTrash, onClick: async () => {
                if (inTrash) return
                const trash = '/_trash_'
                for (const p of sel) { try { await api.moveFile(p, trash) } catch {} }
                try { await refetch() } catch {}
                setCtx(null)
              }})
              if (inTrash) {
                arr.push({ label: 'Permanent delete', danger: true, onClick: async () => {
                  if (!confirm(`Delete ${sel.length} file(s) permanently? This cannot be undone.`)) return
                  try { await api.deleteFiles(sel) } catch {}
                  try { await refetch() } catch {}
                  setCtx(null)
                }})
                arr.push({ label: 'Recover', onClick: async () => {
                  for (const p of sel) {
                    try {
                      const sc = await api.getSidecar(p)
                      const dest = (sc as any).original_position ? ((sc as any).original_position as string).split('/').slice(0,-1).join('/') : '/'
                      const targetDir = dest || '/'
                      await api.moveFile(p, targetDir)
                    } catch {}
                  }
                  try { await refetch() } catch {}
                  setCtx(null)
                }})
              }
              if (sel.length) {
                arr.push({ label: 'Export ratings (CSV)', onClick: () => {
                  try {
                    const set = new Set(sel)
                    const subset = items.filter(i => set.has(i.path))
                    const data = mapItemsToRatings(subset)
                    const csv = toRatingsCsv(data)
                    const blob = new Blob([csv], { type: 'text/csv;charset=utf-8' })
                    const url = URL.createObjectURL(blob)
                    const a = document.createElement('a')
                    a.href = url
                    a.download = 'ratings.csv'
                    document.body.appendChild(a)
                    a.click()
                    a.remove()
                    URL.revokeObjectURL(url)
                  } catch {}
                  setCtx(null)
                }})
                arr.push({ label: 'Export ratings (JSON)', onClick: () => {
                  try {
                    const set = new Set(sel)
                    const subset = items.filter(i => set.has(i.path))
                    const data = mapItemsToRatings(subset)
                    const json = toRatingsJson(data)
                    const blob = new Blob([json], { type: 'application/json;charset=utf-8' })
                    const url = URL.createObjectURL(blob)
                    const a = document.createElement('a')
                    a.href = url
                    a.download = 'ratings.json'
                    document.body.appendChild(a)
                    a.click()
                    a.remove()
                    URL.revokeObjectURL(url)
                  } catch {}
                  setCtx(null)
                }})
              }
              return arr
            })()
        return (<ContextMenu x={ctx.x} y={ctx.y} items={items} />)
      })()}
    </div>
  )
}


