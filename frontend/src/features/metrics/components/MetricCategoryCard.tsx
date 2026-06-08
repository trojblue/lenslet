import React from 'react'
import type { FilterAST } from '../../../lib/types'
import { getMetricRangeFilter } from '../../browse/model/filters'
import type { Range } from '../model/histogram'
import type { MetricCategoryBucket } from '../model/metricValues'

interface MetricCategoryCardProps {
  metricKey: string
  metricLabel?: string
  categories: MetricCategoryBucket[]
  filters: FilterAST
  onChangeRange: (key: string, range: Range | null) => void
  showTitle?: boolean
}

export default function MetricCategoryCard({
  metricKey,
  metricLabel,
  categories,
  filters,
  onChangeRange,
  showTitle = false,
}: MetricCategoryCardProps) {
  const activeRange = getMetricRangeFilter(filters, metricKey)
  const activeCategories = activeRange
    ? categories.filter((category) => categoryInRange(category.code, activeRange))
    : []
  const populationCount = categories.reduce((sum, category) => sum + category.populationCount, 0)
  const filteredCount = categories.reduce((sum, category) => sum + category.filteredCount, 0)
  const selectedCount = categories.reduce((sum, category) => sum + category.selectedCount, 0)

  const displayLabel = metricLabel ?? metricKey

  if (!categories.length) {
    return (
      <div className="ui-card">
        {showTitle && <div className="ui-section-title mb-2">{displayLabel}</div>}
        <div className="text-sm text-muted">No values found for this metric.</div>
      </div>
    )
  }

  return (
    <div className="ui-card">
      {showTitle && <div className="ui-section-title mb-2">{displayLabel}</div>}
      <div className="flex flex-wrap items-center justify-between gap-x-2 gap-y-1 text-[11px] text-muted mb-2 tabular-nums">
        <div className="flex min-w-0 flex-wrap items-center gap-x-2 gap-y-1">
          <span>Population: {populationCount}</span>
          <span>Filtered: {filteredCount}</span>
          {selectedCount > 0 && <span className="text-text">Selected: {selectedCount}</span>}
        </div>
        <span>{categories.length} class{categories.length === 1 ? '' : 'es'}</span>
      </div>
      {activeCategories.length > 0 && (
        <div className="mb-2 text-[11px] text-text min-w-0">
          <span className="text-muted">Active: </span>
          <span className="break-words">{activeCategories.map((category) => category.label).join(', ')}</span>
        </div>
      )}
      <div className="space-y-1 max-h-72 overflow-auto scrollbar-thin pr-1">
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
                  {category.filteredCount}/{category.populationCount}
                </span>
              </span>
              {category.selectedCount > 0 && (
                <span className="mt-0.5 block text-[11px] text-muted tabular-nums">
                  selected {category.selectedCount}
                </span>
              )}
            </button>
          )
        })}
      </div>
      {activeRange && (
        <button
          className="btn btn-xs btn-ghost text-muted hover:text-text mt-3"
          onClick={() => onChangeRange(metricKey, null)}
        >
          Clear
        </button>
      )}
    </div>
  )
}

function categoryInRange(code: number, range: Range): boolean {
  return code >= range.min && code <= range.max
}

function categoryIsExact(code: number, range: Range): boolean {
  return code === range.min && code === range.max
}
