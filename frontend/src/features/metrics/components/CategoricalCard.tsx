import React from 'react'
import type { FilterAST } from '../../../lib/types'
import { getCategoricalInFilter } from '../../browse/model/filters'
import type { CategoricalBucket } from '../model/categoricalValues'
import type { FacetFieldState } from '../model/facetPresentation'

interface CategoricalCardProps {
  categoricalKey: string
  buckets: CategoricalBucket[]
  filters: FilterAST
  onChangeValues: (key: string, values: string[] | null) => void
  showTitle?: boolean
  showFilteredCounts?: boolean
  state?: FacetFieldState
}

export default function CategoricalCard({
  categoricalKey,
  buckets,
  filters,
  onChangeValues,
  showTitle = false,
  showFilteredCounts = true,
  state = 'ready',
}: CategoricalCardProps) {
  const activeValues = getCategoricalInFilter(filters, categoricalKey)
  const activeSet = new Set(activeValues)
  const populationCount = buckets.reduce((sum, bucket) => sum + bucket.populationCount, 0)
  const filteredCount = buckets.reduce((sum, bucket) => sum + bucket.filteredCount, 0)
  const selectedCount = buckets.reduce((sum, bucket) => sum + bucket.selectedCount, 0)

  const displayState = buckets.length ? 'ready' : state === 'ready' ? 'empty' : state

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
    <div
      className="ui-card flex h-96 flex-col"
      data-categorical-card={categoricalKey}
      data-facet-state={displayState}
    >
      {showTitle && <div className="ui-section-title mb-2">{categoricalKey}</div>}
      <div className="flex h-4 shrink-0 items-center justify-between gap-2 text-[11px] text-muted mb-2 tabular-nums whitespace-nowrap">
        <div className="flex min-w-0 items-center gap-2 overflow-hidden">
          <span data-count-role="population">Population: {displayState === 'ready' ? populationCount : '—'}</span>
          <span data-count-role="filtered">
            Filtered: {showFilteredCounts && displayState === 'ready' ? filteredCount : '—'}
          </span>
        </div>
        <div className="flex shrink-0 items-center gap-2">
          <span
            className="w-20 truncate text-right text-text"
            title={`Selected: ${selectedCount}`}
            data-count-role="selected"
          >
            Selected: {selectedCount}
          </span>
          <span className="w-20 text-right" data-count-role="values">
            {displayState === 'ready'
              ? `${buckets.length} value${buckets.length === 1 ? '' : 's'}`
              : '— values'}
          </span>
        </div>
      </div>
      <div className="h-64 shrink-0 overflow-auto scrollbar-thin pr-1" data-facet-body>
        {displayState === 'ready' ? (
          <div className="space-y-1">
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
                    <span
                      className="flex w-32 shrink-0 items-center justify-end text-[11px] text-muted tabular-nums"
                      aria-label={`Selected ${bucket.selectedCount}; filtered ${showFilteredCounts ? bucket.filteredCount : 'not active'}; population ${bucket.populationCount}`}
                      title={`Selected: ${bucket.selectedCount}; Filtered: ${showFilteredCounts ? bucket.filteredCount : '—'}; Population: ${bucket.populationCount}`}
                    >
                      <span className="w-12 text-right" data-count-role="row-selected">
                        {bucket.selectedCount > 0 ? `${bucket.selectedCount} sel` : '—'}
                      </span>
                      <span className="w-4 text-center" aria-hidden="true">·</span>
                      <span className="w-16 text-right" data-count-role="row-filtered-population">
                        {showFilteredCounts ? bucket.filteredCount : '—'}/{bucket.populationCount}
                      </span>
                    </span>
                  </span>
                </button>
              )
            })}
          </div>
        ) : (
          <div className="flex h-full items-center justify-center px-3 text-center text-sm text-muted" role="status">
            {facetStateMessage(displayState, 'field')}
          </div>
        )}
      </div>
      <button
        className={`btn btn-xs btn-ghost text-muted hover:text-text mt-auto self-start ${activeValues.length ? '' : 'invisible'}`}
        onClick={() => onChangeValues(categoricalKey, null)}
        disabled={!activeValues.length}
        aria-hidden={!activeValues.length}
        data-card-action="clear"
      >
        Clear
      </button>
    </div>
  )
}

function facetStateMessage(state: Exclude<FacetFieldState, 'ready'>, subject: string): string {
  if (state === 'pending') return `Loading values for this ${subject}…`
  if (state === 'error') return `Could not load values for this ${subject}.`
  return `No values found for this ${subject}.`
}
