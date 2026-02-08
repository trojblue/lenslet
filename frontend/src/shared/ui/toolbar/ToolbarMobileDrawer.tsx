import React from 'react'
import Dropdown, { type DropdownGroup } from '../Dropdown'
import SortDirectionIcon from './SortDirectionIcon'
import type { ViewMode } from '../../../lib/types'

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
  onViewMode?: (value: ViewMode) => void
  onSortChange?: (value: string) => void
  onToggleSortDir: () => void
  onToggleMultiSelectMode?: () => void
  onUploadClick?: () => void
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
  onViewMode,
  onSortChange,
  onToggleSortDir,
  onToggleMultiSelectMode,
  onUploadClick,
}: ToolbarMobileDrawerProps): JSX.Element {
  return (
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
          onChange={(value) => onSortChange?.(value)}
          options={sortOnlyOptions}
          aria-label="Sort"
          triggerClassName="mobile-pill mobile-pill-dropdown"
          panelClassName="mobile-drawer-panel"
          disabled={sortDisabled}
        />
        <button
          className={`mobile-pill mobile-pill-icon ${sortControlsDisabled ? 'opacity-50 cursor-not-allowed' : ''}`}
          onClick={onToggleSortDir}
          title={sortDisabled ? 'Sorting disabled' : (isRandom ? 'Shuffle' : `Sort ${sortDir === 'desc' ? 'descending' : 'ascending'}`)}
          aria-label={isRandom ? 'Shuffle' : 'Toggle sort direction'}
          aria-disabled={sortControlsDisabled}
          disabled={sortControlsDisabled}
        >
          <SortDirectionIcon isRandom={isRandom} dir={sortDir} />
        </button>
        {showSelectModeToggle && (
          <button
            className={`mobile-pill ${multiSelectMode ? 'is-active' : ''}`}
            onClick={() => onToggleMultiSelectMode?.()}
            aria-pressed={multiSelectMode}
            title={multiSelectMode ? 'Exit select mode' : 'Enter select mode'}
          >
            {selectModeLabel}
          </button>
        )}
        {onUploadClick && (
          <button
            className={`mobile-pill ${uploadDisabled || uploadBusy ? 'opacity-50 cursor-not-allowed' : ''}`}
            onClick={() => !uploadDisabled && !uploadBusy && onUploadClick()}
            disabled={uploadDisabled || uploadBusy}
          >
            {uploadBusy ? 'Uploading…' : 'Upload'}
          </button>
        )}
      </div>
    </div>
  )
}
