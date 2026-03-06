import React, { useEffect, useRef, useState } from 'react'
import Dropdown from './Dropdown'
import SyncIndicator, { type SyncIndicatorData } from './SyncIndicator'
import type { CompareOrderMode, SortSpec, ViewMode } from '../../lib/types'
import { LAYOUT_MEDIA_QUERIES } from '../../lib/breakpoints'
import { useMediaQuery } from '../hooks/useMediaQuery'
import SortDirectionIcon from './toolbar/SortDirectionIcon'
import ToolbarFilterMenu from './toolbar/ToolbarFilterMenu'
import ToolbarMobileDrawer from './toolbar/ToolbarMobileDrawer'
import type { ThemePresetId } from '../../theme/runtime'

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
  onRefreshRoot?: () => void
  refreshEnabled?: boolean
  refreshDisabledReason?: string | null
  refreshBusy?: boolean
  onPrevImage?: () => void
  onNextImage?: () => void
  canPrevImage?: boolean
  canNextImage?: boolean
  searchDisabled?: boolean
  searchPlaceholder?: string
  onUploadClick?: () => void
  uploadBusy?: boolean
  uploadDisabled?: boolean
  themePreset: ThemePresetId
  onThemePresetChange: (themeId: ThemePresetId) => void
  autoloadImageMetadata: boolean
  onAutoloadImageMetadataChange: (enabled: boolean) => void
  compareOrderMode: CompareOrderMode
  onCompareOrderModeChange: (mode: CompareOrderMode) => void
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
  onRefreshRoot,
  refreshEnabled = true,
  refreshDisabledReason,
  refreshBusy = false,
  onPrevImage,
  onNextImage,
  canPrevImage,
  canNextImage,
  searchDisabled = false,
  searchPlaceholder,
  onUploadClick,
  uploadBusy = false,
  uploadDisabled = false,
  themePreset,
  onThemePresetChange,
  autoloadImageMetadata,
  onAutoloadImageMetadataChange,
  compareOrderMode,
  onCompareOrderModeChange,
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
  const showMobileDrawer = isNarrow && !viewerActive
  const isCompactViewer = Boolean(viewerActive) && isToolbarCompact
  const sortSlotsVisible = !isCompactViewer
  const showToolbarNav = !!viewerActive && !isPhone
  const showBackButton = Boolean(viewerActive && onBack)
  const showRefreshButton = Boolean(!viewerActive && onRefreshRoot)
  const showUploadButton = Boolean(!viewerActive && onUploadClick)
  const showDesktopSearch = Boolean(!viewerActive && !isNarrow)
  const showNarrowSearchControls = Boolean(!viewerActive && isNarrow)
  const showNarrowSearchToggle = showNarrowSearchControls
  const showMobileSearchRow = showNarrowSearchControls
  const mobileSearchInteractive = showMobileSearchRow && mobileSearchOpen && !searchDisabled

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
    if (!filtersOpen) return
    if (!sortSlotsVisible || viewerActive) {
      setFiltersOpen(false)
    }
  }, [filtersOpen, sortSlotsVisible, viewerActive])

  useEffect(() => {
    if (searchDisabled || !showMobileSearchRow) {
      setMobileSearchOpen(false)
      return
    }
    if (!mobileSearchOpen) return
    const handle = window.requestAnimationFrame(() => searchInputRef.current?.focus())
    return () => window.cancelAnimationFrame(handle)
  }, [mobileSearchOpen, searchDisabled, showMobileSearchRow])

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

  const showSelectModeToggle = showMobileDrawer && !!onToggleMultiSelectMode
  const refreshButtonDisabled = refreshBusy || !refreshEnabled || !onRefreshRoot
  const refreshButtonTitle = refreshBusy
    ? 'Refreshing root folder…'
    : (refreshEnabled ? 'Refresh root folder' : (refreshDisabledReason || 'Refresh unavailable in current mode'))
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
        <div className="toolbar-sort flex items-center gap-2">
          <div
            className={`toolbar-sort-controls flex items-center gap-2 ${sortSlotsVisible ? '' : 'toolbar-control-hidden'}`}
            aria-hidden={!sortSlotsVisible}
          >
            <Dropdown
              value={currentSort}
              onChange={handleSortLayoutChange}
              options={sortOptions}
              title="Sort and layout options"
              aria-label="Sort and layout"
              triggerClassName="toolbar-sort-trigger min-w-[110px]"
              disabled={sortControlsDisabled || !sortSlotsVisible}
            />
            <button
              className="toolbar-sort-dir btn btn-icon"
              onClick={handleSortDirToggle}
              title={sortDisabled ? 'Sorting disabled' : (isRandom ? 'Shuffle' : `Sort ${sortDir === 'desc' ? 'descending' : 'ascending'}`)}
              aria-label={isRandom ? 'Shuffle' : 'Toggle sort direction'}
              aria-disabled={sortControlsDisabled || !sortSlotsVisible}
              aria-hidden={!sortSlotsVisible}
              disabled={sortControlsDisabled || !sortSlotsVisible}
              tabIndex={sortSlotsVisible ? 0 : -1}
            >
              <SortDirectionIcon isRandom={isRandom} dir={sortDir} />
            </button>
          </div>
          <ToolbarFilterMenu
            viewerActive={Boolean(viewerActive)}
            suppressed={!sortSlotsVisible}
            filtersOpen={filtersOpen}
            filtersRef={filtersRef}
            totalFilterCount={totalFilterCount}
            filterCount={filterCount}
            starFilterList={starFilterList}
            starCounts={starCounts}
            onToggleFilters={() => {
              if (!sortSlotsVisible || viewerActive) return
              setFiltersOpen((value) => !value)
            }}
            onOpenFilters={onOpenFilters}
            onToggleStar={onToggleStar}
            onClearFilters={onClearFilters}
            onClearStars={onClearStars}
          />
          <div className="toolbar-slot toolbar-slot-refresh" data-toolbar-slot="refresh">
            <button
              data-toolbar-control="refresh"
              className={`btn btn-icon ml-1 ${showRefreshButton ? '' : 'toolbar-control-hidden'} ${refreshButtonDisabled ? 'opacity-50 cursor-not-allowed' : ''}`}
              title={refreshButtonTitle}
              onClick={() => {
                if (!showRefreshButton || refreshButtonDisabled) return
                onRefreshRoot?.()
              }}
              aria-label="Refresh root folder"
              aria-disabled={!showRefreshButton || refreshButtonDisabled}
              aria-hidden={!showRefreshButton}
              disabled={!showRefreshButton || refreshButtonDisabled}
              tabIndex={showRefreshButton ? 0 : -1}
            >
              <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round" aria-hidden="true">
                <path d="M21 12a9 9 0 1 1-2.64-6.36" />
                <path d="M21 3v6h-6" />
              </svg>
            </button>
          </div>
        </div>
        <div className="toolbar-slot toolbar-slot-back" data-toolbar-slot="back">
          <button
            data-toolbar-control="back"
            className={`toolbar-back-btn btn btn-sm ${showBackButton ? '' : 'toolbar-control-hidden'}`}
            onClick={() => {
              if (!showBackButton) return
              onBack?.()
            }}
            title="Back to grid"
            aria-label="Back to grid"
            aria-hidden={!showBackButton}
            disabled={!showBackButton}
            tabIndex={showBackButton ? 0 : -1}
          >
            <svg width="12" height="12" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
              <path d="M15 18l-6-6 6-6" />
            </svg>
            <span className="toolbar-back-label">Back</span>
          </button>
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
        <div className="toolbar-slot toolbar-slot-nav" data-toolbar-slot="nav">
          <div className={`toolbar-nav flex items-center gap-1 ${showToolbarNav ? '' : 'toolbar-control-hidden'}`} aria-hidden={!showToolbarNav}>
            <button
              className={`btn btn-icon ${canPrevImage ? '' : 'opacity-40 cursor-not-allowed'}`}
              title="Previous image (A / ←)"
              onClick={() => showToolbarNav && canPrevImage && onPrevImage?.()}
              aria-label="Previous image"
              aria-disabled={!showToolbarNav || !canPrevImage}
              disabled={!showToolbarNav || !canPrevImage}
              tabIndex={showToolbarNav ? 0 : -1}
            >
              <svg width="12" height="12" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
                <path d="M15 18l-6-6 6-6" />
              </svg>
            </button>
            <button
              className={`btn btn-icon ${canNextImage ? '' : 'opacity-40 cursor-not-allowed'}`}
              title="Next image (D / →)"
              onClick={() => showToolbarNav && canNextImage && onNextImage?.()}
              aria-label="Next image"
              aria-disabled={!showToolbarNav || !canNextImage}
              disabled={!showToolbarNav || !canNextImage}
              tabIndex={showToolbarNav ? 0 : -1}
            >
              <svg width="12" height="12" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
                <path d="M9 6l6 6-6 6" />
              </svg>
            </button>
          </div>
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
        <div className="toolbar-slot toolbar-slot-upload" data-toolbar-slot="upload">
          <button
            data-toolbar-control="upload"
            className={`btn toolbar-upload-btn ${showUploadButton ? '' : 'toolbar-control-hidden'} ${(uploadDisabled || uploadBusy) ? 'opacity-50 cursor-not-allowed' : ''}`}
            onClick={() => showUploadButton && !uploadDisabled && !uploadBusy && onUploadClick?.()}
            aria-label="Upload images"
            title={uploadBusy ? 'Uploading…' : 'Upload images'}
            aria-disabled={!showUploadButton || uploadDisabled || uploadBusy}
            aria-hidden={!showUploadButton}
            disabled={!showUploadButton || uploadDisabled || uploadBusy}
            tabIndex={showUploadButton ? 0 : -1}
          >
            <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round" aria-hidden="true">
              <path d="M12 16V5" />
              <path d="M7 10l5-5 5 5" />
              <path d="M4 19h16" />
            </svg>
            <span className="toolbar-upload-label">{uploadBusy ? 'Uploading…' : 'Upload'}</span>
          </button>
        </div>
        {syncIndicator && (
          <SyncIndicator
            {...syncIndicator}
            isNarrow={isNarrow || isToolbarCompact}
          />
        )}
        {isNarrow && (
          <div className="toolbar-slot toolbar-slot-search-toggle" data-toolbar-slot="search-toggle">
            <button
              data-toolbar-control="search-toggle"
              className={`btn btn-icon ${showNarrowSearchToggle ? '' : 'toolbar-control-hidden'} ${mobileSearchOpen ? 'btn-active' : ''} ${searchDisabled ? 'opacity-50 cursor-not-allowed' : ''}`}
              aria-label={mobileSearchOpen ? 'Close search' : 'Open search'}
              title={searchDisabled ? 'Search disabled' : (mobileSearchOpen ? 'Close search' : 'Search')}
              onClick={() => showNarrowSearchToggle && !searchDisabled && setMobileSearchOpen((prev) => !prev)}
              disabled={!showNarrowSearchToggle || searchDisabled}
              aria-hidden={!showNarrowSearchToggle}
              tabIndex={showNarrowSearchToggle ? 0 : -1}
            >
              <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round" aria-hidden="true">
                <circle cx="11" cy="11" r="7" />
                <path d="M21 21l-4.35-4.35" />
              </svg>
            </button>
          </div>
        )}
        {!isNarrow ? (
          <div className="toolbar-slot toolbar-slot-search-desktop" data-toolbar-slot="search-desktop">
            <div className={`toolbar-search toolbar-search-desktop w-[240px] ${showDesktopSearch ? '' : 'toolbar-control-hidden'}`}>
              <input
                data-toolbar-control="search-desktop"
                ref={searchInputRef}
                aria-label="Search filename, tags, notes"
                placeholder={searchDisabled ? (searchPlaceholder ?? 'Search disabled') : 'Search...'}
                onChange={(e) => onSearch(e.target.value)}
                className="toolbar-search-input input w-full focus:w-full transition-all duration-200 select-text"
                disabled={!showDesktopSearch || searchDisabled}
                tabIndex={showDesktopSearch ? 0 : -1}
                aria-hidden={!showDesktopSearch}
              />
            </div>
          </div>
        ) : null}
      </div>
      {showMobileSearchRow && (
        <div
          className={`toolbar-search-row ${mobileSearchInteractive ? 'toolbar-search-row-active' : 'toolbar-search-row-hidden'}`}
          data-toolbar-slot="search-row"
          aria-hidden={!mobileSearchInteractive}
        >
            <input
              data-toolbar-control="search-mobile"
              ref={searchInputRef}
              aria-label="Search filename, tags, notes"
              aria-hidden={!mobileSearchInteractive}
              placeholder={searchPlaceholder ?? 'Search...'}
              onChange={(e) => onSearch(e.target.value)}
              className={`toolbar-search-input-mobile input input-lg w-full select-text ${mobileSearchInteractive ? '' : 'toolbar-control-hidden'}`}
              disabled={!mobileSearchInteractive}
              tabIndex={mobileSearchInteractive ? 0 : -1}
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
          themePreset={themePreset}
          autoloadImageMetadata={autoloadImageMetadata}
          compareOrderMode={compareOrderMode}
          onViewMode={onViewMode}
          onSortChange={(value) => onSortChange?.(parseSort(value, effectiveSort))}
          onToggleSortDir={handleSortDirToggle}
          onToggleMultiSelectMode={onToggleMultiSelectMode}
          onUploadClick={onUploadClick}
          onThemePresetChange={onThemePresetChange}
          onAutoloadImageMetadataChange={onAutoloadImageMetadataChange}
          onCompareOrderModeChange={onCompareOrderModeChange}
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
