import React from 'react'
import Dropdown, { type DropdownGroup } from '../Dropdown'
import SortDirectionIcon from './SortDirectionIcon'
import type { CompareOrderMode, TableSourceColumnsPayload, ViewMode } from '../../../lib/types'
import type { ThemePresetId } from '../../../theme/runtime'
import ThemeSettingsMenu from '../ThemeSettingsMenu'
import ToolbarFilterMenu from './ToolbarFilterMenu'

export interface ToolbarMobileDrawerProps {
  viewMode?: ViewMode
  currentSort: string
  sortOnlyOptions: DropdownGroup[]
  sortDisabled: boolean
  sortControlsDisabled: boolean
  sortDir: 'asc' | 'desc'
  isRandom: boolean
  showSelectModeToggle: boolean
  multiSelectMode: boolean
  selectModeLabel: string
  uploadBusy: boolean
  uploadDisabled: boolean
  themePreset: ThemePresetId
  autoloadImageMetadata: boolean
  compareOrderMode: CompareOrderMode
  sourceColumns?: TableSourceColumnsPayload | null
  sourceColumnSwitching?: boolean
  filtersOpen: boolean
  filtersRef: React.RefObject<HTMLDivElement>
  totalFilterCount: number
  filterCount?: number
  starsInFilterList: number[]
  starCounts?: { [k: string]: number }
  refreshEnabled: boolean
  refreshDisabledReason?: string | null
  refreshBusy: boolean
  leftOpen?: boolean
  rightOpen?: boolean
  onViewMode?: (value: ViewMode) => void
  onSortChange?: (value: string) => void
  onToggleSortDir: () => void
  onToggleFilters: () => void
  onOpenFilters?: () => void
  onToggleStarsIn?: (value: number) => void
  onClearFilters?: () => void
  onClearStarsIn?: () => void
  onRefreshRoot?: () => void
  onToggleLeft?: () => void
  onToggleRight?: () => void
  onToggleMultiSelectMode?: () => void
  onUploadClick?: () => void
  onThemePresetChange: (themeId: ThemePresetId) => void
  onAutoloadImageMetadataChange: (enabled: boolean) => void
  onCompareOrderModeChange: (mode: CompareOrderMode) => void
  onSourceColumnChange?: (sourceColumn: string) => void
}

export default function ToolbarMobileDrawer({
  viewMode,
  currentSort,
  sortOnlyOptions,
  sortDisabled,
  sortControlsDisabled,
  sortDir,
  isRandom,
  showSelectModeToggle,
  multiSelectMode,
  selectModeLabel,
  uploadBusy,
  uploadDisabled,
  themePreset,
  autoloadImageMetadata,
  compareOrderMode,
  sourceColumns,
  sourceColumnSwitching,
  filtersOpen,
  filtersRef,
  totalFilterCount,
  filterCount,
  starsInFilterList,
  starCounts,
  refreshEnabled,
  refreshDisabledReason,
  refreshBusy,
  leftOpen,
  rightOpen,
  onViewMode,
  onSortChange,
  onToggleSortDir,
  onToggleFilters,
  onOpenFilters,
  onToggleStarsIn,
  onClearFilters,
  onClearStarsIn,
  onRefreshRoot,
  onToggleLeft,
  onToggleRight,
  onToggleMultiSelectMode,
  onUploadClick,
  onThemePresetChange,
  onAutoloadImageMetadataChange,
  onCompareOrderModeChange,
  onSourceColumnChange,
}: ToolbarMobileDrawerProps): JSX.Element {
  const canShowUpload = Boolean(onUploadClick)
  const refreshDisabled = refreshBusy || !refreshEnabled || !onRefreshRoot
  const refreshTitle = refreshBusy
    ? 'Refreshing root folder...'
    : (refreshEnabled ? 'Refresh root folder' : (refreshDisabledReason || 'Refresh unavailable in current mode'))

  return (
    <div className="mobile-drawer">
      <div className="mobile-drawer-row">
        <button
          data-toolbar-control="drawer-layout-grid"
          className={`mobile-pill ${viewMode === 'grid' ? 'is-active' : ''}`}
          onClick={() => onViewMode?.('grid')}
          aria-pressed={viewMode === 'grid'}
        >
          Grid
        </button>
        <button
          data-toolbar-control="drawer-layout-adaptive"
          className={`mobile-pill ${viewMode === 'adaptive' ? 'is-active' : ''}`}
          onClick={() => onViewMode?.('adaptive')}
          aria-pressed={viewMode === 'adaptive'}
        >
          Justified rows
        </button>
        <div className="mobile-drawer-theme" data-toolbar-control="drawer-theme">
          <ThemeSettingsMenu
            value={themePreset}
            onChange={onThemePresetChange}
            placement="mobile"
            autoloadImageMetadata={autoloadImageMetadata}
            onAutoloadImageMetadataChange={onAutoloadImageMetadataChange}
            compareOrderMode={compareOrderMode}
            onCompareOrderModeChange={onCompareOrderModeChange}
            sourceColumns={sourceColumns}
            sourceColumnSwitching={sourceColumnSwitching}
            onSourceColumnChange={onSourceColumnChange}
          />
        </div>
        <div className="mobile-drawer-sort-control" data-toolbar-control="drawer-sort">
          <Dropdown
            value={currentSort}
            onChange={(value) => onSortChange?.(value)}
            options={sortOnlyOptions}
            aria-label="Sort"
            triggerClassName="mobile-pill mobile-pill-dropdown"
            panelClassName="mobile-drawer-panel"
            disabled={sortDisabled}
          />
        </div>
        <button
          data-toolbar-control="drawer-sort-dir"
          className={`mobile-pill mobile-pill-icon ${sortControlsDisabled ? 'opacity-50 cursor-not-allowed' : ''}`}
          onClick={onToggleSortDir}
          title={sortDisabled ? 'Sorting disabled' : (isRandom ? 'Shuffle' : `Sort ${sortDir === 'desc' ? 'descending' : 'ascending'}`)}
          aria-label={isRandom ? 'Shuffle' : 'Toggle sort direction'}
          aria-disabled={sortControlsDisabled}
          disabled={sortControlsDisabled}
        >
          <SortDirectionIcon isRandom={isRandom} dir={sortDir} />
        </button>
        <ToolbarFilterMenu
          variant="drawer"
          dataToolbarControl="drawer-filters"
          viewerActive={false}
          filtersOpen={filtersOpen}
          filtersRef={filtersRef}
          totalFilterCount={totalFilterCount}
          filterCount={filterCount}
          starsInFilterList={starsInFilterList}
          starCounts={starCounts}
          onToggleFilters={onToggleFilters}
          onOpenFilters={onOpenFilters}
          onToggleStarsIn={onToggleStarsIn}
          onClearFilters={onClearFilters}
          onClearStarsIn={onClearStarsIn}
        />
        <button
          data-toolbar-control="drawer-refresh"
          className={`mobile-pill ${refreshDisabled ? 'opacity-50 cursor-not-allowed' : ''}`}
          title={refreshTitle}
          onClick={() => {
            if (refreshDisabled) return
            onRefreshRoot?.()
          }}
          aria-label="Refresh root folder"
          aria-disabled={refreshDisabled}
          disabled={refreshDisabled}
        >
          Refresh
        </button>
        <button
          data-toolbar-control="drawer-left-panel"
          className={`mobile-pill ${leftOpen ? 'is-active' : ''}`}
          title={leftOpen ? 'Hide left panel (Ctrl+B)' : 'Show left panel (Ctrl+B)'}
          onClick={onToggleLeft}
          aria-pressed={leftOpen}
          aria-label="Toggle left panel"
        >
          Left
        </button>
        <button
          data-toolbar-control="drawer-right-panel"
          className={`mobile-pill ${rightOpen ? 'is-active' : ''}`}
          title={rightOpen ? 'Hide right panel (Ctrl+Alt+B)' : 'Show right panel (Ctrl+Alt+B)'}
          onClick={onToggleRight}
          aria-pressed={rightOpen}
          aria-label="Toggle right panel"
        >
          Right
        </button>
        {showSelectModeToggle && (
          <button
            data-toolbar-control="drawer-select"
            className={`mobile-pill mobile-pill-select ${multiSelectMode ? 'is-active' : ''}`}
            onClick={() => onToggleMultiSelectMode?.()}
            aria-pressed={multiSelectMode}
            title={multiSelectMode ? 'Exit select mode' : 'Enter select mode'}
          >
            {selectModeLabel}
          </button>
        )}
        {canShowUpload && (
          <button
            data-toolbar-control="drawer-upload"
            className={`mobile-pill mobile-pill-upload ${uploadDisabled || uploadBusy ? 'opacity-50 cursor-not-allowed' : ''}`}
            onClick={() => !uploadDisabled && !uploadBusy && onUploadClick?.()}
            aria-label="Upload images"
            title={uploadBusy ? 'Uploading...' : 'Upload images'}
            aria-disabled={uploadDisabled || uploadBusy}
            disabled={uploadDisabled || uploadBusy}
          >
            {uploadBusy ? 'Uploading...' : 'Upload'}
          </button>
        )}
      </div>
    </div>
  )
}
