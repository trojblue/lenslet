import React, { useEffect, useRef, useState } from 'react'
import Dropdown from './Dropdown'
import SyncIndicator, { type SyncIndicatorData } from './SyncIndicator'
import type { SortSpec, ViewMode } from '../../lib/types'
import { LAYOUT_MEDIA_QUERIES } from '../../lib/breakpoints'
import { useMediaQuery } from '../hooks/useMediaQuery'
import SortDirectionIcon from './toolbar/SortDirectionIcon'
import ToolbarFilterMenu from './toolbar/ToolbarFilterMenu'
import ToolbarMobileDrawer from './toolbar/ToolbarMobileDrawer'

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
  sortDisabled?: boolean
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
  searchDisabled?: boolean
  searchPlaceholder?: string
  onUploadClick?: () => void
  uploadBusy?: boolean
  uploadDisabled?: boolean
  multiSelectMode?: boolean
  selectedCount?: number
  onToggleMultiSelectMode?: () => void
  syncIndicator?: SyncIndicatorData
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
  sortDisabled = false,
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
  searchDisabled = false,
  searchPlaceholder,
  onUploadClick,
  uploadBusy = false,
  uploadDisabled = false,
  multiSelectMode = false,
  selectedCount = 0,
  onToggleMultiSelectMode,
  syncIndicator,
}: ToolbarProps): JSX.Element {
  const [filtersOpen, setFiltersOpen] = useState(false)
  const [mobileSearchOpen, setMobileSearchOpen] = useState(false)
  const filtersRef = useRef<HTMLDivElement>(null)
  const searchInputRef = useRef<HTMLInputElement>(null)
  const isNarrow = useMediaQuery(LAYOUT_MEDIA_QUERIES.narrow)
  const isPhone = useMediaQuery(LAYOUT_MEDIA_QUERIES.phone)
  const isToolbarCompact = useMediaQuery(LAYOUT_MEDIA_QUERIES.toolbarCompact)

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
    if (searchDisabled) {
      setMobileSearchOpen(false)
      return
    }
    if (!isNarrow || viewerActive) {
      setMobileSearchOpen(false)
      return
    }
    if (!mobileSearchOpen) return
    const handle = window.requestAnimationFrame(() => searchInputRef.current?.focus())
    return () => window.cancelAnimationFrame(handle)
  }, [isNarrow, mobileSearchOpen, viewerActive, searchDisabled])

  const effectiveSort: SortSpec = sortSpec ?? { kind: 'builtin', key: 'added', dir: 'desc' }
  const sortDir = effectiveSort.dir
  const isRandom = effectiveSort.kind === 'builtin' && effectiveSort.key === 'random'
  const sortControlsDisabled = viewerActive || sortDisabled

  const metricOptions = metricKeys?.length
    ? metricKeys.map((key) => ({ value: `metric:${key}`, label: key, disabled: sortDisabled }))
    : []
  const sortByOptions = [
    { value: 'builtin:added', label: 'Date added', disabled: sortDisabled },
    { value: 'builtin:name', label: 'Filename', disabled: sortDisabled },
    { value: 'builtin:random', label: 'Random', disabled: sortDisabled },
    ...metricOptions,
  ]

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
      options: sortByOptions,
    },
  ]

  // Determine current sort/layout value
  const currentSort = effectiveSort.kind === 'metric'
    ? `metric:${effectiveSort.key}`
    : `builtin:${effectiveSort.key}`

  const sortOnlyOptions = [
    {
      label: 'Sort by',
      options: sortByOptions,
    },
  ]

  const showMobileDrawer = isNarrow && !viewerActive
  const isCompactViewer = Boolean(viewerActive) && isToolbarCompact
  const showSortFiltersInToolbar = !isCompactViewer
  const showToolbarNav = !!viewerActive && !isPhone
  const showSelectModeToggle = showMobileDrawer && !!onToggleMultiSelectMode
  const selectModeLabel = multiSelectMode
    ? (selectedCount > 0 ? `Done (${selectedCount})` : 'Done')
    : 'Select'

  const handleSortLayoutChange = (value: string) => {
    if (value.startsWith('layout:')) {
      const mode = value === 'layout:masonry' ? 'adaptive' : 'grid'
      onViewMode?.(mode)
    } else {
      if (sortDisabled) return
      onSortChange?.(parseSort(value, effectiveSort))
    }
  }

  const handleSortDirToggle = () => {
    if (!onSortChange || sortDisabled) return
    if (isRandom) {
      onSortChange(effectiveSort) // Re-shuffle
    } else {
      onSortChange({ ...effectiveSort, dir: sortDir === 'desc' ? 'asc' : 'desc' })
    }
  }

  // Count active star filters
  const starFilterList = starFilters ?? []
  const activeStarCount = starFilterList.length
  const totalFilterCount = getTotalFilterCount(filterCount, activeStarCount)
  const countLabel = formatCountLabel(itemCount, totalCount)
  const scopeName = currentLabel || 'Root'

  return (
    <div
      ref={rootRef}
      className={`toolbar-shell ${viewerActive ? 'toolbar-shell-viewer' : ''} ${isPhone ? 'toolbar-shell-phone' : ''} ${isToolbarCompact ? 'toolbar-shell-compact' : ''} fixed top-0 left-0 right-0 h-12 grid grid-cols-[minmax(0,1fr)_minmax(0,1fr)_auto] items-center px-3 gap-3 bg-panel border-b border-border z-[var(--z-toolbar)] col-span-full row-start-1 select-none`}
    >
      {/* Left section */}
      <div className="toolbar-left flex items-center gap-4 min-w-0">
        <div className="toolbar-scope flex items-center gap-3 min-w-0">
          <div className="toolbar-scope-text flex flex-col min-w-0 leading-tight">
            <span className="toolbar-scope-label text-[10px] uppercase tracking-widest text-muted">Scope</span>
            <span className="text-sm font-medium text-text truncate" title={scopeName}>
              {scopeName}
            </span>
          </div>
          {countLabel && (
            <span className="toolbar-count text-xs text-muted whitespace-nowrap tabular-nums">{countLabel}</span>
          )}
        </div>
        {viewerActive && (
          <button className="toolbar-back-btn btn btn-sm" onClick={onBack} title="Back to grid">
            <svg width="12" height="12" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
              <path d="M15 18l-6-6 6-6" />
            </svg>
            Back
          </button>
        )}
        {showSortFiltersInToolbar && (
          <div className="toolbar-sort flex items-center gap-2">
            <div className={`toolbar-sort-controls flex items-center gap-2 ${viewerActive ? 'opacity-40 pointer-events-none' : ''}`}>
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
                onClick={handleSortDirToggle}
                title={sortDisabled ? 'Sorting disabled' : (isRandom ? 'Shuffle' : `Sort ${sortDir === 'desc' ? 'descending' : 'ascending'}`)}
                aria-label={isRandom ? 'Shuffle' : 'Toggle sort direction'}
                aria-disabled={sortControlsDisabled}
                disabled={sortControlsDisabled}
              >
                <SortDirectionIcon isRandom={isRandom} dir={sortDir} />
              </button>
            </div>
            <ToolbarFilterMenu
              viewerActive={Boolean(viewerActive)}
              filtersOpen={filtersOpen}
              filtersRef={filtersRef}
              totalFilterCount={totalFilterCount}
              filterCount={filterCount}
              starFilterList={starFilterList}
              starCounts={starCounts}
              onToggleFilters={() => setFiltersOpen((value) => !value)}
              onOpenFilters={onOpenFilters}
              onToggleStar={onToggleStar}
              onClearFilters={onClearFilters}
              onClearStars={onClearStars}
            />
          </div>
        )}
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
        {showToolbarNav && (
          <div className="toolbar-nav flex items-center gap-1 mr-1">
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
        {!viewerActive && onUploadClick && (
          <button
            className={`btn ${uploadDisabled ? 'opacity-50 cursor-not-allowed' : ''}`}
            onClick={() => !uploadDisabled && onUploadClick()}
            aria-label="Upload images"
            title={uploadBusy ? 'Uploading…' : 'Upload images'}
            aria-disabled={uploadDisabled || uploadBusy}
            disabled={uploadDisabled || uploadBusy}
          >
            <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round" aria-hidden="true">
              <path d="M12 16V5" />
              <path d="M7 10l5-5 5 5" />
              <path d="M4 19h16" />
            </svg>
            <span>{uploadBusy ? 'Uploading…' : 'Upload'}</span>
          </button>
        )}
        {syncIndicator && (
          <SyncIndicator
            {...syncIndicator}
            isNarrow={isNarrow || isToolbarCompact}
          />
        )}
        {!viewerActive && isNarrow && (
          <button
            className={`btn btn-icon ${mobileSearchOpen ? 'btn-active' : ''} ${searchDisabled ? 'opacity-50 cursor-not-allowed' : ''}`}
            aria-label={mobileSearchOpen ? 'Close search' : 'Open search'}
            title={searchDisabled ? 'Search disabled' : (mobileSearchOpen ? 'Close search' : 'Search')}
            onClick={() => !searchDisabled && setMobileSearchOpen((prev) => !prev)}
            disabled={searchDisabled}
          >
            <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round" aria-hidden="true">
              <circle cx="11" cy="11" r="7" />
              <path d="M21 21l-4.35-4.35" />
            </svg>
          </button>
        )}
        {!viewerActive && !isNarrow ? (
          <div className="toolbar-search toolbar-search-desktop w-[240px]">
            <input
              ref={searchInputRef}
              aria-label="Search filename, tags, notes"
              placeholder={searchDisabled ? (searchPlaceholder ?? 'Search disabled') : 'Search...'}
              onChange={(e) => onSearch(e.target.value)}
              className="toolbar-search-input input w-full focus:w-full transition-all duration-200 select-text"
              disabled={searchDisabled}
            />
          </div>
        ) : null}
      </div>
      {!viewerActive && isNarrow && mobileSearchOpen && !searchDisabled && (
        <div className="toolbar-search-row">
          <input
            ref={searchInputRef}
            aria-label="Search filename, tags, notes"
            placeholder={searchPlaceholder ?? 'Search...'}
            onChange={(e) => onSearch(e.target.value)}
            className="toolbar-search-input-mobile input input-lg w-full select-text"
          />
        </div>
      )}
      {showMobileDrawer && (
        <ToolbarMobileDrawer
          viewMode={viewMode}
          currentSort={currentSort}
          sortOnlyOptions={sortOnlyOptions}
          sortDisabled={sortDisabled}
          sortControlsDisabled={sortControlsDisabled}
          sortDir={sortDir}
          isRandom={isRandom}
          showSelectModeToggle={showSelectModeToggle}
          multiSelectMode={multiSelectMode}
          selectModeLabel={selectModeLabel}
          uploadBusy={uploadBusy}
          uploadDisabled={uploadDisabled}
          onViewMode={onViewMode}
          onSortChange={(value) => onSortChange?.(parseSort(value, effectiveSort))}
          onToggleSortDir={handleSortDirToggle}
          onToggleMultiSelectMode={onToggleMultiSelectMode}
          onUploadClick={onUploadClick}
        />
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
