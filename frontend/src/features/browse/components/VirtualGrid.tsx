import React, { useRef, useState, useEffect, useLayoutEffect, useMemo, useCallback } from 'react'
import { createPortal } from 'react-dom'
import type { Item, ViewMode } from '../../../lib/types'
import ThumbCard from './ThumbCard'
import { api } from '../../../shared/api/client'
import { getBrowseHotpathSnapshot, markFirstGridItemVisible } from '../../../lib/browseHotpath'
import { useVirtualGrid } from '../hooks/useVirtualGrid'
import { getNextIndexForKeyNav } from '../hooks/useKeyboardNav'
import type { AdaptiveRow } from '../model/adaptive'
import { getAdjacentThumbPrefetchPaths } from '../model/virtualGridPrefetch'
import {
  collectVisiblePaths,
  getRestoreScrollTopForPath,
  getTopAnchorPathForVisibleRows,
  resolveVirtualGridRestoreDecision,
} from '../model/virtualGridSession'
import { LongPressController } from '../../../lib/touch'
import { shouldOpenOnTap, toggleSelectedPath } from '../../../lib/mobileSelection'

const GAP = 12
const CAPTION_H = 44
const DEFAULT_ASPECT = { w: 4, h: 3 }
const PREVIEW_DELAY_MS = 350
const SCROLL_IDLE_MS = 120

function arePathSetsEqual(a: Set<string>, b: Set<string>): boolean {
  if (a === b) return true
  if (a.size !== b.size) return false
  for (const value of a) {
    if (!b.has(value)) return false
  }
  return true
}

function toLongPressEvent(ev: React.PointerEvent<HTMLDivElement>) {
  return {
    pointerId: ev.pointerId,
    pointerType: ev.pointerType,
    clientX: ev.clientX,
    clientY: ev.clientY,
    isPrimary: ev.isPrimary,
  }
}

function renderHighlightedName(name: string, highlight?: string): React.ReactNode {
  const query = (highlight ?? '').trim()
  if (!query) return name

  const matchIndex = name.toLowerCase().indexOf(query.toLowerCase())
  if (matchIndex === -1) return name

  const before = name.slice(0, matchIndex)
  const match = name.slice(matchIndex, matchIndex + query.length)
  const after = name.slice(matchIndex + query.length)

  return (
    <>
      {before}
      <mark className="bg-accent/20 text-inherit rounded px-0.5">{match}</mark>
      {after}
    </>
  )
}

interface VirtualGridProps {
  items: Item[]
  selected: string[]
  restoreToSelectionToken?: number
  restoreToTopAnchorToken?: number
  restoreToTopAnchorPath?: string | null
  multiSelectMode?: boolean
  onSelectionChange: (paths: string[]) => void
  onOpenViewer: (path: string) => void
  onContextMenuItem?: (e: React.MouseEvent, path: string) => void
  onOpenItemActions?: (path: string, anchor: { x: number; y: number }) => void
  highlight?: string
  recentlyUpdated?: Map<string, string>
  onVisiblePathsChange?: (paths: Set<string>) => void
  onTopAnchorPathChange?: (path: string | null) => void
  suppressSelectionHighlight?: boolean
  viewMode?: ViewMode
  targetCellSize?: number
  scrollRef?: React.RefObject<HTMLDivElement>
  hideScrollbar?: boolean
  isLoading?: boolean
}

export default function VirtualGrid({
  items,
  selected,
  restoreToSelectionToken,
  restoreToTopAnchorToken,
  restoreToTopAnchorPath,
  multiSelectMode = false,
  onSelectionChange,
  onOpenViewer,
  onContextMenuItem,
  onOpenItemActions,
  highlight,
  recentlyUpdated,
  onVisiblePathsChange,
  onTopAnchorPathChange,
  suppressSelectionHighlight = false,
  viewMode = 'grid',
  targetCellSize = 220,
  scrollRef,
  hideScrollbar = false,
  isLoading = false,
}: VirtualGridProps) {
  const [previewFor, setPreviewFor] = useState<string | null>(null)
  const [previewUrl, setPreviewUrl] = useState<string | null>(null)
  const [delayPassed, setDelayPassed] = useState<boolean>(false)
  const [active, setActive] = useState<string | null>(null)
  const [focused, setFocused] = useState<string | null>(null)
  const previewUrlRef = useRef<string | null>(null)
  const previewTimerRef = useRef<number | null>(null)
  const internalRef = useRef<HTMLDivElement | null>(null)
  const parentRef = scrollRef ?? internalRef
  const anchorRef = useRef<string | null>(null)
  const appliedSelectionRestoreTokenRef = useRef(0)
  const appliedTopAnchorRestoreTokenRef = useRef(0)
  const lastVisiblePathsRef = useRef<Set<string>>(new Set())
  const lastTopAnchorPathRef = useRef<string | null>(null)
  const longPressControllerRef = useRef<LongPressController | null>(null)
  const longPressPathRef = useRef<string | null>(null)
  const longPressPointRef = useRef<{ x: number; y: number } | null>(null)
  const suppressClickRef = useRef<{ path: string; untilMs: number } | null>(null)
  const lastPointerRef = useRef<{ path: string | null; pointerType: string | null }>({
    path: null,
    pointerType: null,
  })

  const TARGET_CELL = targetCellSize

  const { width, layout, rowVirtualizer, virtualRows } = useVirtualGrid(parentRef, items, {
    gap: GAP,
    targetCell: TARGET_CELL,
    aspect: DEFAULT_ASPECT,
    captionH: CAPTION_H,
    viewMode,
  })

  const pathToIndex = useMemo(() => {
    const map = new Map<string, number>()
    for (let i = 0; i < items.length; i++) map.set(items[i].path, i)
    return map
  }, [items])

  const adaptivePositions = useMemo(() => {
    if (layout.mode !== 'adaptive') return null
    const map = new Map<string, { row: number, center: number, order: number }>()
    layout.rows.forEach((row: AdaptiveRow, rowIdx: number) => {
      let x = 0
      row.items.forEach((it, order) => {
        const center = x + it.displayW / 2
        map.set(it.item.path, { row: rowIdx, center, order })
        x += it.displayW + GAP
      })
    })
    return map
  }, [layout])

  // Keep active item in sync with external selection changes (e.g., viewer navigation)
  useEffect(() => {
    if (!selected.length) return
    const first = selected[0]
    if (active !== first) setActive(first)
  }, [selected, active])

  const adaptiveRowMeta = useMemo(() => {
    if (layout.mode !== 'adaptive') return null
    let offset = 0
    return layout.rows.map(r => {
      const start = offset
      offset += r.height
      return { start, height: r.height }
    })
  }, [layout])

  const scrollAnimRef = useRef<number | null>(null)
  const scrollRowIntoView = (el: HTMLElement, top: number) => {
    try {
      if (scrollAnimRef.current != null) { try { cancelAnimationFrame(scrollAnimRef.current) } catch {} ; scrollAnimRef.current = null }
      const start = el.scrollTop
      const delta = top - start
      if (Math.abs(delta) < 1) { el.scrollTop = top; return }
      const D = 140
      const t0 = performance.now()
      const easeOutCubic = (t: number) => 1 - Math.pow(1 - t, 3)
      const step = (now: number) => {
        const p = Math.min(1, (now - t0) / D)
        const eased = easeOutCubic(p)
        el.scrollTop = start + delta * eased
        if (p < 1) { scrollAnimRef.current = requestAnimationFrame(step) } else { scrollAnimRef.current = null }
      }
      scrollAnimRef.current = requestAnimationFrame(step)
    } catch { el.scrollTop = top }
  }

  const [isScrolling, setIsScrolling] = useState(false)
  useEffect(() => {
    const el = parentRef.current
    if (!el) return
    let timeoutId = 0
    const onScroll = () => {
      longPressControllerRef.current?.cancelFromScroll()
      setIsScrolling(true)
      window.clearTimeout(timeoutId)
      timeoutId = window.setTimeout(() => setIsScrolling(false), SCROLL_IDLE_MS)
    }
    el.addEventListener('scroll', onScroll, { passive: true } as any)
    return () => el.removeEventListener('scroll', onScroll as any)
  }, [])

  useEffect(() => {
    const controller = new LongPressController({
      onLongPress: (event) => {
        const path = longPressPathRef.current
        if (!path || !onOpenItemActions) return
        const point = longPressPointRef.current ?? { x: event.clientX, y: event.clientY }
        onOpenItemActions(path, point)
        suppressClickRef.current = { path, untilMs: Date.now() + 700 }
      },
    })
    longPressControllerRef.current = controller
    return () => {
      controller.destroy()
      if (longPressControllerRef.current === controller) {
        longPressControllerRef.current = null
      }
    }
  }, [onOpenItemActions])

  const cancelPreviewTimer = () => {
    if (previewTimerRef.current != null) {
      window.clearTimeout(previewTimerRef.current)
      previewTimerRef.current = null
    }
  }

  const clearPreview = () => {
    cancelPreviewTimer()
    setDelayPassed(false)
    setPreviewFor(null)
    if (previewUrlRef.current) {
      try { URL.revokeObjectURL(previewUrlRef.current) } catch {}
      previewUrlRef.current = null
    }
    setPreviewUrl(null)
  }

  const schedulePreview = (path: string) => {
    if (isScrolling) return
    cancelPreviewTimer()
    setPreviewFor(path)
    setDelayPassed(false)
    previewTimerRef.current = window.setTimeout(async () => {
      previewTimerRef.current = null
      try {
        const blob = await api.getFile(path)
        const u = URL.createObjectURL(blob)
        if (previewUrlRef.current) {
          try { URL.revokeObjectURL(previewUrlRef.current) } catch {}
        }
        previewUrlRef.current = u
        setPreviewUrl(u)
        setDelayPassed(true)
      } catch {}
    }, PREVIEW_DELAY_MS)
  }

  const effectiveColumns = layout.mode === 'grid' ? layout.columns : Math.max(1, Math.floor(width / (TARGET_CELL + GAP)))

  const findClosestInRow = (rowIdx: number, targetCenter: number): string | null => {
    if (layout.mode !== 'adaptive') return null
    const row = layout.rows[rowIdx]
    if (!row) return null
    let x = 0
    let best: { path: string; dist: number } | null = null
    for (const it of row.items) {
      const center = x + it.displayW / 2
      const dist = Math.abs(center - targetCenter)
      if (!best || dist < best.dist) {
        best = { path: it.item.path, dist }
      }
      x += it.displayW + GAP
    }
    return best ? best.path : null
  }

  const getNextPath = (current: string | null, e: KeyboardEvent): string | 'open' | null => {
    if (!items.length) return null
    // Default to first item when nothing is focused
    const currentPath = current ?? items[0].path

    if (layout.mode !== 'adaptive') {
      const nextIdx = getNextIndexForKeyNav(items, effectiveColumns, currentPath, e)
      if (nextIdx === 'open' || nextIdx == null) return nextIdx
      return items[nextIdx]?.path ?? null
    }

    const info = adaptivePositions?.get(currentPath)
    if (!info) return currentPath

    const idx = pathToIndex.get(currentPath) ?? 0
    const key = e.key

    if (key === 'Enter') return 'open'

    // Horizontal moves stay in reading order using the flat list
    if (key === 'ArrowRight' || key === 'd') return items[Math.min(items.length - 1, idx + 1)]?.path ?? currentPath
    if (key === 'ArrowLeft' || key === 'a') return items[Math.max(0, idx - 1)]?.path ?? currentPath

    const delta = key === 'ArrowDown' || key === 's' ? 1 : key === 'ArrowUp' || key === 'w' ? -1 : 0
    if (delta === 0) return null

    const targetRow = info.row + delta
    if (targetRow < 0 || targetRow >= (layout.rows?.length ?? 0)) return currentPath

    const targetCenter = info.center
    const candidate = findClosestInRow(targetRow, targetCenter)
    return candidate ?? currentPath
  }

  const focusCell = (path: string) => {
    try { (document.getElementById(`cell-${encodeURIComponent(path)}`) as HTMLElement | null)?.focus() } catch {}
  }

  const prefetchThumbSafely = useCallback((path: string) => {
    try {
      api.prefetchThumb(path)
    } catch {}
  }, [])

  const openActionsForPath = useCallback((path: string, anchor: { x: number; y: number }) => {
    onOpenItemActions?.(path, anchor)
  }, [onOpenItemActions])

  const clearLongPressTracking = () => {
    longPressPathRef.current = null
    longPressPointRef.current = null
  }

  const handleItemPointerDown = (path: string, ev: React.PointerEvent<HTMLDivElement>) => {
    if ((ev.target as HTMLElement).closest('[data-grid-action]')) return
    lastPointerRef.current = { path, pointerType: ev.pointerType }
    if (multiSelectMode) return
    longPressPathRef.current = path
    longPressPointRef.current = { x: ev.clientX, y: ev.clientY }
    longPressControllerRef.current?.pointerDown(toLongPressEvent(ev))
  }

  const handleItemPointerMove = (ev: React.PointerEvent<HTMLDivElement>) => {
    if (multiSelectMode) return
    longPressPointRef.current = { x: ev.clientX, y: ev.clientY }
    longPressControllerRef.current?.pointerMove(toLongPressEvent(ev))
  }

  const handleItemPointerUp = (ev: React.PointerEvent<HTMLDivElement>) => {
    if (multiSelectMode) return
    longPressControllerRef.current?.pointerUp(ev.pointerId)
    clearLongPressTracking()
  }

  const handleItemPointerCancel = (ev: React.PointerEvent<HTMLDivElement>) => {
    if (multiSelectMode) return
    longPressControllerRef.current?.pointerCancel(ev.pointerId)
    clearLongPressTracking()
  }

  const handleItemClick = (path: string, ev: React.MouseEvent) => {
    const suppressed = suppressClickRef.current
    if (suppressed && suppressed.path === path && suppressed.untilMs > Date.now()) {
      suppressClickRef.current = null
      focusCell(path)
      return
    }
    if (suppressed && suppressed.untilMs <= Date.now()) {
      suppressClickRef.current = null
    }
    setActive(path)
    setFocused(path)
    const isShift = !!ev.shiftKey
    const isToggle = !!(ev.ctrlKey || ev.metaKey)
    if (multiSelectMode) {
      onSelectionChange(toggleSelectedPath(selected, path))
      anchorRef.current = path
    } else if (shouldOpenOnTap({
      pointerType: lastPointerRef.current.path === path ? lastPointerRef.current.pointerType : null,
      multiSelectMode,
      isShift,
      isToggle,
      selectedPaths: selected,
      path,
    })) {
      onSelectionChange([path])
      anchorRef.current = path
      onOpenViewer(path)
    } else if (isShift) {
      const anchorPath = anchorRef.current ?? active ?? (selected[0] ?? path)
      const aIdx = pathToIndex.get(anchorPath) ?? items.findIndex(i => i.path === anchorPath)
      const bIdx = pathToIndex.get(path) ?? items.findIndex(i => i.path === path)
      if (aIdx !== -1 && bIdx !== -1) {
        const start = Math.min(aIdx, bIdx)
        const end = Math.max(aIdx, bIdx)
        const range = items.slice(start, end + 1).map(x => x.path)
        if (isToggle) {
          const next = new Set(selected)
          for (const p of range) next.add(p)
          onSelectionChange(Array.from(next))
        } else {
          onSelectionChange(range)
        }
      } else {
        onSelectionChange([path])
      }
    } else if (isToggle) {
      onSelectionChange(toggleSelectedPath(selected, path))
      anchorRef.current = path
    } else {
      onSelectionChange([path])
      anchorRef.current = path
    }
    if (!isScrolling) prefetchThumbSafely(path)
    focusCell(path)
  }

  const handleDragStart = (path: string, e: React.DragEvent<HTMLDivElement>) => {
    try {
      const paths = selectedSet.has(path) && selected.length > 0 ? selected : [path]
      e.dataTransfer?.setData('application/x-lenslet-paths', JSON.stringify(paths))
      if (e.dataTransfer) e.dataTransfer.effectAllowed = 'copyMove'
      try { document.body.classList.add('drag-active') } catch {}
      const host = e.currentTarget as HTMLElement
      const img = host.querySelector('.cell-content img') as HTMLImageElement | null
      const ghost = document.createElement('div')
      ghost.className = 'drag-ghost'
      const ghostImg = document.createElement('img')
      ghostImg.draggable = false
      ghostImg.alt = 'drag'
      if (img && img.src) ghostImg.src = img.src
      ghost.appendChild(ghostImg)
      document.body.appendChild(ghost)
      const w = ghost.getBoundingClientRect().width || 150
      e.dataTransfer?.setDragImage(ghost, Math.round(w / 2), 0)
      const cleanup = () => {
        try { ghost.remove() } catch {}
        try { document.body.classList.remove('drag-active') } catch {}
        window.removeEventListener('dragend', cleanup)
        window.removeEventListener('pointerup', cleanup)
        document.removeEventListener('visibilitychange', cleanup)
      }
      window.addEventListener('dragend', cleanup)
      window.addEventListener('pointerup', cleanup)
      document.addEventListener('visibilitychange', cleanup)
    } catch {}
  }

  useEffect(() => {
    const el = parentRef.current
    if (!el) return
    const onKey = (e: KeyboardEvent) => {
      const nextPath = getNextPath(focused, e)
      if (nextPath == null) return
      e.preventDefault()
      if (nextPath === 'open') { if (focused) onOpenViewer(focused); return }
      const nextItem = items.find(i => i.path === nextPath)
      if (!nextItem) return
      setFocused(nextItem.path)
      setActive(nextItem.path)
      onSelectionChange([nextItem.path])
      anchorRef.current = nextItem.path
      
      // Find row for next item
      const nextRowIdx = layout.mode === 'grid'
        ? Math.floor((pathToIndex.get(nextItem.path) ?? 0) / Math.max(1, layout.columns))
        : (adaptivePositions?.get(nextItem.path)?.row ?? 0)

      const scrollTop = el.scrollTop
      const viewBottom = scrollTop + el.clientHeight
      const rowTop = layout.mode === 'adaptive' 
        ? (adaptiveRowMeta?.[nextRowIdx]?.start ?? 0)
        : nextRowIdx * layout.rowH
      const rowBottom = layout.mode === 'adaptive'
        ? rowTop + (adaptiveRowMeta?.[nextRowIdx]?.height ?? 0)
        : rowTop + layout.rowH

      if (rowTop < scrollTop || rowBottom > viewBottom) {
        scrollRowIntoView(el, rowTop)
      }
      focusCell(nextItem.path)
    }
    el.addEventListener('keydown', onKey)
    return () => { el.removeEventListener('keydown', onKey) }
  }, [items, focused, effectiveColumns, onOpenViewer, layout, adaptivePositions, adaptiveRowMeta, pathToIndex])

  useLayoutEffect(() => {
    const el = parentRef.current
    if (!el) return
    const restoreDecision = resolveVirtualGridRestoreDecision({
      selectionToken: restoreToSelectionToken,
      appliedSelectionToken: appliedSelectionRestoreTokenRef.current,
      selectedPath: selected[0] ?? null,
      topAnchorToken: restoreToTopAnchorToken,
      appliedTopAnchorToken: appliedTopAnchorRestoreTokenRef.current,
      topAnchorPath: restoreToTopAnchorPath ?? null,
      hasPath: (path) => pathToIndex.has(path),
    })
    if (!restoreDecision) return

    const targetTop = getRestoreScrollTopForPath({
      path: restoreDecision.path,
      pathToIndex,
      layout,
      adaptiveRowMeta,
    })
    if (targetTop == null) return

    try { el.scrollTop = targetTop } catch {}
    if (restoreDecision.source === 'selection') {
      appliedSelectionRestoreTokenRef.current = restoreDecision.token
      return
    }
    appliedTopAnchorRestoreTokenRef.current = restoreDecision.token
  }, [
    restoreToSelectionToken,
    restoreToTopAnchorToken,
    restoreToTopAnchorPath,
    selected,
    pathToIndex,
    layout,
    adaptiveRowMeta,
  ])

  const selectedSet = useMemo(() => new Set(selected), [selected])
  const hasPreview = !!(previewFor && previewUrl && delayPassed)
  const adjacentThumbPrefetchPaths = useMemo(
    () => getAdjacentThumbPrefetchPaths(virtualRows, layout, items),
    [items, layout, virtualRows],
  )

  useEffect(() => {
    if (isScrolling || adjacentThumbPrefetchPaths.length === 0) return
    for (const path of adjacentThumbPrefetchPaths) {
      prefetchThumbSafely(path)
    }
  }, [isScrolling, adjacentThumbPrefetchPaths, prefetchThumbSafely])

  useEffect(() => {
    parentRef.current?.focus()
  }, [])

  useEffect(() => {
    if (!suppressSelectionHighlight) return
    try {
      parentRef.current?.blur()
    } catch {}
    setFocused(null)
  }, [suppressSelectionHighlight])

  const visiblePaths = useMemo(
    () => collectVisiblePaths(items, layout, virtualRows),
    [items, layout, virtualRows],
  )
  const topAnchorPath = useMemo(
    () => getTopAnchorPathForVisibleRows(items, layout, virtualRows, parentRef.current?.scrollTop ?? 0),
    [items, layout, virtualRows, parentRef],
  )

  useEffect(() => {
    if (!onVisiblePathsChange) return
    if (arePathSetsEqual(lastVisiblePathsRef.current, visiblePaths)) return
    lastVisiblePathsRef.current = visiblePaths
    onVisiblePathsChange(visiblePaths)
  }, [onVisiblePathsChange, visiblePaths])

  useEffect(() => {
    if (!onTopAnchorPathChange) return
    if (lastTopAnchorPathRef.current === topAnchorPath) return
    lastTopAnchorPathRef.current = topAnchorPath
    onTopAnchorPathChange(topAnchorPath)
  }, [onTopAnchorPathChange, topAnchorPath])

  const activeDescendantId = focused ? `cell-${encodeURIComponent(focused)}` : undefined
  useEffect(() => {
    if (!items.length) return
    if (getBrowseHotpathSnapshot().firstGridItemLatencyMs != null) return
    const container = parentRef.current
    if (!container) return
    const firstCell = container.querySelector<HTMLElement>('[role="gridcell"][id^="cell-"]')
    if (!firstCell) return
    const viewport = container.getBoundingClientRect()
    const rect = firstCell.getBoundingClientRect()
    const visible = rect.bottom >= viewport.top && rect.top <= viewport.bottom
    if (!visible) return
    const encodedPath = firstCell.id.startsWith('cell-') ? firstCell.id.slice(5) : ''
    let path = items[0].path
    if (encodedPath) {
      try {
        path = decodeURIComponent(encodedPath)
      } catch {
        path = items[0].path
      }
    }
    markFirstGridItemVisible(path)
  }, [items, parentRef])

  return (
    <div 
      role="grid" 
      aria-label="Gallery" 
      className={`relative h-full overflow-auto p-3 outline-none ${hideScrollbar ? 'scrollbar-hidden pr-4' : 'scrollbar-thin'} ${hasPreview ? 'cursor-zoom-in' : ''}`}
      ref={parentRef} 
      tabIndex={0} 
      aria-activedescendant={activeDescendantId} 
      aria-busy={isLoading || undefined}
      onMouseDown={() => parentRef.current?.focus()} 
      style={{ ['--gap' as any]: `${GAP}px` }}
    >
      <div key={`${viewMode}-${effectiveColumns}`} className="relative w-full" style={{ height: rowVirtualizer.getTotalSize() }}>
        {virtualRows.map(row => {
          let rowItems: { item: Item, displayW: number, displayH: number }[] = []
          let rowStyle: React.CSSProperties = {}
          let rowClass = ""

          if (layout.mode === 'adaptive') {
             const rowData = layout.rows[row.index]
             if (!rowData) return null
             rowItems = rowData.items
             rowStyle = {
                 height: rowData.height,
                 transform: `translate3d(0, ${row.start}px, 0)`,
                 display: 'flex',
                 gap: GAP,
                 paddingBottom: GAP,
             }
             rowClass = "absolute top-0 left-0 right-0 w-full will-change-transform"
          } else {
             const start = row.index * layout.columns
             const slice = items.slice(start, start + layout.columns)
             rowItems = slice.map(it => ({ item: it, displayW: layout.cellW, displayH: layout.mediaH }))
             rowStyle = {
                 transform: `translate3d(0, ${row.start}px, 0)`,
                 gridTemplateColumns: `repeat(${layout.columns}, minmax(0, 1fr))`,
                 gap: GAP,
                 paddingBottom: GAP,
             }
             rowClass = "absolute top-0 left-0 right-0 w-full grid will-change-transform"
          }
          
          const isTopmostVisibleRow = row.index === virtualRows[0]?.index
          
          return (
            <div 
              key={row.key} 
              className={rowClass}
              role="row" 
              style={rowStyle}
            >
              {rowItems.map(({ item: it, displayW, displayH }) => {
                const isVisuallySelected = !suppressSelectionHighlight && ((active===it.path) || selectedSet.has(it.path))
                const recentUpdateKey = recentlyUpdated?.get(it.path) ?? null
                const isRecentlyUpdated = recentUpdateKey != null
                const wrapperStyle = layout.mode === 'adaptive' ? { width: displayW } : {}
                const imageContainerStyle = layout.mode === 'adaptive' ? { height: displayH } : {}
                
                const itemContainerClass = layout.mode === 'adaptive' 
                    ? "relative rounded-lg overflow-hidden bg-[var(--thumb-bg,#121212)] group shrink-0" 
                    : "relative aspect-[4/3] rounded-lg overflow-hidden bg-[var(--thumb-bg,#121212)] group"

                return (
                <div 
                  id={`cell-${encodeURIComponent(it.path)}`} 
                  key={it.path} 
                  className={`relative min-w-0 ${isVisuallySelected ? 'outline outline-2 outline-accent outline-offset-2 rounded-[10px]' : ''}`}
                  role="gridcell" 
                  aria-selected={isVisuallySelected} 
                  tabIndex={focused===it.path?0:-1}
                  onFocus={()=> setFocused(it.path)} 
                  draggable 
                  style={wrapperStyle}
                  onDragStart={(e) => handleDragStart(it.path, e)}
                  onPointerDown={(e) => handleItemPointerDown(it.path, e)}
                  onPointerMove={handleItemPointerMove}
                  onPointerUp={handleItemPointerUp}
                  onPointerCancel={handleItemPointerCancel}
                  onContextMenu={(e) => {
                    e.preventDefault()
                    e.stopPropagation()
                    onContextMenuItem?.(e, it.path)
                  }}>
                  <div 
                    className={itemContainerClass}
                    style={imageContainerStyle}
                    onDoubleClick={()=> { if (!multiSelectMode) onOpenViewer(it.path) }} 
                    onMouseLeave={clearPreview}>
                    <button
                      type="button"
                      className="grid-item-action-btn touch-manipulation"
                      data-grid-action="1"
                      aria-label={`Open actions for ${it.name}`}
                      aria-haspopup="menu"
                      onPointerDown={(e) => e.stopPropagation()}
                      onClick={(e) => {
                        e.stopPropagation()
                        const rect = e.currentTarget.getBoundingClientRect()
                        openActionsForPath(it.path, { x: rect.right - 4, y: rect.bottom - 4 })
                      }}
                    >
                      <svg width="13" height="13" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round" aria-hidden="true">
                        <circle cx="12" cy="5" r="1.5" />
                        <circle cx="12" cy="12" r="1.5" />
                        <circle cx="12" cy="19" r="1.5" />
                      </svg>
                    </button>
                    <div className="cell-content absolute inset-0">
                      <ThumbCard
                        path={it.path}
                        name={it.name}
                        selected={isVisuallySelected}
                        highlighted={isRecentlyUpdated}
                        highlightKey={recentUpdateKey}
                        displayW={displayW}
                        displayH={displayH}
                        ioRoot={parentRef.current}
                        isScrolling={isScrolling}
                        priority={isTopmostVisibleRow}
                        onClick={(ev: React.MouseEvent) => handleItemClick(it.path, ev)}
                      />
                    </div>
                    <div 
                      className="absolute right-0 bottom-0 w-7 h-7 cursor-zoom-in"
                      onMouseEnter={() => schedulePreview(it.path)}
                      onMouseLeave={clearPreview}>
                      <div
                        className="grid-item-preview-corner absolute right-0 bottom-0 h-[18px] w-[18px] flex items-center justify-center text-text select-none"
                        style={{
                          clipPath: 'path("M0 9C0 4.02944 4.02944 0 9 0H18V18H0V9Z")',
                          background: 'linear-gradient(135deg, rgba(18,18,18,0.9) 0%, rgba(34,34,34,0.9) 60%, rgba(22,22,22,0.9) 100%)',
                          borderTop: '1px solid rgba(255,255,255,0.08)',
                          borderLeft: '1px solid rgba(255,255,255,0.08)',
                          boxShadow: '0 1px 2px rgba(0,0,0,0.45)',
                          backdropFilter: 'blur(1px)'
                        }}
                      >
                        <svg
                          width="11"
                          height="11"
                          viewBox="0 0 24 24"
                          fill="none"
                          stroke="currentColor"
                          strokeWidth="1.7"
                          strokeLinecap="round"
                          strokeLinejoin="round"
                          className="text-[#d9dce2]"
                          aria-hidden="true"
                          style={{ transform: 'translate(0px,0px)' }}
                        >
                          <circle cx="11" cy="11" r="5.4" />
                          <path d="M15.5 15.5 L19 19" />
                        </svg>
                      </div>
                    </div>
                  </div>
                  <div className="flex flex-col items-center text-center gap-0 mt-1 px-0.5 text-white/90">
                    <div className="text-sm leading-[18px] thumb-filename line-clamp-2 break-words hyphens-auto text-center" title={it.name}>
                      {renderHighlightedName(it.name, highlight)}
                    </div>
                    <div className="text-[11px] leading-[15px] opacity-70">{it.w} × {it.h}</div>
                  </div>
                </div>
              )})}
            </div>
          )
        })}
        {previewFor && previewUrl && delayPassed && createPortal(
          <div className="toolbar-offset fixed inset-0 z-[999] flex items-center justify-center pointer-events-none bg-black/20 opacity-100">
            <img src={previewUrl} alt="preview" className="max-w-[80vw] max-h-[80vh] object-contain opacity-[0.98]" />
          </div>,
          document.body
        )}
      </div>
      {isLoading && items.length === 0 && (
        <div className="pointer-events-none absolute inset-3 z-20 flex items-center justify-center">
          <div className="w-full max-w-[580px] rounded-lg border border-border bg-panel/95 px-4 py-3 shadow-lg">
            <div className="flex items-center justify-between gap-3 text-xs text-text">
              <span className="font-semibold">Loading gallery…</span>
            </div>
            <div className="mt-2 text-[11px] text-muted">Preparing gallery…</div>
          </div>
        </div>
      )}
    </div>
  )
}
