import React from 'react'
import type { FilterAST } from '../../../lib/types'
import { getCategoricalInFilter } from '../../browse/model/filters'
import type { CategoricalBucket } from '../model/categoricalValues'

interface CategoricalCardProps {
  categoricalKey: string
  buckets: CategoricalBucket[]
  filters: FilterAST
  onChangeValues: (key: string, values: string[] | null) => void
  showTitle?: boolean
}

export default function CategoricalCard({
  categoricalKey,
  buckets,
  filters,
  onChangeValues,
  showTitle = false,
}: CategoricalCardProps) {
  const activeValues = getCategoricalInFilter(filters, categoricalKey)
  const activeSet = new Set(activeValues)
  const populationCount = buckets.reduce((sum, bucket) => sum + bucket.populationCount, 0)
  const filteredCount = buckets.reduce((sum, bucket) => sum + bucket.filteredCount, 0)
  const selectedCount = buckets.reduce((sum, bucket) => sum + bucket.selectedCount, 0)

  if (!buckets.length) {
    return (
      <div className="ui-card">
        {showTitle && <div className="ui-section-title mb-2">{categoricalKey}</div>}
        <div className="text-sm text-muted">No values found for this field.</div>
      </div>
    )
  }

  const toggleValue = (value: string) => {
    const next = new Set(activeSet)
    if (next.has(value)) {
      next.delete(value)
    } else {
      next.add(value)
    }
    onChangeValues(categoricalKey, next.size ? Array.from(next) : null)
  }

  return (
    <div className="ui-card">
      {showTitle && <div className="ui-section-title mb-2">{categoricalKey}</div>}
      <div className="flex flex-wrap items-center justify-between gap-x-2 gap-y-1 text-[11px] text-muted mb-2 tabular-nums">
        <div className="flex min-w-0 flex-wrap items-center gap-x-2 gap-y-1">
          <span>Population: {populationCount}</span>
          <span>Filtered: {filteredCount}</span>
          {selectedCount > 0 && <span className="text-text">Selected: {selectedCount}</span>}
        </div>
        <span>{buckets.length} value{buckets.length === 1 ? '' : 's'}</span>
      </div>
      {activeValues.length > 0 && (
        <div className="mb-2 text-[11px] text-text min-w-0">
          <span className="text-muted">Active: </span>
          <span className="break-words">{activeValues.join(', ')}</span>
        </div>
      )}
      <div className="space-y-1 max-h-72 overflow-auto scrollbar-thin pr-1">
        {buckets.map((bucket) => {
          const active = activeSet.has(bucket.value)
          return (
            <button
              key={bucket.value}
              type="button"
              className={`w-full min-w-0 rounded-md border px-2 py-1.5 text-left text-[12px] transition-colors ${
                active
                  ? 'border-accent/70 bg-accent/20 text-text'
                  : 'border-border/60 bg-surface hover:border-border hover:bg-surface-hover'
              }`}
              title={bucket.value}
              aria-pressed={active}
              onClick={() => toggleValue(bucket.value)}
            >
              <span className="flex items-center justify-between gap-2 min-w-0">
                <span className="truncate">{bucket.value}</span>
                <span className="shrink-0 text-[11px] text-muted tabular-nums">
                  {bucket.filteredCount}/{bucket.populationCount}
                </span>
              </span>
              {bucket.selectedCount > 0 && (
                <span className="mt-0.5 block text-[11px] text-muted tabular-nums">
                  selected {bucket.selectedCount}
                </span>
              )}
            </button>
          )
        })}
      </div>
      {activeValues.length > 0 && (
        <button
          className="btn btn-xs btn-ghost text-muted hover:text-text mt-3"
          onClick={() => onChangeValues(categoricalKey, null)}
        >
          Clear
        </button>
      )}
    </div>
  )
}
