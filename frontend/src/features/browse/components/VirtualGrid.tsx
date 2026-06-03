import React, { useRef, useState, useEffect, useLayoutEffect, useMemo, useCallback } from 'react'
import { createPortal } from 'react-dom'
import type { BrowseItemPayload, ViewMode } from '../../../lib/types'
import VirtualGridRows from './VirtualGridRows'
import { api } from '../../../api/client'
import { getBrowseHotpathSnapshot, markFirstGridItemVisible } from '../../../lib/browseHotpath'
import { cssVars } from '../../../lib/cssVars'
import { getVisibleViewportBounds } from '../../../lib/menuPosition'
import { useVirtualGrid } from '../hooks/useVirtualGrid'
import { getNextIndexForKeyNav } from '../hooks/useKeyboardNav'
import type { AdaptiveRow } from '../model/adaptive'
import {
  HoverPreviewRequestController,
  getHoverPreviewPosition,
  getHoverPreviewSurfaceSize,
  type HoverPreviewSurfaceSize,
} from '../model/hoverPreview'
import { getAdjacentThumbPrefetchPaths } from '../model/virtualGridPrefetch'
import {
  collectVisiblePaths,
  getRestoreScrollTopForPath,
  getTopAnchorPathForVisibleRows,
  resolveVirtualGridRestoreDecision,
} from '../model/virtualGridSession'
import {
  cancelPendingScrollAnimationFrame,
  clearScrollIdleTimeout,
} from '../model/virtualGridScrollLifecycle'
import { LongPressController } from '../../../lib/touch'
import { shouldOpenOnTap, toggleSelectedPath } from '../../../lib/mobileSelection'

const GAP = 16
const CAPTION_H = 56
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

interface VirtualGridProps {
  items: BrowseItemPayload[]
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
  isLoading?: boolean
  hasMore?: boolean
  isLoadingMore?: boolean
  onLoadMore?: () => void
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
  isLoading = false,
  hasMore = false,
  isLoadingMore = false,
  onLoadMore,
}: VirtualGridProps) {
  const [previewFor, setPreviewFor] = useState<string | null>(null)
  const [previewUrl, setPreviewUrl] = useState<string | null>(null)
  const [previewPosition, setPreviewPosition] = useState<{ x: number; y: number } | null>(null)
  const [previewSize, setPreviewSize] = useState<HoverPreviewSurfaceSize | null>(null)
  const [delayPassed, setDelayPassed] = useState<boolean>(false)
  const [active, setActive] = useState<string | null>(null)
  const [focused, setFocused] = useState<string | null>(null)
  const previewTimerRef = useRef<number | null>(null)
  const previewControllerRef = useRef<HoverPreviewRequestController | null>(null)
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

  if (previewControllerRef.current === null) {
    previewControllerRef.current = new HoverPreviewRequestController(
      (path) => api.getHoverPreview(path),
      {
        createObjectURL: (blob) => URL.createObjectURL(blob),
        revokeObjectURL: (url) => URL.revokeObjectURL(url),
      },
      {
        onReady: ({ path, url }) => {
          setPreviewFor(path)
          setPreviewUrl(url)
          setDelayPassed(true)
        },
      },
    )
  }

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
      cancelPendingScrollAnimationFrame(
        scrollAnimRef,
        (frameId) => window.cancelAnimationFrame(frameId),
      )
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

  useEffect(() => {
    return () => {
      cancelPendingScrollAnimationFrame(
        scrollAnimRef,
        (frameId) => window.cancelAnimationFrame(frameId),
      )
    }
  }, [])

  const [isScrolling, setIsScrolling] = useState(false)
  useEffect(() => {
    const el = parentRef.current
    if (!el) return
    let timeoutId: number | null = null
    const onScroll = () => {
      longPressControllerRef.current?.cancelFromScroll()
      clearPreview()
      setIsScrolling(true)
      timeoutId = clearScrollIdleTimeout(timeoutId, (id) => window.clearTimeout(id))
      timeoutId = window.setTimeout(() => setIsScrolling(false), SCROLL_IDLE_MS)
    }
    el.addEventListener('scroll', onScroll, { passive: true })
    return () => {
      el.removeEventListener('scroll', onScroll)
      timeoutId = clearScrollIdleTimeout(timeoutId, (id) => window.clearTimeout(id))
    }
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

  function cancelPreviewTimer(): void {
    if (previewTimerRef.current != null) {
      window.clearTimeout(previewTimerRef.current)
      previewTimerRef.current = null
    }
  }

  function clearPreview(): void {
    cancelPreviewTimer()
    previewControllerRef.current?.clear()
    setDelayPassed(false)
    setPreviewFor(null)
    setPreviewUrl(null)
    setPreviewPosition(null)
    setPreviewSize(null)
  }

  const schedulePreview = (path: string) => {
    if (isScrolling) return
    cancelPreviewTimer()
    previewControllerRef.current?.clear()
    const viewport = getVisibleViewportBounds()
    const surfaceSize = getHoverPreviewSurfaceSize(viewport)
    const position = getHoverPreviewPosition({
      surfaceSize,
      viewport,
    })
    setPreviewFor(path)
    setPreviewUrl(null)
    setPreviewPosition(position)
    setPreviewSize(surfaceSize)
    setDelayPassed(false)
    previewTimerRef.current = window.setTimeout(() => {
      previewTimerRef.current = null
      previewControllerRef.current?.begin(path)
    }, PREVIEW_DELAY_MS)
  }

  useEffect(() => () => {
    if (previewTimerRef.current != null) {
      window.clearTimeout(previewTimerRef.current)
      previewTimerRef.current = null
    }
    previewControllerRef.current?.clear()
  }, [])

  const effectiveColumns = layout.mode === 'grid' ? layout.columns : Math.max(1, Math.floor(width / (TARGET_CELL + GAP)))

  useEffect(() => {
    if (!onLoadMore || !hasMore || isLoadingMore || !items.length || !virtualRows.length) return
    const lastVirtualRow = virtualRows[virtualRows.length - 1]
    const lastVisibleIndex = layout.mode === 'grid'
      ? Math.min(items.length - 1, ((lastVirtualRow.index + 1) * Math.max(1, layout.columns)) - 1)
      : Math.max(
        -1,
        ...(layout.rows[lastVirtualRow.index]?.items ?? []).map((entry) => entry.originalIndex),
      )
    const threshold = Math.max(30, effectiveColumns * 8)
    if (lastVisibleIndex >= items.length - threshold) onLoadMore()
  }, [effectiveColumns, hasMore, isLoadingMore, items.length, layout, onLoadMore, virtualRows])

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
    const normalized = key.toLowerCase()

    if (key === 'Enter') return 'open'

    // Horizontal moves stay in reading order using the flat list
    if (key === 'ArrowRight' || normalized === 'd') {
      return items[Math.min(items.length - 1, idx + 1)]?.path ?? currentPath
    }
    if (key === 'ArrowLeft' || normalized === 'a') {
      return items[Math.max(0, idx - 1)]?.path ?? currentPath
    }

    const delta = key === 'ArrowDown' || normalized === 's'
      ? 1
      : key === 'ArrowUp' || normalized === 'w'
        ? -1
        : 0
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
  const selectionOrderByPath = useMemo(() => {
    const order = new Map<string, number>()
    for (let i = 0; i < selected.length; i += 1) {
      order.set(selected[i], i + 1)
    }
    return order
  }, [selected])
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
      className={`relative h-full overflow-auto p-3 outline-none scrollbar-thin ${hasPreview ? 'cursor-zoom-in' : ''}`}
      ref={parentRef} 
      tabIndex={0} 
      aria-activedescendant={activeDescendantId} 
      aria-busy={(isLoading || isLoadingMore) || undefined}
      onMouseDown={() => parentRef.current?.focus()} 
      style={cssVars({ '--gap': `${GAP}px` })}
    >
      <div key={`${viewMode}-${effectiveColumns}`} className="relative w-full" style={{ height: rowVirtualizer.getTotalSize() }}>
        <VirtualGridRows
          virtualRows={virtualRows}
          layout={layout}
          items={items}
          gap={GAP}
          scrollRootRef={parentRef}
          suppressSelectionHighlight={suppressSelectionHighlight}
          active={active}
          focused={focused}
          selectedSet={selectedSet}
          selectionOrderByPath={selectionOrderByPath}
          recentlyUpdated={recentlyUpdated}
          highlight={highlight}
          isScrolling={isScrolling}
          multiSelectMode={multiSelectMode}
          onCellFocus={setFocused}
          onPointerDown={handleItemPointerDown}
          onPointerMove={handleItemPointerMove}
          onPointerUp={handleItemPointerUp}
          onPointerCancel={handleItemPointerCancel}
          onContextMenuItem={onContextMenuItem}
          onOpenItemActions={openActionsForPath}
          onOpenViewer={onOpenViewer}
          onClearPreview={clearPreview}
          onSchedulePreview={schedulePreview}
          onItemClick={handleItemClick}
        />
        {previewFor && previewUrl && delayPassed && previewPosition && previewSize && createPortal(
          <div
            className="grid-hover-preview fixed z-[999] pointer-events-none overflow-hidden rounded-lg border border-border bg-panel/95 shadow-lg"
            data-preview-path={previewFor}
            aria-hidden="true"
            style={{
              left: previewPosition.x,
              top: previewPosition.y,
              width: previewSize.width,
              height: previewSize.height,
            }}
          >
            <img
              src={previewUrl}
              alt="preview"
              className="block h-full w-full object-contain opacity-[0.98]"
            />
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
