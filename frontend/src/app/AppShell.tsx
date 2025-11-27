import React, { useCallback, useEffect, useMemo, useRef, useState } from 'react'
import Toolbar from '../shared/ui/Toolbar'
import FolderTree from '../features/folders/FolderTree'
import VirtualGrid from '../features/browse/components/VirtualGrid'
import Viewer from '../features/viewer/Viewer'
import Inspector from '../features/inspector/Inspector'
import { useFolder } from '../shared/api/folders'
import { useSearch } from '../shared/api/search'
import { api } from '../shared/api/client'
import { readHash, writeHash, sanitizePath, getParentPath, isTrashPath } from './routing/hash'
import { applyFilters, applySort } from '../features/browse/model/apply'
import { useSidebars } from './layout/useSidebars'
import ContextMenu, { MenuItem } from './menu/ContextMenu'
import { mapItemsToRatings, toRatingsCsv, toRatingsJson } from '../features/ratings/services/exportRatings'
import { useDebounced } from '../shared/hooks/useDebounced'
import type { Item, SortKey, SortDir, ContextMenuState, StarRating, ViewMode } from '../lib/types'
import { isInputElement } from '../lib/keyboard'
import { safeJsonParse } from '../lib/util'

/** Local storage keys for persisted settings */
const STORAGE_KEYS = {
  sortKey: 'sortKey',
  sortDir: 'sortDir',
  starFilters: 'starFilters',
  viewMode: 'viewMode',
  gridItemSize: 'gridItemSize',
} as const

export default function AppShell() {
  // Navigation state
  const [current, setCurrent] = useState<string>('/')
  const [query, setQuery] = useState('')
  const [selectedPaths, setSelectedPaths] = useState<string[]>([])
  const [viewer, setViewer] = useState<string | null>(null)
  const [restoreGridToSelectionToken, setRestoreGridToSelectionToken] = useState(0)
  
  // Viewer zoom state
  const [requestedZoom, setRequestedZoom] = useState<number | null>(null)
  const [currentZoom, setCurrentZoom] = useState(100)
  
  // Sort and filter state
  const [sortKey, setSortKey] = useState<SortKey>('added')
  const [sortDir, setSortDir] = useState<SortDir>('desc')
  const [starFilters, setStarFilters] = useState<number[]>([])
  const [viewMode, setViewMode] = useState<ViewMode>('adaptive')
  const [gridItemSize, setGridItemSize] = useState<number>(220)
  
  // Local optimistic updates for star ratings
  const [localStarOverrides, setLocalStarOverrides] = useState<Record<string, StarRating>>({})
  
  // Refs
  const appRef = useRef<HTMLDivElement>(null)
  const gridShellRef = useRef<HTMLDivElement>(null)
  const viewerHistoryPushedRef = useRef(false)
  const lastFocusedPathRef = useRef<string | null>(null)

  const { leftW, rightW, onResizeLeft, onResizeRight } = useSidebars(appRef)

  // Drag and drop state
  const [isDraggingOver, setDraggingOver] = useState(false)
  
  // Context menu state
  const [ctx, setCtx] = useState<ContextMenuState | null>(null)

  // Initialize current folder from URL hash and keep in sync
  useEffect(() => {
    const initPath = sanitizePath(readHash())
    setCurrent(initPath)
    
    const onHash = () => {
      const norm = sanitizePath(readHash())
      setViewer(null)
      // Only trigger "restore selection into view" when the folder/tab actually changes
      setCurrent((prev) => {
        if (prev === norm) return prev
        setRestoreGridToSelectionToken((t) => t + 1)
        return norm
      })
    }
    
    window.addEventListener('hashchange', onHash)
    return () => window.removeEventListener('hashchange', onHash)
  }, [])

  const { data, refetch, isLoading, isError } = useFolder(current)
  const searching = query.trim().length > 0
  const debouncedQ = useDebounced(query, 250)
  const normalizedQ = useMemo(() => debouncedQ.trim().replace(/\s+/g, ' '), [debouncedQ])
  const search = useSearch(searching ? normalizedQ : '', current)

  // Merge items with local star overrides and apply sort/filters
  const items = useMemo((): Item[] => {
    const base = searching ? (search.data?.items ?? []) : (data?.items ?? [])
    const merged = base.map((it) => ({
      ...it,
      star: localStarOverrides[it.path] !== undefined ? localStarOverrides[it.path] : it.star,
    }))
    const filtered = applyFilters(merged, starFilters.length > 0 ? starFilters : null)
    return applySort(filtered, sortKey, sortDir)
  }, [searching, search.data, data, sortKey, sortDir, starFilters, localStarOverrides])

  // Compute star counts for the filter UI
  const starCounts = useMemo(() => {
    const baseItems = data?.items ?? []
    const counts: Record<string, number> = { '0': 0, '1': 0, '2': 0, '3': 0, '4': 0, '5': 0 }
    for (const it of baseItems) {
      const star = localStarOverrides[it.path] ?? it.star ?? 0
      counts[String(star)] = (counts[String(star)] || 0) + 1
    }
    return counts
  }, [data?.items, localStarOverrides])

  // Clear selection when entering search mode
  useEffect(() => {
    if (searching) {
      setSelectedPaths([])
      setViewer(null)
    }
  }, [searching])

  // Load persisted settings on mount
  useEffect(() => {
    try {
      const storedSortKey = localStorage.getItem(STORAGE_KEYS.sortKey)
      const storedSortDir = localStorage.getItem(STORAGE_KEYS.sortDir)
      const storedStarFilters = localStorage.getItem(STORAGE_KEYS.starFilters)
      const storedViewMode = localStorage.getItem(STORAGE_KEYS.viewMode) as ViewMode | null
      const storedGridSize = localStorage.getItem(STORAGE_KEYS.gridItemSize)
      
      if (storedSortKey === 'name' || storedSortKey === 'added') {
        setSortKey(storedSortKey)
      }
      if (storedSortDir === 'asc' || storedSortDir === 'desc') {
        setSortDir(storedSortDir)
      }
      if (storedStarFilters) {
        const parsed = safeJsonParse<number[]>(storedStarFilters)
        if (Array.isArray(parsed)) {
          setStarFilters(parsed.filter((n) => [0, 1, 2, 3, 4, 5].includes(n)))
        }
      }
      if (storedViewMode === 'grid' || storedViewMode === 'adaptive') {
        setViewMode(storedViewMode)
      }
      if (storedGridSize) {
        const size = Number(storedGridSize)
        if (!isNaN(size) && size >= 80 && size <= 500) {
          setGridItemSize(size)
        }
      }
    } catch {
      // Ignore localStorage errors (private browsing, etc.)
    }
  }, [])

  // Persist settings when they change
  useEffect(() => {
    try {
      localStorage.setItem(STORAGE_KEYS.sortKey, sortKey)
      localStorage.setItem(STORAGE_KEYS.sortDir, sortDir)
      localStorage.setItem(STORAGE_KEYS.starFilters, JSON.stringify(starFilters))
      localStorage.setItem(STORAGE_KEYS.viewMode, viewMode)
      localStorage.setItem(STORAGE_KEYS.gridItemSize, String(gridItemSize))
    } catch {
      // Ignore localStorage errors
    }
  }, [sortKey, sortDir, starFilters, viewMode, gridItemSize])

  // Ctrl + scroll adjusts thumbnail size (override browser zoom)
  useEffect(() => {
    const shell = gridShellRef.current
    if (!shell) return
    const clamp = (v: number) => Math.min(500, Math.max(80, v))
    const onWheel = (e: WheelEvent) => {
      if (!e.ctrlKey) return
      e.preventDefault()
      setGridItemSize((prev) => clamp(prev + (e.deltaY < 0 ? 20 : -20)))
    }
    shell.addEventListener('wheel', onWheel, { passive: false })
    return () => shell.removeEventListener('wheel', onWheel)
  }, [])

  // Prefetch neighbors for the open viewer (previous and next)
  useEffect(() => {
    if (!viewer) return
    
    const paths = items.map((i) => i.path)
    const idx = paths.indexOf(viewer)
    if (idx === -1) return
    
    // Prefetch 2 items in each direction
    const neighbors = [
      paths[idx - 2],
      paths[idx - 1],
      paths[idx + 1],
      paths[idx + 2],
    ].filter((p): p is string => Boolean(p))
    
    for (const p of neighbors) {
      api.prefetchFile(p)
      api.prefetchThumb(p)
    }
  }, [viewer, items])

  // On folder load, prefetch fullsize for the first few items
  useEffect(() => {
    if (!data?.items?.length) return
    
    const toPreload = data.items.slice(0, 5)
    for (const it of toPreload) {
      api.prefetchFile(it.path)
    }
  }, [data?.path, data?.items])

  // Navigation callbacks
  const openFolder = useCallback((p: string) => {
    setViewer(null)
    const safe = sanitizePath(p)
    setCurrent(safe)
    writeHash(safe)
  }, [])

  const openViewer = useCallback((p: string) => {
    setViewer(p)
    if (!viewerHistoryPushedRef.current) {
      window.history.pushState({ viewer: true }, '', window.location.href)
      viewerHistoryPushedRef.current = true
    }
  }, [])

  const closeViewer = useCallback(() => {
    setViewer(null)
    if (viewerHistoryPushedRef.current) {
      viewerHistoryPushedRef.current = false
      window.history.back()
    }
    // Restore focus to the last focused grid cell
    const p = lastFocusedPathRef.current
    if (p) {
      const el = document.getElementById(`cell-${encodeURIComponent(p)}`)
      el?.focus()
    }
  }, [])

  // Handle browser back/forward specifically for closing the viewer.
  // NOTE: We intentionally do NOT touch grid scroll position here – closing
  // the fullscreen viewer should leave the grid exactly where it was.
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

  // Drag and drop file upload handling
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
      // Only trigger if leaving the app container entirely
      const related = e.relatedTarget as Node | null
      if (related && el.contains(related)) return
      setDraggingOver(false)
    }

    const onDrop = async (e: DragEvent) => {
      e.preventDefault()
      setDraggingOver(false)
      
      const files = Array.from(e.dataTransfer?.files ?? [])
      if (!files.length) return
      
      // Only allow uploads to leaf folders (no subdirectories)
      const isLeaf = (data?.dirs?.length ?? 0) === 0
      if (!isLeaf) {
        alert('Uploads are only allowed into folders without subdirectories.')
        return
      }
      
      // Upload files sequentially
      for (const f of files) {
        try {
          await api.uploadFile(current, f)
        } catch (err) {
          console.error(`Failed to upload ${f.name}:`, err)
        }
      }
      
      // Refresh folder contents
      refetch()
    }

    el.addEventListener('dragover', onDragOver)
    el.addEventListener('dragleave', onDragLeave)
    el.addEventListener('drop', onDrop)
    
    return () => {
      el.removeEventListener('dragover', onDragOver)
      el.removeEventListener('dragleave', onDragLeave)
      el.removeEventListener('drop', onDrop)
    }
  }, [current, data?.dirs?.length, refetch])

  // Close context menu on click or escape
  useEffect(() => {
    const onGlobalClick = () => setCtx(null)
    const onEsc = (e: KeyboardEvent) => {
      if (e.key === 'Escape') setCtx(null)
    }
    
    window.addEventListener('click', onGlobalClick)
    window.addEventListener('keydown', onEsc)
    
    return () => {
      window.removeEventListener('click', onGlobalClick)
      window.removeEventListener('keydown', onEsc)
    }
  }, [])

  // Global keyboard shortcuts (when not in viewer)
  useEffect(() => {
    const onKey = (e: KeyboardEvent) => {
      // Ignore if in input field
      if (isInputElement(e.target)) return
      // Ignore if viewer is open (viewer has its own handlers)
      if (viewer) return
      
      if (e.key === 'Backspace' || e.key === 'Delete') {
        e.preventDefault()
        openFolder(getParentPath(current))
      } else if ((e.ctrlKey || e.metaKey) && e.key.toLowerCase() === 'a') {
        e.preventDefault()
        setSelectedPaths(items.map((i) => i.path))
      } else if (e.key === 'Escape') {
        if (selectedPaths.length) {
          e.preventDefault()
          setSelectedPaths([])
        }
      } else if (e.key === '/') {
        e.preventDefault()
        const searchInput = document.querySelector('.toolbar-right .input') as HTMLInputElement | null
        searchInput?.focus()
      }
    }
    
    window.addEventListener('keydown', onKey)
    return () => window.removeEventListener('keydown', onKey)
  }, [current, items, selectedPaths, viewer, openFolder])

  return (
    <div className="grid h-full grid-cols-[var(--left)_1fr_var(--right)] grid-rows-[48px_1fr]" ref={appRef} style={{ ['--left' as any]: `${leftW}px`, ['--right' as any]: `${rightW}px` }}>
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
        onToggleStar={(v) => {
          setStarFilters((prev) => {
            const next = new Set(prev)
            if (next.has(v)) {
              next.delete(v)
            } else {
              next.add(v)
            }
            return Array.from(next)
          })
        }}
        onClearStars={() => setStarFilters([])}
        starCounts={starCounts}
        viewMode={viewMode}
        onViewMode={setViewMode}
        gridItemSize={gridItemSize}
        onGridItemSize={setGridItemSize}
      />
      <FolderTree current={current} roots={[{label:'Root', path:'/'}]} data={data} onOpen={openFolder} onResize={onResizeLeft}
        onContextMenu={(e, p)=>{ e.preventDefault(); setCtx({ x:e.clientX, y:e.clientY, kind:'tree', payload:{ path:p } }) }}
      />
      <div className="col-start-2 row-start-2 relative overflow-hidden" ref={gridShellRef}>
        <div aria-live="polite" className="sr-only">
          {selectedPaths.length ? `${selectedPaths.length} selected` : ''}
        </div>
        {/* Breadcrumb / path bar intentionally hidden for now */}
        {false && (
          <div className="sticky top-0 z-10 px-3 py-2.5 bg-panel backdrop-blur-sm shadow-[0_1px_0_rgba(255,255,255,.04),0_6px_8px_-6px_rgba(0,0,0,.5)]">
            {(() => {
              const parts = current.split('/').filter(Boolean)
              const segs: { label:string; path:string }[] = []
              let acc = ''
              for (const p of parts) { acc = acc ? `${acc}/${p}` : `/${p}`; segs.push({ label: p, path: acc }) }
              return (
                <>
                  <a href={`#${encodeURI('/')}`} onClick={(e)=>{ e.preventDefault(); openFolder('/') }} className="text-text opacity-85 no-underline hover:opacity-100 hover:underline">Root</a>
                  {segs.map((s, i) => (
                    <span key={s.path}>
                      <span className="opacity-50 mx-1.5">/</span>
                      {i < segs.length-1 ? (
                        <a href={`#${encodeURI(s.path)}`} onClick={(e)=>{ e.preventDefault(); openFolder(s.path) }} className="text-text opacity-85 no-underline hover:opacity-100 hover:underline">{s.label}</a>
                      ) : (
                        <span aria-current="page">{s.label}</span>
                      )}
                    </span>
                  ))}
                  <span className="opacity-0 hover:opacity-100 ml-2 cursor-pointer text-xs text-muted" role="button" aria-label="Copy path" title="Copy path" onClick={()=>{ try { navigator.clipboard.writeText(current) } catch {} }}>⧉</span>
                </>
              )
            })()}
          </div>
        )}
        <VirtualGrid items={items} selected={selectedPaths} restoreToSelectionToken={restoreGridToSelectionToken} onSelectionChange={setSelectedPaths} onOpenViewer={(p)=> { try { lastFocusedPathRef.current = p } catch {} ; openViewer(p); setSelectedPaths([p]) }}
          highlight={searching ? normalizedQ : ''}
          suppressSelectionHighlight={!!viewer}
          viewMode={viewMode}
          targetCellSize={gridItemSize}
          onContextMenuItem={(e, path)=>{ e.preventDefault(); const paths = selectedPaths.length ? selectedPaths : [path]; setCtx({ x:e.clientX, y:e.clientY, kind:'grid', payload:{ paths } }) }}
        />
        {/* Bottom selection bar removed intentionally */}
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
        <div className="fixed inset-0 top-[48px] left-[var(--left)] right-[var(--right)] bg-accent/10 border-2 border-dashed border-accent text-text flex items-center justify-center text-lg z-overlay pointer-events-none">Drop images to upload</div>
      )}
      {ctx && <ContextMenuItems ctx={ctx} current={current} items={items} refetch={refetch} setCtx={setCtx} />}
    </div>
  )
}

/**
 * Helper function to trigger a file download from a blob.
 */
function downloadBlob(blob: Blob, filename: string): void {
  const url = URL.createObjectURL(blob)
  const a = document.createElement('a')
  a.href = url
  a.download = filename
  document.body.appendChild(a)
  a.click()
  a.remove()
  URL.revokeObjectURL(url)
}

/**
 * Context menu items component - extracted for cleaner render logic.
 */
function ContextMenuItems({
  ctx,
  current,
  items,
  refetch,
  setCtx,
}: {
  ctx: ContextMenuState
  current: string
  items: Item[]
  refetch: () => void
  setCtx: (ctx: ContextMenuState | null) => void
}) {
  const inTrash = isTrashPath(current)
  
  const menuItems: MenuItem[] = ctx.kind === 'tree'
    ? [{ label: 'Export (disabled)', disabled: true, onClick: () => {} }]
    : (() => {
        const sel = ctx.payload.paths ?? []
        const arr: MenuItem[] = []
        
        // Move to trash
        arr.push({
          label: 'Move to trash',
          disabled: inTrash,
          onClick: async () => {
            if (inTrash) return
            for (const p of sel) {
              try {
                await api.moveFile(p, '/_trash_')
              } catch (err) {
                console.error(`Failed to trash ${p}:`, err)
              }
            }
            refetch()
            setCtx(null)
          },
        })
        
        // Trash-specific actions
        if (inTrash) {
          arr.push({
            label: 'Permanent delete',
            danger: true,
            onClick: async () => {
              if (!confirm(`Delete ${sel.length} file(s) permanently? This cannot be undone.`)) {
                return
              }
              try {
                await api.deleteFiles(sel)
              } catch (err) {
                console.error('Failed to delete files:', err)
              }
              refetch()
              setCtx(null)
            },
          })
          
          arr.push({
            label: 'Recover',
            onClick: async () => {
              for (const p of sel) {
                try {
                  const sc = await api.getSidecar(p)
                  const originalPath = sc.original_position
                  const targetDir = originalPath
                    ? originalPath.split('/').slice(0, -1).join('/') || '/'
                    : '/'
                  await api.moveFile(p, targetDir)
                } catch (err) {
                  console.error(`Failed to recover ${p}:`, err)
                }
              }
              refetch()
              setCtx(null)
            },
          })
        }
        
        // Export ratings
        if (sel.length) {
          arr.push({
            label: 'Export ratings (CSV)',
            onClick: () => {
              const selSet = new Set(sel)
              const subset = items.filter((i) => selSet.has(i.path))
              const ratings = mapItemsToRatings(subset)
              const csv = toRatingsCsv(ratings)
              downloadBlob(new Blob([csv], { type: 'text/csv;charset=utf-8' }), 'ratings.csv')
              setCtx(null)
            },
          })
          
          arr.push({
            label: 'Export ratings (JSON)',
            onClick: () => {
              const selSet = new Set(sel)
              const subset = items.filter((i) => selSet.has(i.path))
              const ratings = mapItemsToRatings(subset)
              const json = toRatingsJson(ratings)
              downloadBlob(new Blob([json], { type: 'application/json;charset=utf-8' }), 'ratings.json')
              setCtx(null)
            },
          })
        }
        
        return arr
      })()
  
  return <ContextMenu x={ctx.x} y={ctx.y} items={menuItems} />
}
