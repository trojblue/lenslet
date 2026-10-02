import React, { useCallback, useRef, useState } from 'react'
import type { BrowseFolderPayload } from '../../lib/types'
import { useLatestRef } from '../../shared/hooks/useLatestRef'
import FolderTreeRows from './FolderTreeRows'
import { expandedAncestorPaths } from './model/treeRows'

interface Root {
  label: string
  path: string
}

interface FolderTreeProps {
  active?: boolean
  current: string
  roots: Root[]
  data?: BrowseFolderPayload
  onOpen: (path: string) => void
  onPullRefresh?: () => Promise<void> | void
  onResize?: (e: React.PointerEvent<HTMLDivElement>) => void
  onContextMenu?: (e: React.MouseEvent, path: string) => void
  onOpenActions?: (path: string, anchor: { x: number; y: number }) => void
  countVersion?: number
  className?: string
  showResizeHandle?: boolean
}

const PULL_REFRESH_THRESHOLD = 64
const MAX_PULL_DISTANCE = 120

export default function FolderTree({
  active = true,
  current,
  roots,
  data,
  onOpen,
  onPullRefresh,
  onResize,
  onContextMenu,
  onOpenActions,
  countVersion,
  className,
  showResizeHandle = true,
}: FolderTreeProps) {
  const handlers = useLatestRef({ onOpen, onContextMenu, onOpenActions })
  const openFolder = useCallback((path: string) => handlers.current.onOpen(path), [handlers])
  const openContextMenu = useCallback((event: React.MouseEvent, path: string) => {
    handlers.current.onContextMenu?.(event, path)
  }, [handlers])
  const openActions = useCallback((path: string, anchor: { x: number; y: number }) => {
    handlers.current.onOpenActions?.(path, anchor)
  }, [handlers])
  const [expansion, setExpansion] = useState(() => ({ current, paths: new Set(expandedAncestorPaths(current)) }))
  if (expansion.current !== current) {
    setExpansion({ current, paths: new Set([...expansion.paths, ...expandedAncestorPaths(current)]) })
  }
  const expanded = expansion.paths
  const setExpanded = useCallback((updater: (paths: Set<string>) => Set<string>) => {
    setExpansion((previous) => ({ ...previous, paths: updater(previous.paths) }))
  }, [])
  const [scrollElement, setScrollElement] = useState<HTMLDivElement | null>(null)
  const [isPullRefreshing, setIsPullRefreshing] = useState(false)
  const [pullDistance, setPullDistance] = useState(0)
  const pullStartYRef = useRef<number | null>(null)
  const isPullingRef = useRef(false)
  const resetPullState = useCallback(() => {
    setPullDistance(0)
    pullStartYRef.current = null
    isPullingRef.current = false
  }, [])

  const handlePullRefresh = useCallback(async () => {
    if (!onPullRefresh || isPullRefreshing) return
    setIsPullRefreshing(true)
    try {
      await onPullRefresh()
    } catch (err) {
      console.error('Failed to refresh folders:', err)
    } finally {
      setIsPullRefreshing(false)
      setPullDistance(0)
    }
  }, [onPullRefresh, isPullRefreshing])

  const handleTouchStart = useCallback((e: React.TouchEvent<HTMLDivElement>) => {
    if (!onPullRefresh || isPullRefreshing) return
    if (e.touches.length !== 1) return
    if (e.currentTarget.scrollTop > 0) return
    pullStartYRef.current = e.touches[0].clientY
    isPullingRef.current = false
  }, [onPullRefresh, isPullRefreshing])

  const handleTouchMove = useCallback((e: React.TouchEvent<HTMLDivElement>) => {
    if (!onPullRefresh || isPullRefreshing) return
    if (e.touches.length !== 1) return
    const startY = pullStartYRef.current
    if (startY == null) return
    if (e.currentTarget.scrollTop > 0) {
      resetPullState()
      return
    }
    const delta = e.touches[0].clientY - startY
    if (delta <= 0) {
      if (isPullingRef.current) setPullDistance(0)
      return
    }
    if (!isPullingRef.current && delta < 8) return
    isPullingRef.current = true
    e.preventDefault()
    setPullDistance(Math.min(MAX_PULL_DISTANCE, delta * 0.55))
  }, [isPullRefreshing, onPullRefresh, resetPullState])

  const handleTouchEnd = useCallback(() => {
    if (!onPullRefresh || isPullRefreshing) {
      resetPullState()
      return
    }
    const shouldRefresh = isPullingRef.current && pullDistance >= PULL_REFRESH_THRESHOLD
    pullStartYRef.current = null
    isPullingRef.current = false
    if (shouldRefresh) {
      void handlePullRefresh()
      return
    }
    setPullDistance(0)
  }, [handlePullRefresh, isPullRefreshing, onPullRefresh, pullDistance, resetPullState])

  const containerClass = className ?? 'h-full overflow-auto bg-panel scrollbar-thin'
  const stableContainerClass = `${containerClass} folder-tree-scroll`
  const treeContainerClass = onPullRefresh ? `${stableContainerClass} overscroll-y-contain` : stableContainerClass
  const showPullIndicator = !!onPullRefresh && (isPullRefreshing || pullDistance > 0)
  const pullReady = pullDistance >= PULL_REFRESH_THRESHOLD
  const pullIndicatorHeight = isPullRefreshing ? 28 : Math.min(44, pullDistance)

  return (
    <div
      ref={setScrollElement}
      className={treeContainerClass}
      onTouchStart={onPullRefresh ? handleTouchStart : undefined}
      onTouchMove={onPullRefresh ? handleTouchMove : undefined}
      onTouchEnd={onPullRefresh ? handleTouchEnd : undefined}
      onTouchCancel={onPullRefresh ? handleTouchEnd : undefined}
    >
      {showPullIndicator && (
        <div
          className="flex items-end justify-center text-[11px] text-muted select-none transition-[height,opacity] duration-150"
          style={{ height: pullIndicatorHeight, opacity: isPullRefreshing || pullDistance > 8 ? 1 : 0.65 }}
          aria-live="polite"
        >
          {isPullRefreshing ? 'Refreshing…' : (pullReady ? 'Release to refresh' : 'Pull to refresh')}
        </div>
      )}
      <FolderTreeRows
        active={active} roots={roots} current={current} initial={data}
        expanded={expanded} setExpanded={setExpanded} scrollElement={scrollElement}
        onOpen={openFolder} onContextMenu={onContextMenu ? openContextMenu : undefined}
        onOpenActions={onOpenActions ? openActions : undefined} countVersion={countVersion}
      />
      {showResizeHandle && (
        <div
          className="toolbar-offset sidebar-resize-handle absolute bottom-0 left-[calc(var(--grid-left)-6px)]"
          onPointerDown={onResize}
        />
      )}
    </div>
  )
}
