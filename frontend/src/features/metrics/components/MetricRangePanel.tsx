import React, { useMemo, useState } from 'react'
import type { FilterAST, Item } from '../../../lib/types'
import type { Range } from '../model/histogram'
import {
  collectMetricValuesByKey,
  getMetricValues,
  type MetricValuesByKey,
} from '../model/metricValues'
import MetricHistogramCard from './MetricHistogramCard'

interface MetricRangePanelProps {
  items: Item[]
  filteredItems: Item[]
  metricKeys: string[]
  selectedValuesByKey?: MetricValuesByKey | null
  selectedMetric?: string
  onSelectMetric: (key: string) => void
  filters: FilterAST
  onChangeRange: (key: string, range: Range | null) => void
}

const EMPTY_VALUES_BY_KEY: MetricValuesByKey = new Map()

export default function MetricRangePanel({
  items,
  filteredItems,
  metricKeys,
  selectedValuesByKey,
  selectedMetric,
  onSelectMetric,
  filters,
  onChangeRange,
}: MetricRangePanelProps) {
  const [showAll, setShowAll] = useState(false)
  const activeMetric = selectedMetric && metricKeys.includes(selectedMetric) ? selectedMetric : metricKeys[0]
  const scopedMetricKeys = useMemo(() => (
    showAll ? metricKeys : activeMetric ? [activeMetric] : []
  ), [showAll, metricKeys, activeMetric])
  const populationValuesByKey = useMemo(
    () => collectMetricValuesByKey(items, scopedMetricKeys),
    [items, scopedMetricKeys]
  )
  const filteredValuesByKey = useMemo(
    () => collectMetricValuesByKey(filteredItems, scopedMetricKeys),
    [filteredItems, scopedMetricKeys]
  )
  const selectedValues = selectedValuesByKey ?? EMPTY_VALUES_BY_KEY

  return (
    <>
      <div>
        <div className="flex items-center justify-between gap-2">
          <label className="ui-label">Metric</label>
          <button
            className="btn btn-sm btn-ghost text-[11px]"
            onClick={() => setShowAll((v) => !v)}
            aria-pressed={showAll}
          >
            {showAll ? 'Show one' : 'Show all'}
          </button>
        </div>
        {showAll ? (
          <div className="ui-input ui-input-readonly w-full flex items-center text-xs">
            All metrics
          </div>
        ) : (
          <select
            className="ui-select w-full"
            value={activeMetric}
            onChange={(e) => onSelectMetric(e.target.value)}
          >
            {metricKeys.map((key) => (
              <option key={key} value={key}>{key}</option>
            ))}
          </select>
        )}
      </div>

      {showAll ? (
        <div className="space-y-3">
          {metricKeys.map((key) => (
            <MetricHistogramCard
              key={key}
              metricKey={key}
              populationValues={getMetricValues(populationValuesByKey, key)}
              filteredValues={getMetricValues(filteredValuesByKey, key)}
              selectedValues={getMetricValues(selectedValues, key)}
              filters={filters}
              onChangeRange={onChangeRange}
              showTitle
            />
          ))}
        </div>
      ) : (
        activeMetric ? (
          <MetricHistogramCard
            metricKey={activeMetric}
            populationValues={getMetricValues(populationValuesByKey, activeMetric)}
            filteredValues={getMetricValues(filteredValuesByKey, activeMetric)}
            selectedValues={getMetricValues(selectedValues, activeMetric)}
            filters={filters}
            onChangeRange={onChangeRange}
          />
        ) : (
          <div className="text-sm text-muted">No values found for this metric.</div>
        )
      )}
    </>
  )
}
