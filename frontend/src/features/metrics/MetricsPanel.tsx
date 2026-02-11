import React, { useMemo } from 'react'
import type { FilterAST, Item } from '../../lib/types'
import AttributesPanel from './components/AttributesPanel'
import MetricRangePanel from './components/MetricRangePanel'
import { formatNumber, type Range } from './model/histogram'

// S0/T1 seam anchors (see docs/dev_notes/20260211_s0_t1_seam_map.md):
// - T20 component split: MetricsPanel composition + features/metrics/components/*.
// - T21 histogram math extraction: computeHistogramFromValues and numeric helpers in MetricHistogramCard.
// - T22 interaction hook extraction: drag/hover/edit state in MetricHistogramCard.
// - T23 optimization seam: histogram reuse across population/filtered/selected computations.

interface MetricsPanelProps {
  items: Item[]
  filteredItems: Item[]
  metricKeys: string[]
  selectedItems?: Item[]
  selectedMetric?: string
  onSelectMetric: (key: string) => void
  filters: FilterAST
  onChangeRange: (key: string, range: Range | null) => void
  onChangeFilters: (filters: FilterAST) => void
}

interface SelectedMetricsPanelProps {
  selectedItems: Item[]
  metricKeys: string[]
}

const MAX_SELECTED_METRICS = 12

export default function MetricsPanel({
  items,
  filteredItems,
  metricKeys,
  selectedItems,
  selectedMetric,
  onSelectMetric,
  filters,
  onChangeRange,
  onChangeFilters,
}: MetricsPanelProps) {
  const metricsSummary = selectedItems && selectedItems.length
    ? (
      <SelectedMetricsPanel
        selectedItems={selectedItems}
        metricKeys={metricKeys}
      />
    )
    : null
  const attributesPanel = (
    <AttributesPanel
      filters={filters}
      onChangeFilters={onChangeFilters}
    />
  )

  if (!metricKeys.length) {
    return (
      <div className="h-full flex flex-col gap-3 p-3 overflow-auto scrollbar-thin">
        {metricsSummary}
        {attributesPanel}
        <div className="p-4 text-sm text-muted">
          No metrics found in this dataset.
        </div>
      </div>
    )
  }

  return (
    <div className="h-full flex flex-col gap-3 p-3 overflow-auto scrollbar-thin">
      {metricsSummary}
      <MetricRangePanel
        items={items}
        filteredItems={filteredItems}
        metricKeys={metricKeys}
        selectedItems={selectedItems}
        selectedMetric={selectedMetric}
        onSelectMetric={onSelectMetric}
        filters={filters}
        onChangeRange={onChangeRange}
      />
      {attributesPanel}
    </div>
  )
}

function SelectedMetricsPanel({ selectedItems, metricKeys }: SelectedMetricsPanelProps) {
  const summary = useMemo(() => {
    if (!selectedItems.length) return null
    const valuesByKey = new Map<string, number[]>()
    for (const it of selectedItems) {
      const metrics = it.metrics
      if (!metrics) continue
      for (const [key, raw] of Object.entries(metrics)) {
        if (raw == null || Number.isNaN(raw)) continue
        const existing = valuesByKey.get(key)
        if (existing) existing.push(raw)
        else valuesByKey.set(key, [raw])
      }
    }
    if (!valuesByKey.size) return null
    const keys = metricKeys.length
      ? metricKeys.filter((key) => valuesByKey.has(key))
      : Array.from(valuesByKey.keys()).sort()
    const entries = keys.map((key) => {
      const values = valuesByKey.get(key) ?? []
      const min = Math.min(...values)
      const max = Math.max(...values)
      const avg = values.reduce((sum, v) => sum + v, 0) / Math.max(1, values.length)
      return { key, value: values[0], min, max, avg, count: values.length }
    })
    return { entries, totalItems: selectedItems.length }
  }, [selectedItems, metricKeys])

  if (!summary) return null

  const { entries, totalItems } = summary
  const show = entries.slice(0, MAX_SELECTED_METRICS)
  const remaining = entries.length - show.length
  const isMulti = totalItems > 1

  return (
    <div className="ui-card">
      <div className="ui-card-header">
        <div className="ui-section-title">Selected metrics</div>
        <div className="text-[11px] text-muted">{totalItems} item{totalItems === 1 ? '' : 's'}</div>
      </div>
      <div className="space-y-1 text-[12px]">
        {show.map((entry) => (
          <div key={entry.key} className="flex items-center justify-between gap-2">
            <span className="text-muted w-28 shrink-0 truncate" title={entry.key}>{entry.key}</span>
            <span className="font-mono text-text text-right tabular-nums">
              {isMulti ? `${formatNumber(entry.min)} – ${formatNumber(entry.max)}` : formatNumber(entry.value)}
              {isMulti && (
                <span className="text-[11px] text-muted ml-2">
                  avg {formatNumber(entry.avg)}
                  {entry.count !== totalItems ? ` · ${entry.count}/${totalItems}` : ''}
                </span>
              )}
            </span>
          </div>
        ))}
        {remaining > 0 && (
          <div className="text-[11px] text-muted">+{remaining} more</div>
        )}
      </div>
    </div>
  )
}
