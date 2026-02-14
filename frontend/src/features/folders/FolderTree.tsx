import React, { useCallback, useEffect, useRef, useState } from 'react'
import { useQueryClient } from '@tanstack/react-query'
import type { FolderIndex } from '../../lib/types'
import { folderQueryKey, useFolder } from '../../shared/api/folders'
import { api } from '../../shared/api/client'
import { middleTruncate } from '../../lib/util'
import { joinPath, sanitizePath } from '../../app/routing/hash'
import { useFolderTreeDragDrop } from './hooks/useFolderTreeDragDrop'
import { useFolderTreeKeyboardNav } from './hooks/useFolderTreeKeyboardNav'

interface Root {
  label: string
  path: string
}

interface FolderTreeProps {
  current: string
  roots: Root[]
  data?: FolderIndex
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

function getExpandedAncestorPaths(path: string): string[] {
  const parts = path.split('/').filter(Boolean)
  const ancestors = ['/']
  let current = ''
  for (const part of parts) {
    current = current ? `${current}/${part}` : `/${part}`
    ancestors.push(current)
  }
  return ancestors
}

export default function FolderTree({
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
  const [expanded, setExpanded] = useState<Set<string>>(new Set(['/']))
  const countCacheRef = useRef<Map<string, number>>(new Map())
  const inflightRef = useRef<Map<string, Promise<number>>>(new Map())
  const [isPullRefreshing, setIsPullRefreshing] = useState(false)
  const [pullDistance, setPullDistance] = useState(0)
  const pullStartYRef = useRef<number | null>(null)
  const isPullingRef = useRef(false)
  const queryClient = useQueryClient()
  const resetPullState = useCallback(() => {
    setPullDistance(0)
    pullStartYRef.current = null
    isPullingRef.current = false
  }, [])

  const getSubtreeCount = useCallback(async (path: string): Promise<number> => {
    const target = sanitizePath(path || '/')
    const cache = countCacheRef.current
    const inflight = inflightRef.current
    const cached = cache.get(target)
    if (cached !== undefined) return cached

    const recursiveKey = folderQueryKey(target, { recursive: true })
    const cachedRecursive = queryClient.getQueryData<FolderIndex>(recursiveKey)
    if (cachedRecursive) {
      const count = cachedRecursive.totalItems ?? cachedRecursive.items.length
      cache.set(target, count)
      return count
    }

    const pending = inflight.get(target)
    if (pending) return pending

    const promise = (async () => {
      try {
        const state = queryClient.getQueryState(recursiveKey)
        if (state?.fetchStatus === 'fetching') {
          const folder = await queryClient.fetchQuery({
            queryKey: recursiveKey,
            queryFn: () => api.getFolder(target, { recursive: true }),
          })
          const count = folder.totalItems ?? folder.items.length
          cache.set(target, count)
          return count
        }
        const folder = await api.getFolderCount(target)
        const count = folder.totalItems ?? folder.items.length
        cache.set(target, count)
        return count
      } finally {
        inflight.delete(target)
      }
    })()

    inflight.set(target, promise)
    return promise
  }, [queryClient])

  useEffect(() => {
    countCacheRef.current.clear()
    inflightRef.current.clear()
  }, [countVersion])

  useEffect(() => {
    const ancestorPaths = getExpandedAncestorPaths(current)
    setExpanded((prev) => {
      const next = new Set(prev)
      for (const ancestorPath of ancestorPaths) {
        next.add(ancestorPath)
      }
      return next
    })
  }, [current])

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
  const treeContainerClass = onPullRefresh ? `${containerClass} overscroll-y-contain` : containerClass
  const showPullIndicator = !!onPullRefresh && (isPullRefreshing || pullDistance > 0)
  const pullReady = pullDistance >= PULL_REFRESH_THRESHOLD
  const pullIndicatorHeight = isPullRefreshing ? 28 : Math.min(44, pullDistance)

  return (
    <div
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
      <div className="p-1" role="tree" aria-label="Folders">
        {roots.map(r => (
          <TreeNode
            key={r.path}
            path={r.path}
            label={r.label}
            depth={0}
            current={current}
            expanded={expanded}
            setExpanded={setExpanded}
            onOpen={onOpen}
            onContextMenu={onContextMenu}
            onOpenActions={onOpenActions}
            initial={data}
            getSubtreeCount={getSubtreeCount}
            countVersion={countVersion}
          />
        ))}
      </div>
      {showResizeHandle && (
        <div
          className="toolbar-offset sidebar-resize-handle absolute bottom-0 left-[calc(var(--left)-6px)]"
          onPointerDown={onResize}
        />
      )}
    </div>
  )
}

interface TreeNodeProps {
  path: string
  label: string
  depth: number
  current: string
  expanded: Set<string>
  setExpanded: (updater: (s: Set<string>) => Set<string>) => void
  onOpen: (path: string) => void
  onContextMenu?: (e: React.MouseEvent, path: string) => void
  onOpenActions?: (path: string, anchor: { x: number; y: number }) => void
  initial?: FolderIndex
  getSubtreeCount: (path: string) => Promise<number>
  countVersion?: number
}

function TreeNode({
  path,
  label,
  depth,
  current,
  expanded,
  setExpanded,
  onOpen,
  onContextMenu,
  onOpenActions,
  initial,
  getSubtreeCount,
  countVersion,
}: TreeNodeProps) {
  const isExpanded = expanded.has(path)
  const isActive = current === path
  const shouldFetchFolder = path === '/' || isExpanded || isActive
  const { data } = useFolder(path, false, { enabled: shouldFetchFolder })
  const idx = initial && path === initial.path ? initial : data
  const hasIndex = !!idx
  const isLeaf = hasIndex ? idx.dirs.length === 0 : false
  const [subtreeCount, setSubtreeCount] = useState<number | null>(idx ? idx.items.length : null)

  const onKeyDown = useFolderTreeKeyboardNav({
    path,
    isLeaf,
    isExpanded,
    setExpanded,
    onOpen,
  })

  const { onDragOver, onDragEnter, onDragLeave, onDrop } = useFolderTreeDragDrop({ path, isLeaf })

  const toggle = (e: React.MouseEvent<HTMLButtonElement>) => {
    e.stopPropagation()
    if (isLeaf) return
    setExpanded((prev) => {
      const next = new Set(prev)
      if (next.has(path)) {
        next.delete(path)
      } else {
        next.add(path)
      }
      return next
    })
  }

  const openActions = (e: React.MouseEvent<HTMLButtonElement>) => {
    e.stopPropagation()
    if (!onOpenActions) return
    const rect = e.currentTarget.getBoundingClientRect()
    onOpenActions(path, { x: rect.right - 4, y: rect.bottom - 4 })
  }

  useEffect(() => {
    let cancelled = false
    if (!idx) {
      setSubtreeCount(null)
      return
    }
    setSubtreeCount(idx.items.length)
    const shouldResolveRecursiveCount = isExpanded && (depth > 0 || isActive)
    if (!shouldResolveRecursiveCount) {
      return
    }
    getSubtreeCount(path)
      .then((count) => {
        if (!cancelled) setSubtreeCount(count)
      })
      .catch((err) => {
        if (!cancelled) console.warn(`Failed to compute subtree count for ${path}:`, err)
      })
    return () => {
      cancelled = true
    }
  }, [idx, path, getSubtreeCount, countVersion, isExpanded, depth, isActive])

  return (
    <div>
      <div
        className={`tree-row flex items-center gap-1.5 py-1 px-2 rounded-md cursor-pointer min-h-[40px] outline-none transition-colors duration-75 ${isActive ? 'bg-accent/20 text-accent font-medium' : 'hover:bg-white/5 text-text'}`}
        role="treeitem"
        aria-level={depth+1}
        aria-expanded={isLeaf ? undefined : isExpanded}
        aria-selected={isActive}
        tabIndex={isActive ? 0 : -1}
        style={{ paddingLeft: 8 + depth * 14 }}
        onClick={() => onOpen(path)}
        onContextMenu={(e) => {
          e.preventDefault()
          e.stopPropagation()
          onContextMenu?.(e, path)
        }}
        onKeyDown={onKeyDown}
        onDragOver={onDragOver}
        onDragEnter={onDragEnter}
        onDragLeave={onDragLeave}
        onDrop={onDrop}
      >
        <button
          type="button"
          className="tree-expand-btn touch-manipulation"
          onClick={toggle}
          aria-label={isLeaf ? `No subfolders in ${label}` : `${isExpanded ? 'Collapse' : 'Expand'} ${label}`}
          aria-expanded={isLeaf ? undefined : isExpanded}
          disabled={isLeaf}
        >
          {isLeaf ? '•' : (isExpanded ? '▼' : '▶')}
        </button>
        <span className="flex-1 overflow-hidden truncate text-sm" title={label}>{middleTruncate(label, 28)}</span>
        {subtreeCount !== null && (
          <span className="text-[10px] opacity-50 bg-white/5 border border-white/5 rounded px-1.5 min-w-[24px] text-center">
            {subtreeCount}
          </span>
        )}
        {onOpenActions && (
          <button
            type="button"
            className="tree-row-action-btn touch-manipulation"
            aria-label={`Open actions for ${label}`}
            aria-haspopup="menu"
            onPointerDown={(e) => e.stopPropagation()}
            onClick={openActions}
          >
            <svg width="13" height="13" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round" aria-hidden="true">
              <circle cx="12" cy="5" r="1.5" />
              <circle cx="12" cy="12" r="1.5" />
              <circle cx="12" cy="19" r="1.5" />
            </svg>
          </button>
        )}
      </div>
      {isExpanded && idx?.dirs?.map(d => (
        <TreeNode
          key={d.name}
          path={joinPath(path, d.name)}
          label={d.name}
          depth={depth+1}
          current={current}
          expanded={expanded}
          setExpanded={setExpanded}
          onOpen={onOpen}
          onContextMenu={onContextMenu}
          onOpenActions={onOpenActions}
          getSubtreeCount={getSubtreeCount}
          countVersion={countVersion}
        />
      ))}
    </div>
  )
}
