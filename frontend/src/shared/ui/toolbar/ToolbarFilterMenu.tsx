import React from 'react'

export interface ToolbarFilterMenuProps {
  viewerActive: boolean
  filtersOpen: boolean
  filtersRef: React.RefObject<HTMLDivElement>
  totalFilterCount: number
  filterCount?: number
  starFilterList: number[]
  starCounts?: { [k: string]: number }
  onToggleFilters: () => void
  onOpenFilters?: () => void
  onToggleStar?: (value: number) => void
  onClearFilters?: () => void
  onClearStars?: () => void
}

export default function ToolbarFilterMenu({
  viewerActive,
  filtersOpen,
  filtersRef,
  totalFilterCount,
  filterCount,
  starFilterList,
  starCounts,
  onToggleFilters,
  onOpenFilters,
  onToggleStar,
  onClearFilters,
  onClearStars,
}: ToolbarFilterMenuProps): JSX.Element {
  return (
    <div ref={filtersRef} className={`toolbar-filter relative ${viewerActive ? 'opacity-40 pointer-events-none' : ''}`}>
      <button
        className={`btn ${totalFilterCount > 0 ? 'btn-active' : ''}`}
        onClick={onToggleFilters}
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
          <div className="dropdown-label">Rating</div>
          <div className="px-1">
            {[5, 4, 3, 2, 1].map((value) => {
              const active = starFilterList.includes(value)
              const count = starCounts?.[String(value)] ?? 0
              return (
                <button
                  key={value}
                  onClick={() => onToggleStar?.(value)}
                  className={`dropdown-item justify-between ${active ? 'bg-accent-muted' : ''}`}
                >
                  <span className={active ? 'text-star-active' : 'text-text'}>
                    {'★'.repeat(value)}{'☆'.repeat(5 - value)}
                  </span>
                  <span className="text-xs text-muted">{count}</span>
                </button>
              )
            })}
            <button
              onClick={() => onToggleStar?.(0)}
              className={`dropdown-item justify-between ${starFilterList.includes(0) ? 'bg-accent-muted' : ''}`}
            >
              <span className="text-text">Unrated</span>
              <span className="text-xs text-muted">{starCounts?.['0'] ?? 0}</span>
            </button>
          </div>

          <div className="dropdown-divider" />

          <div className="dropdown-label">Metrics</div>
          <button
            className="dropdown-item"
            onClick={() => {
              onToggleFilters()
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
  )
}
