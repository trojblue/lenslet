import React, { type CSSProperties, type Key, type ReactNode, type RefObject } from 'react'
import type { BrowseItemPayload } from '../../../lib/types'
import type { VirtualGridLayout } from '../hooks/useVirtualGrid'
import ThumbCard from './ThumbCard'

type VirtualGridVirtualRow = {
  key: Key
  index: number
  start: number
}

type VirtualGridRowItem = {
  item: BrowseItemPayload
  displayW: number
  displayH: number
  fit?: 'contain'
}

type VirtualGridRowsProps = {
  virtualRows: readonly VirtualGridVirtualRow[]
  layout: VirtualGridLayout
  items: readonly BrowseItemPayload[]
  gap: number
  scrollRootRef: RefObject<HTMLDivElement>
  suppressSelectionHighlight: boolean
  active: string | null
  focused: string | null
  selectedSet: ReadonlySet<string>
  selectionOrderByPath: ReadonlyMap<string, number>
  recentlyUpdated?: ReadonlyMap<string, string>
  highlight?: string
  isScrolling: boolean
  multiSelectMode: boolean
  onCellFocus: (path: string) => void
  onPointerDown: (path: string, event: React.PointerEvent<HTMLDivElement>) => void
  onPointerMove: (event: React.PointerEvent<HTMLDivElement>) => void
  onPointerUp: (event: React.PointerEvent<HTMLDivElement>) => void
  onPointerCancel: (event: React.PointerEvent<HTMLDivElement>) => void
  onContextMenuItem?: (event: React.MouseEvent, path: string) => void
  onOpenItemActions: (path: string, anchor: { x: number; y: number }) => void
  onOpenViewer: (path: string) => void
  onClearPreview: () => void
  onSchedulePreview: (path: string) => void
  onItemClick: (path: string, event: React.MouseEvent) => void
  demandThumbPaths: ReadonlySet<string>
}

function renderHighlightedName(name: string, highlight?: string): ReactNode {
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

function getRowItems({
  layout,
  items,
  rowIndex,
}: {
  layout: VirtualGridLayout
  items: readonly BrowseItemPayload[]
  rowIndex: number
}): {
  items: VirtualGridRowItem[]
  height?: number
  imageHeight?: number
} | null {
  if (layout.mode === 'adaptive') {
    const row = layout.rows[rowIndex]
    if (!row) return null
    return {
      items: row.items,
      height: row.height,
      imageHeight: row.imageH,
    }
  }

  const start = rowIndex * layout.columns
  return {
    items: items.slice(start, start + layout.columns).map((item) => ({
      item,
      displayW: layout.cellW,
      displayH: layout.mediaH,
    })),
  }
}

function getRowLayoutStyle({
  layout,
  rowStart,
  rowHeight,
  gap,
}: {
  layout: VirtualGridLayout
  rowStart: number
  rowHeight?: number
  gap: number
}): {
  className: string
  style: CSSProperties
} {
  if (layout.mode === 'adaptive') {
    return {
      className: 'absolute top-0 left-0 right-0 w-full will-change-transform',
      style: {
        height: rowHeight,
        transform: `translate3d(0, ${rowStart}px, 0)`,
        display: 'flex',
        gap,
        paddingBottom: gap,
      },
    }
  }

  return {
    className: 'absolute top-0 left-0 right-0 w-full grid will-change-transform',
    style: {
      transform: `translate3d(0, ${rowStart}px, 0)`,
      gridTemplateColumns: `repeat(${layout.columns}, minmax(0, 1fr))`,
      gap,
      paddingBottom: gap,
    },
  }
}

export default function VirtualGridRows({
  virtualRows,
  layout,
  items,
  gap,
  scrollRootRef,
  suppressSelectionHighlight,
  active,
  focused,
  selectedSet,
  selectionOrderByPath,
  recentlyUpdated,
  highlight,
  isScrolling,
  multiSelectMode,
  onCellFocus,
  onPointerDown,
  onPointerMove,
  onPointerUp,
  onPointerCancel,
  onContextMenuItem,
  onOpenItemActions,
  onOpenViewer,
  onClearPreview,
  onSchedulePreview,
  onItemClick,
  demandThumbPaths,
}: VirtualGridRowsProps): JSX.Element {
  return (
    <>
      {virtualRows.map((row) => {
        const rowData = getRowItems({ layout, items, rowIndex: row.index })
        if (!rowData) return null

        const { className, style } = getRowLayoutStyle({
          layout,
          rowStart: row.start,
          rowHeight: rowData.height,
          gap,
        })
        return (
          <div
            key={row.key}
            className={className}
            role="row"
            data-adaptive-image-height={rowData.imageHeight}
            style={style}
          >
            {rowData.items.map(({ item, displayW, displayH, fit }) => {
              const isVisuallySelected = !suppressSelectionHighlight
                && (active === item.path || selectedSet.has(item.path))
              const selectionOrder = selectionOrderByPath.get(item.path) ?? null
              const recentUpdateKey = recentlyUpdated?.get(item.path) ?? null
              const isRecentlyUpdated = recentUpdateKey != null
              const wrapperStyle: CSSProperties | undefined = layout.mode === 'adaptive'
                ? { width: displayW }
                : undefined
              const imageContainerStyle: CSSProperties | undefined = layout.mode === 'adaptive'
                ? { height: displayH }
                : undefined
              const itemContainerClass = layout.mode === 'adaptive'
                ? 'relative rounded-[10px] group shrink-0'
                : 'relative aspect-[4/3] rounded-[10px] group'

              return (
                <div
                  id={`cell-${encodeURIComponent(item.path)}`}
                  key={item.path}
                  className="relative min-w-0"
                  role="gridcell"
                  data-adaptive-fit={fit}
                  aria-selected={isVisuallySelected}
                  tabIndex={focused === item.path ? 0 : -1}
                  onFocus={() => onCellFocus(item.path)}
                  style={wrapperStyle}
                  onPointerDown={(event) => onPointerDown(item.path, event)}
                  onPointerMove={onPointerMove}
                  onPointerUp={onPointerUp}
                  onPointerCancel={onPointerCancel}
                  onContextMenu={(event) => {
                    event.preventDefault()
                    event.stopPropagation()
                    onContextMenuItem?.(event, item.path)
                  }}
                >
                  <div
                    className={itemContainerClass}
                    style={imageContainerStyle}
                    onDoubleClick={() => {
                      if (!multiSelectMode) onOpenViewer(item.path)
                    }}
                    onMouseLeave={onClearPreview}
                  >
                    <button
                      type="button"
                      className="grid-item-action-btn touch-manipulation"
                      data-grid-action="1"
                      aria-label={`Open actions for ${item.name}`}
                      aria-haspopup="menu"
                      onPointerDown={(event) => event.stopPropagation()}
                      onClick={(event) => {
                        event.stopPropagation()
                        const rect = event.currentTarget.getBoundingClientRect()
                        onOpenItemActions(item.path, { x: rect.right - 4, y: rect.bottom - 4 })
                      }}
                    >
                      <svg
                        width="13"
                        height="13"
                        viewBox="0 0 24 24"
                        fill="none"
                        stroke="currentColor"
                        strokeWidth="2"
                        strokeLinecap="round"
                        strokeLinejoin="round"
                        aria-hidden="true"
                      >
                        <circle cx="12" cy="5" r="1.5" />
                        <circle cx="12" cy="12" r="1.5" />
                        <circle cx="12" cy="19" r="1.5" />
                      </svg>
                    </button>
                    <div className="cell-content absolute inset-0">
                      <ThumbCard
                        path={item.path}
                        name={item.name}
                        selected={isVisuallySelected}
                        highlighted={isRecentlyUpdated}
                        highlightKey={recentUpdateKey}
                        selectionOrder={selectionOrder}
                        displayW={displayW}
                        displayH={displayH}
                        fit={fit}
                        ioRoot={scrollRootRef.current}
                        isScrolling={isScrolling}
                        priority={demandThumbPaths.has(item.path)}
                        onClick={(event: React.MouseEvent) => onItemClick(item.path, event)}
                      />
                    </div>
                    <div
                      className="grid-item-preview-hotspot absolute right-0 bottom-0 w-7 h-7 cursor-zoom-in"
                      onMouseEnter={() => onSchedulePreview(item.path)}
                      onMouseLeave={onClearPreview}
                    >
                      <div
                        className="grid-item-preview-corner absolute right-0 bottom-0 h-[18px] w-[18px] flex items-center justify-center text-text select-none"
                        style={{
                          clipPath: 'path("M0 9C0 4.02944 4.02944 0 9 0H18V18H0V9Z")',
                          background: 'linear-gradient(135deg, rgba(18,18,18,0.9) 0%, rgba(34,34,34,0.9) 60%, rgba(22,22,22,0.9) 100%)',
                          borderTop: '1px solid rgba(255,255,255,0.08)',
                          borderLeft: '1px solid rgba(255,255,255,0.08)',
                          boxShadow: '0 1px 2px rgba(0,0,0,0.45)',
                          backdropFilter: 'blur(1px)',
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
                  <div className="flex flex-col items-center text-center gap-0.5 mt-2 px-1 text-text-secondary">
                    <div
                      className="text-xs font-medium leading-[16px] thumb-filename line-clamp-2 break-words hyphens-auto text-center"
                      title={item.name}
                    >
                      {renderHighlightedName(item.name, highlight)}
                    </div>
                    <div className="text-[10px] leading-[14px] text-muted">
                      {item.width} &times; {item.height}
                    </div>
                  </div>
                </div>
              )
            })}
          </div>
        )
      })}
    </>
  )
}
