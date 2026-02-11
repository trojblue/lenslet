import React, { useState } from 'react'
import type { FilterAST, Item } from '../../../lib/types'
import type { Range } from '../model/histogram'
import MetricHistogramCard from './MetricHistogramCard'

interface MetricRangePanelProps {
  items: Item[]
  filteredItems: Item[]
  metricKeys: string[]
  selectedItems?: Item[]
  selectedMetric?: string
  onSelectMetric: (key: string) => void
  filters: FilterAST
  onChangeRange: (key: string, range: Range | null) => void
}

export default function MetricRangePanel({
  items,
  filteredItems,
  metricKeys,
  selectedItems,
  selectedMetric,
  onSelectMetric,
  filters,
  onChangeRange,
}: MetricRangePanelProps) {
  const [showAll, setShowAll] = useState(false)
  const activeMetric = selectedMetric && metricKeys.includes(selectedMetric) ? selectedMetric : metricKeys[0]

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
              items={items}
              filteredItems={filteredItems}
              selectedItems={selectedItems}
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
            items={items}
            filteredItems={filteredItems}
            selectedItems={selectedItems}
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
