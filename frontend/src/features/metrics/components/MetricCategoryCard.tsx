import React from 'react'
import type { FilterAST } from '../../../lib/types'
import { getMetricRangeFilter } from '../../browse/model/filters'
import type { Range } from '../model/histogram'
import type { MetricCategoryBucket } from '../model/metricValues'
import type { FacetFieldState } from '../model/facetPresentation'

interface MetricCategoryCardProps {
  metricKey: string
  metricLabel?: string
  categories: MetricCategoryBucket[]
  filters: FilterAST
  onChangeRange: (key: string, range: Range | null) => void
  showTitle?: boolean
  showFilteredCounts?: boolean
  state?: FacetFieldState
  embedded?: boolean
}

export default function MetricCategoryCard({
  metricKey,
  metricLabel,
  categories,
  filters,
  onChangeRange,
  showTitle = false,
  showFilteredCounts = true,
  state = 'ready',
  embedded = false,
}: MetricCategoryCardProps) {
  const activeRange = getMetricRangeFilter(filters, metricKey)
  const populationCount = categories.reduce((sum, category) => sum + category.populationCount, 0)
  const filteredCount = categories.reduce((sum, category) => sum + category.filteredCount, 0)
  const selectedCount = categories.reduce((sum, category) => sum + category.selectedCount, 0)

  const displayLabel = metricLabel ?? metricKey

  const displayState = categories.length ? 'ready' : state === 'ready' ? 'empty' : state

  return (
    <div
      className={embedded ? 'flex h-full flex-col' : 'ui-card flex h-96 flex-col'}
      data-metric-category-card={metricKey}
      data-facet-state={displayState}
    >
      {showTitle && <div className="ui-section-title mb-2">{displayLabel}</div>}
      <div className="flex h-4 shrink-0 items-center justify-between gap-2 text-[11px] text-muted mb-2 tabular-nums whitespace-nowrap">
        <div className="flex min-w-0 items-center gap-2 overflow-hidden">
          <span>Population: {displayState === 'ready' ? populationCount : '—'}</span>
          {showFilteredCounts && <span>Filtered: {displayState === 'ready' ? filteredCount : '—'}</span>}
        </div>
        <div className="flex shrink-0 items-center gap-2">
          <span
            className={`w-20 truncate text-right text-text ${selectedCount > 0 ? '' : 'invisible'}`}
            title={selectedCount > 0 ? `Selected: ${selectedCount}` : undefined}
            aria-hidden={selectedCount > 0 ? undefined : true}
          >
            Selected: {selectedCount || 0}
          </span>
          <span className="w-14 text-right">
            {displayState === 'ready' ? `${categories.length} class${categories.length === 1 ? '' : 'es'}` : ''}
          </span>
        </div>
      </div>
      <div className="h-64 shrink-0 overflow-auto scrollbar-thin pr-1" data-facet-body>
        {displayState === 'ready' ? (
          <div className="space-y-1">
            {categories.map((category) => {
              const active = activeRange ? categoryInRange(category.code, activeRange) : false
              const exact = activeRange ? categoryIsExact(category.code, activeRange) : false
              return (
                <button
                  key={`${category.code}:${category.label}`}
                  type="button"
                  className={`w-full min-w-0 rounded-md border px-2 py-1.5 text-left text-[12px] transition-colors ${
                    active
                      ? 'border-accent/70 bg-accent/20 text-text'
                      : 'border-border/60 bg-surface hover:border-border hover:bg-surface-hover'
                  }`}
                  title={category.label}
                  aria-pressed={active}
                  onClick={() => onChangeRange(metricKey, exact ? null : { min: category.code, max: category.code })}
                >
                  <span className="flex items-center justify-between gap-2 min-w-0">
                    <span className="truncate">{category.label}</span>
                    <span className="shrink-0 text-[11px] text-muted tabular-nums">
                      {category.selectedCount > 0 ? `${category.selectedCount} sel · ` : ''}
                      {showFilteredCounts ? `${category.filteredCount}/` : ''}{category.populationCount}
                    </span>
                  </span>
                </button>
              )
            })}
          </div>
        ) : (
          <div className="flex h-full items-center justify-center px-3 text-center text-sm text-muted" role="status">
            {displayState === 'pending'
              ? 'Loading values for this metric…'
              : displayState === 'error'
                ? 'Could not load values for this metric.'
                : 'No values found for this metric.'}
          </div>
        )}
      </div>
      <button
        className={`btn btn-xs btn-ghost text-muted hover:text-text mt-auto self-start ${activeRange ? '' : 'invisible'}`}
        onClick={() => onChangeRange(metricKey, null)}
        disabled={!activeRange}
        aria-hidden={!activeRange}
        data-card-action="clear"
      >
        Clear
      </button>
    </div>
  )
}

function categoryInRange(code: number, range: Range): boolean {
  return code >= range.min && code <= range.max
}

function categoryIsExact(code: number, range: Range): boolean {
  return code === range.min && code === range.max
}
