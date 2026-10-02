import { memo, useCallback, useLayoutEffect, useMemo, useRef, useState, type MouseEvent } from 'react'
import { defaultRangeExtractor, measureElement, observeElementRect, useVirtualizer, type Virtualizer } from '@tanstack/react-virtual'
import { useQueryClient } from '@tanstack/react-query'
import { folderQueryKey } from '../../api/folders'
import { middleTruncate } from '../../lib/util'
import type { BrowseFolderPayload } from '../../lib/types'
import { flattenFolderRows, folderKeyboardTarget, type FolderRoot, type FolderTreeRow } from './model/treeRows'
import { useFolderTreeData } from './hooks/useFolderTreeData'

export type FolderTreeRowsProps = {
  active: boolean
  roots: FolderRoot[]
  current: string
  initial?: BrowseFolderPayload
  expanded: Set<string>
  setExpanded: (updater: (value: Set<string>) => Set<string>) => void
  onOpen: (path: string) => void
  onContextMenu?: (event: MouseEvent, path: string) => void
  onOpenActions?: (path: string, anchor: { x: number; y: number }) => void
  countVersion?: number
  scrollElement: HTMLDivElement | null
}

export default memo(function FolderTreeRows(props: FolderTreeRowsProps) {
  const { active, roots, current, initial, expanded, setExpanded, scrollElement, countVersion } = props
  const queryClient = useQueryClient()
  const { payloads, errors, counts, pendingCounts } = useFolderTreeData(roots, expanded, current, active, initial, countVersion)
  const rows = useMemo(() => flattenFolderRows(roots, expanded, payloads, errors), [roots, expanded, payloads, errors])
  const [focusedPath, setFocusedPath] = useState<string | null>(null)
  const focusedIndex = focusedPath ? rows.findIndex((row) => row.kind === 'folder' && row.path === focusedPath) : -1
  const currentIndex = rows.findIndex((row) => row.kind === 'folder' && row.path === current)
  const tabStopIndex = focusedIndex >= 0 ? focusedIndex : Math.max(0, currentIndex)
  const pendingFocus = useRef<string | null>(null)
  const virtual = rows.length > 100
  const rangeExtractor = useCallback((range: Parameters<typeof defaultRangeExtractor>[0]) => {
    const indices = defaultRangeExtractor(range)
    if (!indices.includes(tabStopIndex)) indices.push(tabStopIndex)
    return indices.sort((a, b) => a - b)
  }, [tabStopIndex])
  const getItemKey = useCallback((index: number) => `${rows[index].kind}:${rows[index].path}`, [rows])
  const viewportListener = useRef<((rect: { width: number; height: number }) => void) | null>(null)
  const observeVisibleViewport = useCallback((instance: Virtualizer<HTMLDivElement, HTMLDivElement>, callback: (rect: { width: number; height: number }) => void) => {
    viewportListener.current = callback
    return observeElementRect(instance, (rect) => {
      if (rect.height > 0 && rect.width > 0) callback(rect)
    })
  }, [])
  useLayoutEffect(() => {
    const element = scrollElement
    if (active && element && element.offsetHeight > 0 && element.offsetWidth > 0) {
      viewportListener.current?.({ width: element.offsetWidth, height: element.offsetHeight })
    }
  }, [active, scrollElement])
  const measuredSizes = useRef(new Map<string, number>())
  const measureVisibleRow = useCallback((element: HTMLDivElement, entry: ResizeObserverEntry | undefined, instance: Virtualizer<HTMLDivElement, HTMLDivElement>) => {
    const key = element.dataset.rowKey ?? ''
    const size = measureElement(element, entry, instance)
    if (size > 0) measuredSizes.current.set(key, size)
    return size > 0 ? size : measuredSizes.current.get(key) ?? 40
  }, [])
  const virtualizer = useVirtualizer<HTMLDivElement, HTMLDivElement>({
    count: rows.length,
    enabled: virtual,
    getScrollElement: () => scrollElement,
    estimateSize: () => 40,
    overscan: 8,
    getItemKey,
    rangeExtractor,
    measureElement: measureVisibleRow,
    observeElementRect: observeVisibleViewport,
  })
  const visible = virtual
    ? virtualizer.getVirtualItems()
    : rows.map((row, index) => ({ index, key: `${row.kind}:${row.path}`, start: 0 }))

  useLayoutEffect(() => {
    const path = pendingFocus.current
    if (!path) return
    const target = [...(scrollElement?.querySelectorAll<HTMLElement>('[data-folder-path]') ?? [])]
      .find((element) => element.dataset.folderPath === path)
    if (target) {
      target.focus({ preventScroll: true })
      pendingFocus.current = null
    }
  })

  const focusRow = (index: number) => {
    if (index < 0) return
    const path = rows[index].path
    pendingFocus.current = path
    setFocusedPath(path)
    if (virtual) virtualizer.scrollToIndex(index, { align: 'auto' })
    else {
      const target = [...(scrollElement?.querySelectorAll<HTMLElement>('[data-folder-path]') ?? [])]
        .find((element) => element.dataset.folderPath === path)
      target?.scrollIntoView({ block: 'nearest' })
    }
  }
  const toggle = (row: FolderTreeRow) => {
    if (row.leaf) return
    setExpanded((previous) => {
      const next = new Set(previous)
      if (next.has(row.path)) next.delete(row.path)
      else next.add(row.path)
      return next
    })
  }
  return (
    <div className="p-1" role="tree" aria-label="Folders" style={virtual ? { height: virtualizer.getTotalSize(), position: 'relative' } : undefined}>
      {visible.map(({ index, key, start }) => {
        const row = rows[index]
        const selected = current === row.path
        const count = counts[row.path] ?? (row.leaf ? row.payload?.items.length : null) ?? null
        const countPending = count === null && (pendingCounts.has(row.path) || (active && row.expanded && !row.payload && !errors.has(row.path)))
        const countLabel = count !== null ? `${count.toLocaleString()} items` : countPending ? 'Folder item count loading' : 'Expand folder to load its item count' 
        return (
          <div key={key} data-index={index} data-row-key={key} ref={virtual ? virtualizer.measureElement : undefined}
            style={virtual ? { position: 'absolute', top: 0, left: 4, right: 4, transform: `translateY(${start}px)` } : undefined}>
            {row.kind !== 'folder' ? (
              <div className={`tree-child-state ${row.kind === 'error' ? 'text-danger' : 'text-muted'}`}
                style={{ paddingLeft: 8 + row.depth * 14 }} role={row.kind === 'error' ? 'alert' : 'status'}>
                {row.kind === 'error' ? <>
                  <span>Couldn’t load folders.</span>
                  <button type="button" className="ml-2 underline" onClick={() => {
                    void queryClient.refetchQueries({ queryKey: folderQueryKey(row.path), exact: true })
                  }}>Retry</button>
                </> : 'Loading folders…'}
              </div>
            ) : (
              <div className={`tree-row flex items-center gap-1.5 py-1 px-2 rounded-md cursor-pointer min-h-[40px] outline-none transition-colors ${selected ? 'bg-accent/20 text-text font-medium' : 'hover:bg-white/5 text-text'}`}
                role="treeitem" aria-level={row.depth + 1} aria-posinset={row.position} aria-setsize={row.siblings}
                aria-expanded={row.leaf ? undefined : row.expanded} aria-selected={selected}
                tabIndex={index === tabStopIndex ? 0 : -1}
                data-folder-path={row.path} style={{ paddingLeft: 8 + row.depth * 14 }}
                onFocus={() => setFocusedPath(row.path)} onClick={() => props.onOpen(row.path)}
                onContextMenu={(event) => { event.preventDefault(); event.stopPropagation(); props.onContextMenu?.(event, row.path) }}
                onKeyDown={(event) => {
                  if ((event.key === 'Enter' || event.key === ' ') && event.target !== event.currentTarget) return
                  if (event.key === 'Enter' || event.key === ' ') { event.preventDefault(); props.onOpen(row.path) }
                  else if (event.key === 'ArrowRight' && !row.leaf && !row.expanded) { event.preventDefault(); toggle(row) }
                  else if (event.key === 'ArrowLeft' && row.expanded) { event.preventDefault(); toggle(row) }
                  else if (['ArrowDown', 'ArrowUp', 'Home', 'End'].includes(event.key)) {
                    event.preventDefault(); focusRow(folderKeyboardTarget(rows, row.path, event.key))
                  }
                }}>
                <button type="button" className="tree-expand-btn touch-manipulation"
                  onClick={(event) => { event.stopPropagation(); toggle(row) }}
                  aria-label={row.leaf ? `No subfolders in ${row.label}` : `${row.expanded ? 'Collapse' : 'Expand'} ${row.label}`}
                  aria-expanded={row.leaf ? undefined : row.expanded} disabled={row.leaf}>
                  {row.leaf ? '•' : row.expanded ? '▼' : '▶'}
                </button>
                <span className="flex-1 overflow-hidden truncate text-sm" title={row.label}>{middleTruncate(row.label, 28)}</span>
                <span className="tree-row-count text-[10px] text-text-secondary tabular-nums bg-white/5 border border-white/5 rounded px-1.5 text-center"
                  data-pending={countPending} title={countLabel} aria-label={countLabel}>
                  {count === null ? (countPending ? '…' : '—') : count.toLocaleString()}
                </span>
                {props.onOpenActions ? <button type="button" className="tree-row-action-btn touch-manipulation"
                  aria-label={`Open actions for ${row.label}`} aria-haspopup="menu"
                  onPointerDown={(event) => event.stopPropagation()} onClick={(event) => {
                    event.stopPropagation(); const rect = event.currentTarget.getBoundingClientRect()
                    props.onOpenActions?.(row.path, { x: rect.right - 4, y: rect.bottom - 4 })
                  }}>
                  <svg width="13" height="13" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round" aria-hidden="true">
                    <circle cx="12" cy="5" r="1.5" /><circle cx="12" cy="12" r="1.5" /><circle cx="12" cy="19" r="1.5" />
                  </svg>
                </button> : <span className="tree-row-action-btn tree-row-action-placeholder" aria-hidden="true" />}
              </div>
            )}
          </div>
        )
      })}
    </div>
  )
})
