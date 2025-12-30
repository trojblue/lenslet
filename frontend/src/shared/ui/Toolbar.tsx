import React from 'react'
import Dropdown from './Dropdown'
import type { SortSpec, ViewMode } from '../../lib/types'

export interface ToolbarProps {
  onSearch: (q: string) => void
  viewerActive?: boolean
  onBack?: () => void
  zoomPercent?: number
  onZoomPercentChange?: (p: number) => void
  sortSpec?: SortSpec
  metricKeys?: string[]
  onSortChange?: (spec: SortSpec) => void
  filterCount?: number
  onOpenFilters?: () => void
  viewMode?: ViewMode
  onViewMode?: (v: ViewMode) => void
  gridItemSize?: number
  onGridItemSize?: (s: number) => void
  leftOpen?: boolean
  rightOpen?: boolean
  onToggleLeft?: () => void
  onToggleRight?: () => void
  onPrevImage?: () => void
  onNextImage?: () => void
  canPrevImage?: boolean
  canNextImage?: boolean
}

export default function Toolbar({
  onSearch,
  viewerActive,
  onBack,
  zoomPercent,
  onZoomPercentChange,
  sortSpec,
  metricKeys,
  onSortChange,
  filterCount,
  onOpenFilters,
  viewMode,
  onViewMode,
  gridItemSize,
  onGridItemSize,
  leftOpen,
  rightOpen,
  onToggleLeft,
  onToggleRight,
  onPrevImage,
  onNextImage,
  canPrevImage,
  canNextImage,
}: ToolbarProps) {
  const effectiveSort: SortSpec = sortSpec ?? { kind: 'builtin', key: 'added', dir: 'desc' }
  const sortDir = effectiveSort.dir
  const isRandom = effectiveSort.kind === 'builtin' && effectiveSort.key === 'random'

  // Build sort options with groups
  const sortOptions = [
    {
      label: 'Layout',
      options: [
        { value: 'layout:grid', label: 'Grid' },
        { value: 'layout:masonry', label: 'Masonry' },
      ],
    },
    {
      label: 'Sort by',
      options: [
        { value: 'builtin:added', label: 'Date added' },
        { value: 'builtin:name', label: 'Filename' },
        { value: 'builtin:random', label: 'Random' },
        ...(metricKeys && metricKeys.length > 0
          ? metricKeys.map((key) => ({ value: `metric:${key}`, label: key }))
          : []),
      ],
    },
  ]

  // Determine current sort/layout value
  const currentLayout = viewMode === 'adaptive' ? 'layout:masonry' : 'layout:grid'
  const currentSort = effectiveSort.kind === 'metric'
    ? `metric:${effectiveSort.key}`
    : `builtin:${effectiveSort.key}`

  const handleSortLayoutChange = (value: string) => {
    if (value.startsWith('layout:')) {
      const mode = value === 'layout:masonry' ? 'adaptive' : 'grid'
      onViewMode?.(mode)
    } else {
      onSortChange?.(parseSort(value, effectiveSort))
    }
  }

  // Get display label for sort dropdown
  const getSortLabel = () => {
    if (effectiveSort.kind === 'metric') return effectiveSort.key
    switch (effectiveSort.key) {
      case 'added': return 'Date added'
      case 'name': return 'Filename'
      case 'random': return 'Random'
      default: return 'Sort'
    }
  }

  const totalFilterCount = typeof filterCount === 'number' ? filterCount : 0

  return (
    <div className="fixed top-0 left-0 right-0 h-12 grid grid-cols-[auto_1fr_auto] items-center px-3 gap-3 bg-panel border-b border-border z-[var(--z-toolbar)] col-span-full row-start-1">
      {/* Left section */}
      <div className="flex items-center gap-2">
        {viewerActive && (
          <button className="btn" onClick={onBack}>
            <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
              <path d="M15 18l-6-6 6-6" />
            </svg>
            Back
          </button>
        )}

        {!viewerActive && (
          <div className="flex gap-2 items-center">
            {/* Sort dropdown */}
            <Dropdown
              value={currentSort}
              onChange={handleSortLayoutChange}
              options={sortOptions}
              title="Sort and layout options"
              aria-label="Sort and layout"
              triggerClassName="min-w-[110px]"
            />

            {/* Sort direction toggle */}
            <button
              className="btn btn-icon"
              onClick={() => {
                if (!onSortChange) return
                if (isRandom) {
                  onSortChange(effectiveSort) // Re-shuffle
                } else {
                  onSortChange({ ...effectiveSort, dir: sortDir === 'desc' ? 'asc' : 'desc' })
                }
              }}
              title={isRandom ? 'Shuffle' : `Sort ${sortDir === 'desc' ? 'descending' : 'ascending'}`}
              aria-label={isRandom ? 'Shuffle' : 'Toggle sort direction'}
            >
              {isRandom ? (
                <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
                  <path d="M21 12a9 9 0 1 1-9-9c2.52 0 4.93 1 6.74 2.74L21 8" />
                  <path d="M21 3v5h-5" />
                </svg>
              ) : sortDir === 'desc' ? (
                <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
                  <path d="M12 5v14" />
                  <path d="M19 12l-7 7-7-7" />
                </svg>
              ) : (
                <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
                  <path d="M12 19V5" />
                  <path d="M5 12l7-7 7 7" />
                </svg>
              )}
            </button>

            <div className="w-px h-5 bg-border" />

            <button
              className={`btn ${totalFilterCount > 0 ? 'btn-active' : ''}`}
              onClick={() => onOpenFilters?.()}
              title="Filters"
              aria-label="Open filters"
            >
              <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
                <polygon points="22 3 2 3 10 12.46 10 19 14 21 14 12.46 22 3" />
              </svg>
              <span>Filters</span>
              {totalFilterCount > 0 && (
                <span className="px-1.5 py-0.5 text-[11px] rounded-full bg-accent-strong text-text">
                  {totalFilterCount}
                </span>
              )}
            </button>
          </div>
        )}
      </div>

      {/* Center section - size slider */}
      <div className="flex items-center gap-3 justify-center">
        {viewerActive ? (
          <>
            <input
              type="range"
              min={5}
              max={800}
              step={1}
              value={Math.round(Math.max(5, Math.min(800, zoomPercent ?? 100)))}
              onChange={(e) => onZoomPercentChange?.(Number(e.target.value))}
              className="zoom-slider"
              aria-label="Zoom level"
            />
            <span className="text-xs text-muted min-w-[42px] text-right">
              {Math.round(zoomPercent ?? 100)}%
            </span>
          </>
        ) : (
          onGridItemSize && (
            <div className="flex items-center gap-2">
              <span className="text-xs text-muted">Size</span>
              <input
                type="range"
                min={80}
                max={500}
                step={10}
                value={gridItemSize ?? 220}
                onChange={(e) => onGridItemSize(Number(e.target.value))}
                className="w-32 h-1.5 bg-border rounded-full appearance-none cursor-pointer hover:bg-hover transition-colors [&::-webkit-slider-thumb]:appearance-none [&::-webkit-slider-thumb]:w-3 [&::-webkit-slider-thumb]:h-3 [&::-webkit-slider-thumb]:rounded-full [&::-webkit-slider-thumb]:bg-text [&::-moz-range-thumb]:w-3 [&::-moz-range-thumb]:h-3 [&::-moz-range-thumb]:rounded-full [&::-moz-range-thumb]:bg-text [&::-moz-range-thumb]:border-0"
                aria-label="Thumbnail size"
              />
            </div>
          )
        )}
      </div>

      {/* Right section */}
      <div className="flex items-center gap-2 justify-end toolbar-right">
        {viewerActive && (
          <div className="flex items-center gap-1 mr-1">
            <button
              className={`btn btn-icon ${canPrevImage ? '' : 'opacity-40 cursor-not-allowed'}`}
              title="Previous image (A / ←)"
              onClick={() => canPrevImage && onPrevImage?.()}
              aria-label="Previous image"
              aria-disabled={!canPrevImage}
            >
              <svg width="12" height="12" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
                <path d="M15 18l-6-6 6-6" />
              </svg>
            </button>
            <button
              className={`btn btn-icon ${canNextImage ? '' : 'opacity-40 cursor-not-allowed'}`}
              title="Next image (D / →)"
              onClick={() => canNextImage && onNextImage?.()}
              aria-label="Next image"
              aria-disabled={!canNextImage}
            >
              <svg width="12" height="12" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
                <path d="M9 6l6 6-6 6" />
              </svg>
            </button>
          </div>
        )}

        {/* Panel toggles */}
        <div className="flex items-center gap-1">
          <button
            className={`btn btn-icon ${leftOpen ? '' : 'opacity-50'}`}
            title={leftOpen ? 'Hide left panel (Ctrl+B)' : 'Show left panel (Ctrl+B)'}
            onClick={onToggleLeft}
            aria-pressed={leftOpen}
            aria-label="Toggle left panel"
          >
            <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
              <rect x="3" y="5" width="6" height="14" rx="1.5" />
              <rect x="11" y="5" width="10" height="14" rx="1.5" />
            </svg>
          </button>
          <button
            className={`btn btn-icon ${rightOpen ? '' : 'opacity-50'}`}
            title={rightOpen ? 'Hide right panel (Ctrl+Alt+B)' : 'Show right panel (Ctrl+Alt+B)'}
            onClick={onToggleRight}
            aria-pressed={rightOpen}
            aria-label="Toggle right panel"
          >
            <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
              <rect x="15" y="5" width="6" height="14" rx="1.5" />
              <rect x="3" y="5" width="10" height="14" rx="1.5" />
            </svg>
          </button>
        </div>

        {/* Search input */}
        <input
          aria-label="Search filename, tags, notes"
          placeholder="Search..."
          onChange={(e) => onSearch(e.target.value)}
          className="h-8 w-[200px] focus:w-[260px] transition-all duration-200 rounded-lg px-3 border border-border bg-surface text-text placeholder:text-muted"
        />
      </div>
    </div>
  )
}

function parseSort(value: string, fallback: SortSpec): SortSpec {
  if (value.startsWith('metric:')) {
    const key = value.slice('metric:'.length)
    if (!key) return fallback
    return { kind: 'metric', key, dir: fallback.dir }
  }
  if (value.startsWith('builtin:')) {
    const key = value.slice('builtin:'.length) as 'name' | 'added' | 'random' | string
    if (key === 'name' || key === 'added' || key === 'random') {
      return { kind: 'builtin', key, dir: fallback.dir }
    }
  }
  return fallback
}
