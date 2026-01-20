import React, { useEffect, useRef, useState } from 'react'
import Dropdown from './Dropdown'
import type { SortSpec, ViewMode } from '../../lib/types'

export interface ToolbarProps {
  rootRef?: React.RefObject<HTMLDivElement>
  onSearch: (q: string) => void
  viewerActive?: boolean
  onBack?: () => void
  zoomPercent?: number
  onZoomPercentChange?: (p: number) => void
  currentLabel?: string
  itemCount?: number
  totalCount?: number
  sortSpec?: SortSpec
  metricKeys?: string[]
  onSortChange?: (spec: SortSpec) => void
  filterCount?: number
  onOpenFilters?: () => void
  starFilters?: number[] | null
  onToggleStar?: (v: number) => void
  onClearStars?: () => void
  onClearFilters?: () => void
  starCounts?: { [k: string]: number }
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
  rootRef,
  onSearch,
  viewerActive,
  onBack,
  zoomPercent,
  onZoomPercentChange,
  currentLabel,
  itemCount,
  totalCount,
  sortSpec,
  metricKeys,
  onSortChange,
  filterCount,
  onOpenFilters,
  starFilters,
  onToggleStar,
  onClearStars,
  onClearFilters,
  starCounts,
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
}: ToolbarProps): JSX.Element {
  const [filtersOpen, setFiltersOpen] = useState(false)
  const [isNarrow, setIsNarrow] = useState(false)
  const [mobileSearchOpen, setMobileSearchOpen] = useState(false)
  const filtersRef = useRef<HTMLDivElement>(null)
  const searchInputRef = useRef<HTMLInputElement>(null)

  // Close filters on click outside
  useEffect(() => {
    if (!filtersOpen) return
    const onClick = (e: MouseEvent) => {
      if (filtersRef.current && !filtersRef.current.contains(e.target as Node)) {
        setFiltersOpen(false)
      }
    }
    window.addEventListener('click', onClick)
    return () => window.removeEventListener('click', onClick)
  }, [filtersOpen])

  useEffect(() => {
    if (typeof window === 'undefined' || !('matchMedia' in window)) return
    const media = window.matchMedia('(max-width: 900px)')
    const onChange = (evt: MediaQueryListEvent) => setIsNarrow(evt.matches)
    setIsNarrow(media.matches)
    if ('addEventListener' in media) {
      media.addEventListener('change', onChange)
      return () => media.removeEventListener('change', onChange)
    }
    media.addListener(onChange)
    return () => media.removeListener(onChange)
  }, [])

  useEffect(() => {
    if (!isNarrow || viewerActive) {
      setMobileSearchOpen(false)
      return
    }
    if (!mobileSearchOpen) return
    const handle = window.requestAnimationFrame(() => searchInputRef.current?.focus())
    return () => window.cancelAnimationFrame(handle)
  }, [isNarrow, mobileSearchOpen, viewerActive])

  const effectiveSort: SortSpec = sortSpec ?? { kind: 'builtin', key: 'added', dir: 'desc' }
  const sortDir = effectiveSort.dir
  const isRandom = effectiveSort.kind === 'builtin' && effectiveSort.key === 'random'

  const metricOptions = metricKeys?.length
    ? metricKeys.map((key) => ({ value: `metric:${key}`, label: key }))
    : []

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
        ...metricOptions,
      ],
    },
  ]

  // Determine current sort/layout value
  const currentSort = effectiveSort.kind === 'metric'
    ? `metric:${effectiveSort.key}`
    : `builtin:${effectiveSort.key}`

  const sortOnlyOptions = [
    {
      label: 'Sort by',
      options: [
        { value: 'builtin:added', label: 'Date added' },
        { value: 'builtin:name', label: 'Filename' },
        { value: 'builtin:random', label: 'Random' },
        ...metricOptions,
      ],
    },
  ]

  const showMobileDrawer = isNarrow && !viewerActive

  const handleSortLayoutChange = (value: string) => {
    if (value.startsWith('layout:')) {
      const mode = value === 'layout:masonry' ? 'adaptive' : 'grid'
      onViewMode?.(mode)
    } else {
      onSortChange?.(parseSort(value, effectiveSort))
    }
  }

  // Count active star filters
  const activeStarCount = (starFilters || []).length
  const totalFilterCount = getTotalFilterCount(filterCount, activeStarCount)
  const countLabel = formatCountLabel(itemCount, totalCount)

  return (
    <div ref={rootRef} className="toolbar-shell fixed top-0 left-0 right-0 h-12 grid grid-cols-[minmax(0,1fr)_minmax(0,1fr)_auto] items-center px-3 gap-3 bg-panel border-b border-border z-[var(--z-toolbar)] col-span-full row-start-1 select-none">
      {/* Left section */}
      <div className="toolbar-left flex items-center gap-4 min-w-0">
        <div className="flex items-center gap-3 min-w-0">
          <div className="flex flex-col min-w-0 leading-tight">
            <span className="text-[10px] uppercase tracking-widest text-muted">Scope</span>
            <span className="text-sm font-medium text-text truncate" title={currentLabel || 'Root'}>
              {currentLabel || 'Root'}
            </span>
          </div>
          {countLabel && (
            <span className="toolbar-count text-xs text-muted whitespace-nowrap tabular-nums">{countLabel}</span>
          )}
          {viewerActive && (
            <button className="btn btn-sm" onClick={onBack} title="Back to grid">
              <svg width="12" height="12" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
                <path d="M15 18l-6-6 6-6" />
              </svg>
              Back
            </button>
          )}
        </div>
        <div className={`toolbar-sort flex items-center gap-2 ${viewerActive ? 'opacity-40 pointer-events-none' : ''}`}>
          <div className="toolbar-sort-controls flex items-center gap-2">
            <Dropdown
              value={currentSort}
              onChange={handleSortLayoutChange}
              options={sortOptions}
              title="Sort and layout options"
              aria-label="Sort and layout"
              triggerClassName="min-w-[110px]"
            />
            <button
              className="toolbar-sort-dir btn btn-icon"
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
              aria-disabled={viewerActive}
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
          </div>
          <div ref={filtersRef} className="toolbar-filter relative">
            <button
              className={`btn ${totalFilterCount > 0 ? 'btn-active' : ''}`}
              onClick={() => setFiltersOpen((v) => !v)}
              aria-haspopup="dialog"
              aria-expanded={filtersOpen}
              title="Filters"
              aria-disabled={viewerActive}
            >
              <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
                <polygon points="22 3 2 3 10 12.46 10 19 14 21 14 12.46 22 3" />
              </svg>
              <span className="toolbar-filters-label">Filters</span>
              {totalFilterCount > 0 && (
                <span className="toolbar-filters-count px-1.5 py-0.5 text-[11px] rounded-full bg-accent-strong text-text">
                  {totalFilterCount}
                </span>
              )}
            </button>

            {filtersOpen && (
              <div
                role="dialog"
                aria-label="Filters"
                className="dropdown-panel w-[240px]"
                style={{ top: '38px', left: 0 }}
              >
                {/* Rating section */}
                <div className="dropdown-label">Rating</div>
                <div className="px-1">
                  {[5, 4, 3, 2, 1].map((v) => {
                    const active = (starFilters || []).includes(v)
                    const count = starCounts?.[String(v)] ?? 0
                    return (
                      <button
                        key={v}
                        onClick={() => onToggleStar?.(v)}
                        className={`dropdown-item justify-between ${active ? 'bg-accent-muted' : ''}`}
                      >
                        <span className={active ? 'text-star-active' : 'text-text'}>
                          {'★'.repeat(v)}{'☆'.repeat(5 - v)}
                        </span>
                        <span className="text-xs text-muted">{count}</span>
                      </button>
                    )
                  })}
                  <button
                    onClick={() => onToggleStar?.(0)}
                    className={`dropdown-item justify-between ${(starFilters || []).includes(0) ? 'bg-accent-muted' : ''}`}
                  >
                    <span className="text-text">Unrated</span>
                    <span className="text-xs text-muted">{starCounts?.['0'] ?? 0}</span>
                  </button>
                </div>

                <div className="dropdown-divider" />

                {/* Metrics section */}
                <div className="dropdown-label">Metrics</div>
                <button
                  className="dropdown-item"
                  onClick={() => {
                    setFiltersOpen(false)
                    onOpenFilters?.()
                  }}
                >
                  <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
                    <path d="M4 19V9" />
                    <path d="M10 19V5" />
                    <path d="M16 19v-7" />
                    <path d="M3 19h18" />
                  </svg>
                  <span>Open Metrics Panel</span>
                  {(filterCount || 0) > 0 && (
                    <span className="ml-auto text-xs text-muted">{filterCount} active</span>
                  )}
                </button>

                <div className="dropdown-divider" />

                {/* Clear all */}
                <button
                  className="dropdown-item text-muted hover:text-text"
                  onClick={() => {
                    if (onClearFilters) {
                      onClearFilters()
                    } else {
                      onClearStars?.()
                    }
                  }}
                  disabled={totalFilterCount === 0}
                >
                  Clear all filters
                </button>
              </div>
            )}
          </div>
        </div>
      </div>

      {/* Center section - size slider */}
      <div className="toolbar-center flex items-center gap-3 justify-center min-w-0">
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
                className="w-28 h-1.5 bg-border rounded-full appearance-none cursor-pointer hover:bg-hover transition-colors [&::-webkit-slider-thumb]:appearance-none [&::-webkit-slider-thumb]:w-3 [&::-webkit-slider-thumb]:h-3 [&::-webkit-slider-thumb]:rounded-full [&::-webkit-slider-thumb]:bg-text [&::-moz-range-thumb]:w-3 [&::-moz-range-thumb]:h-3 [&::-moz-range-thumb]:rounded-full [&::-moz-range-thumb]:bg-text [&::-moz-range-thumb]:border-0"
                aria-label="Thumbnail size"
              />
            </div>
          )
        )}
      </div>

      {/* Right section */}
      <div className="toolbar-right flex items-center gap-2 justify-end">
        <div className={`toolbar-nav flex items-center gap-1 mr-1 ${viewerActive ? '' : 'opacity-0 pointer-events-none'}`} aria-hidden={!viewerActive}>
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

        {/* Panel toggles */}
        <div className="toolbar-panels flex items-center gap-1">
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
        {!viewerActive && isNarrow && (
          <button
            className={`btn btn-icon ${mobileSearchOpen ? 'btn-active' : ''}`}
            aria-label={mobileSearchOpen ? 'Close search' : 'Open search'}
            title={mobileSearchOpen ? 'Close search' : 'Search'}
            onClick={() => setMobileSearchOpen((prev) => !prev)}
          >
            <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round" aria-hidden="true">
              <circle cx="11" cy="11" r="7" />
              <path d="M21 21l-4.35-4.35" />
            </svg>
          </button>
        )}
        {!viewerActive && !isNarrow ? (
          <div className="toolbar-search w-[240px]">
            <input
              ref={searchInputRef}
              aria-label="Search filename, tags, notes"
              placeholder="Search..."
              onChange={(e) => onSearch(e.target.value)}
              className="toolbar-search-input input h-8 w-full focus:w-full transition-all duration-200 rounded-lg px-3 border border-border bg-surface text-text placeholder:text-muted select-text"
            />
          </div>
        ) : viewerActive ? (
          <div className="toolbar-search w-[240px]" aria-hidden="true" />
        ) : null}
      </div>
      {!viewerActive && isNarrow && mobileSearchOpen && (
        <div className="toolbar-search-row">
          <input
            ref={searchInputRef}
            aria-label="Search filename, tags, notes"
            placeholder="Search..."
            onChange={(e) => onSearch(e.target.value)}
            className="toolbar-search-input-mobile h-9 w-full rounded-lg px-3 border border-border bg-surface text-text placeholder:text-muted select-text"
          />
        </div>
      )}
      {showMobileDrawer && (
        <div className="mobile-drawer">
          <div className="mobile-drawer-row">
            <div className="mobile-pill-group">
              <button
                className={`mobile-pill ${viewMode === 'grid' ? 'is-active' : ''}`}
                onClick={() => onViewMode?.('grid')}
                aria-pressed={viewMode === 'grid'}
              >
                Grid
              </button>
              <button
                className={`mobile-pill ${viewMode === 'adaptive' ? 'is-active' : ''}`}
                onClick={() => onViewMode?.('adaptive')}
                aria-pressed={viewMode === 'adaptive'}
              >
                Masonry
              </button>
            </div>
            <Dropdown
              value={currentSort}
              onChange={(value) => onSortChange?.(parseSort(value, effectiveSort))}
              options={sortOnlyOptions}
              aria-label="Sort"
              triggerClassName="mobile-pill mobile-pill-dropdown"
              panelClassName="mobile-drawer-panel"
            />
            <button
              className="mobile-pill mobile-pill-icon"
              onClick={() => {
                if (!onSortChange) return
                if (isRandom) {
                  onSortChange(effectiveSort)
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
          </div>
        </div>
      )}
    </div>
  )
}

function formatCountLabel(current?: number, total?: number): string | null {
  if (typeof current !== 'number') return null
  const currentLabel = current.toLocaleString()
  if (typeof total !== 'number') return `${currentLabel} items`
  const totalLabel = total.toLocaleString()
  if (total === current) return `${currentLabel} items`
  return `${currentLabel} / ${totalLabel} items`
}

function getTotalFilterCount(filterCount: number | undefined, activeStarCount: number): number {
  if (typeof filterCount === 'number') return filterCount
  if (activeStarCount > 0) return 1
  return 0
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
