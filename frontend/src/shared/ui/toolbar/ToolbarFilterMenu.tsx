import React, { useCallback, useEffect, useLayoutEffect, useMemo, useRef, useState } from 'react'
import {
  getDropdownPanelPosition,
  getVisibleViewportBounds,
  subscribeVisibleViewportChanges,
} from '../../../lib/menuPosition'

const useIsomorphicLayoutEffect = typeof window === 'undefined' ? useEffect : useLayoutEffect

export interface ToolbarFilterMenuProps {
  viewerActive: boolean
  suppressed?: boolean
  variant?: 'toolbar' | 'drawer'
  dataToolbarControl?: string
  filtersOpen: boolean
  filtersRef: React.RefObject<HTMLDivElement>
  totalFilterCount: number
  filterCount?: number
  starsInFilterList: number[]
  starCounts?: { [k: string]: number }
  onToggleFilters: () => void
  onOpenFilters?: () => void
  onToggleStarsIn?: (value: number) => void
  onClearFilters?: () => void
  onClearStarsIn?: () => void
}

export default function ToolbarFilterMenu({
  viewerActive,
  suppressed = false,
  variant = 'toolbar',
  dataToolbarControl,
  filtersOpen,
  filtersRef,
  totalFilterCount,
  filterCount,
  starsInFilterList,
  starCounts,
  onToggleFilters,
  onOpenFilters,
  onToggleStarsIn,
  onClearFilters,
  onClearStarsIn,
}: ToolbarFilterMenuProps): JSX.Element {
  const controlsVisible = !suppressed
  const buttonDisabled = viewerActive || suppressed
  const hasActiveFilters = totalFilterCount > 0
  const isDrawer = variant === 'drawer'
  const triggerRef = useRef<HTMLButtonElement>(null)
  const panelRef = useRef<HTMLDivElement>(null)
  const [panelPosition, setPanelPosition] = useState({ x: 0, y: 0, ready: false })
  const buttonClassName = isDrawer
    ? `mobile-pill mobile-pill-filter ${hasActiveFilters ? 'is-active' : ''}`
    : `btn ${hasActiveFilters ? 'btn-active' : ''}`
  const updatePanelPosition = useCallback(() => {
    if (!filtersOpen || !controlsVisible || buttonDisabled) return
    const anchor = triggerRef.current
    const panel = panelRef.current
    if (!anchor || !panel) return
    const anchorRect = anchor.getBoundingClientRect()
    const panelRect = panel.getBoundingClientRect()
    const next = getDropdownPanelPosition({
      anchorRect,
      menuSize: {
        width: panelRect.width || 240,
        height: panelRect.height || panel.scrollHeight || 1,
      },
      viewport: getVisibleViewportBounds(),
      align: 'left',
      sideOffset: isDrawer ? 8 : 6,
    })
    setPanelPosition((prev) => (
      prev.ready && prev.x === next.x && prev.y === next.y
        ? prev
        : { x: next.x, y: next.y, ready: true }
    ))
  }, [buttonDisabled, controlsVisible, filtersOpen, isDrawer])

  useIsomorphicLayoutEffect(() => {
    if (!filtersOpen || !controlsVisible || buttonDisabled) {
      setPanelPosition({ x: 0, y: 0, ready: false })
      return
    }
    updatePanelPosition()
  }, [buttonDisabled, controlsVisible, filtersOpen, updatePanelPosition])

  useEffect(() => {
    if (!filtersOpen || !controlsVisible || buttonDisabled) return
    return subscribeVisibleViewportChanges(updatePanelPosition)
  }, [buttonDisabled, controlsVisible, filtersOpen, updatePanelPosition])

  const panelStyle = useMemo<React.CSSProperties>(() => ({
    position: 'fixed',
    left: panelPosition.x,
    top: panelPosition.y,
    width: 240,
    visibility: panelPosition.ready ? 'visible' : 'hidden',
  }), [panelPosition])

  return (
    <div
      ref={filtersRef}
      className={`toolbar-filter ${isDrawer ? 'toolbar-filter-drawer' : ''} relative ${controlsVisible ? '' : 'toolbar-control-hidden'} ${viewerActive ? 'opacity-40 pointer-events-none' : ''}`}
      aria-hidden={!controlsVisible}
    >
      <button
        ref={triggerRef}
        data-toolbar-control={dataToolbarControl}
        className={buttonClassName}
        onClick={() => {
          if (buttonDisabled) return
          onToggleFilters()
        }}
        aria-haspopup="dialog"
        aria-expanded={filtersOpen}
        title="Filters"
        aria-disabled={buttonDisabled}
        aria-hidden={!controlsVisible}
        disabled={buttonDisabled}
        tabIndex={controlsVisible ? 0 : -1}
      >
        <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
          <polygon points="22 3 2 3 10 12.46 10 19 14 21 14 12.46 22 3" />
        </svg>
        <span className="toolbar-filters-label">Filters</span>
        <span
          className={`toolbar-filters-count px-1.5 py-0.5 text-[11px] rounded-full bg-accent-strong text-text ${hasActiveFilters ? '' : 'toolbar-filters-count-hidden'}`}
          aria-hidden={!hasActiveFilters}
        >
          {hasActiveFilters ? totalFilterCount : '0'}
        </span>
      </button>

      {filtersOpen && controlsVisible && !buttonDisabled && (
        <div
          ref={panelRef}
          role="dialog"
          aria-label="Filters"
          className={`dropdown-panel w-[240px] ${isDrawer ? 'mobile-drawer-panel' : ''}`}
          style={panelStyle}
        >
          <div className="dropdown-label">Rating</div>
          <div className="px-1">
            {[5, 4, 3, 2, 1].map((value) => {
              const active = starsInFilterList.includes(value)
              const count = starCounts?.[String(value)] ?? 0
              return (
                <button
                  key={value}
                  onClick={() => onToggleStarsIn?.(value)}
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
              onClick={() => onToggleStarsIn?.(0)}
              className={`dropdown-item justify-between ${starsInFilterList.includes(0) ? 'bg-accent-muted' : ''}`}
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
                onClearStarsIn?.()
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
