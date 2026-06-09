import React, { useMemo } from 'react'
import type { FilterAST, BrowseFacetsPayload, BrowseItemPayload, DerivedMetricSpec, MetricDisplayNames } from '../../lib/types'
import AttributesPanel from './components/AttributesPanel'
import CategoricalPanel from './components/CategoricalPanel'
import DerivedScoreCard from './components/DerivedScoreCard'
import MetricRangePanel from './components/MetricRangePanel'
import { formatNumber, type Range } from './model/histogram'
import {
  collectMetricValuesByKey,
  type MetricValuesByKey,
} from './model/metricValues'
import type { DerivedMetricEvaluation } from './model/derivedMetric'
import { getMetricDisplayName } from '../../lib/metricDisplay'

interface MetricsPanelProps {
  items: BrowseItemPayload[]
  filteredItems: BrowseItemPayload[]
  metricKeys: string[]
  categoricalKeys: string[]
  metricDisplayNames?: MetricDisplayNames | null
  facets?: BrowseFacetsPayload | null
  itemPopulationComplete?: boolean
  derivedMetric: DerivedMetricEvaluation
  derivedRankDisabledReason?: string | null
  selectedItems?: BrowseItemPayload[]
  selectedMetric?: string
  onSelectMetric: (key: string) => void
  onApplyDerivedMetric: (spec: DerivedMetricSpec | null) => void
  onRankByDerivedMetric: (spec: DerivedMetricSpec) => void
  filters: FilterAST
  onChangeRange: (key: string, range: Range | null) => void
  onChangeCategoricalValues: (key: string, values: string[] | null) => void
  onChangeFilters: (filters: FilterAST) => void
}

interface SelectedMetricsPanelProps {
  selectedValuesByKey: MetricValuesByKey
  selectedItems: BrowseItemPayload[]
  totalItems: number
  metricKeys: string[]
  metricDisplayNames?: MetricDisplayNames | null
}

const MAX_SELECTED_METRICS = 12

export default function MetricsPanel({
  items,
  filteredItems,
  metricKeys,
  categoricalKeys,
  metricDisplayNames,
  facets = null,
  itemPopulationComplete = true,
  derivedMetric,
  derivedRankDisabledReason,
  selectedItems,
  selectedMetric,
  onSelectMetric,
  onApplyDerivedMetric,
  onRankByDerivedMetric,
  filters,
  onChangeRange,
  onChangeCategoricalValues,
  onChangeFilters,
}: MetricsPanelProps) {
  const selectedValuesByKey = useMemo(() => (
    selectedItems?.length ? collectMetricValuesByKey(selectedItems, metricKeys) : null
  ), [selectedItems, metricKeys])
  const metricsSummary = selectedValuesByKey && selectedItems && selectedItems.length
    ? (
      <SelectedMetricsPanel
        selectedValuesByKey={selectedValuesByKey}
        selectedItems={selectedItems}
        totalItems={selectedItems.length}
        metricKeys={metricKeys}
        metricDisplayNames={metricDisplayNames}
      />
    )
    : null
  const attributesPanel = (
    <AttributesPanel
      filters={filters}
      onChangeFilters={onChangeFilters}
    />
  )
  const categoricalValuesByKey = useMemo(
    () => categoricalValuesFromFacets(facets, categoricalKeys),
    [categoricalKeys, facets],
  )
  const categoricalPanel = (
    <CategoricalPanel
      items={items}
      filteredItems={filteredItems}
      categoricalKeys={categoricalKeys}
      facets={facets}
      itemPopulationComplete={itemPopulationComplete}
      selectedItems={selectedItems}
      filters={filters}
      onChangeValues={onChangeCategoricalValues}
    />
  )

  if (!metricKeys.length && !categoricalKeys.length) {
    return (
      <div className="h-full flex flex-col gap-3 p-3 overflow-auto scrollbar-thin">
        {metricsSummary}
        <DerivedScoreCard
          items={items}
          metricKeys={metricKeys}
          categoricalKeys={categoricalKeys}
          metricDisplayNames={metricDisplayNames}
          categoricalValuesByKey={categoricalValuesByKey}
          derivedMetric={derivedMetric}
          rankDisabledReason={derivedRankDisabledReason}
          onApplyDerivedMetric={onApplyDerivedMetric}
          onRankByDerivedMetric={onRankByDerivedMetric}
        />
        {attributesPanel}
        <div className="p-4 text-sm text-muted">
          No metrics or categoricals found in this dataset.
        </div>
      </div>
    )
  }

  return (
    <div className="h-full flex flex-col gap-3 p-3 overflow-auto scrollbar-thin">
      {metricsSummary}
      <DerivedScoreCard
        items={items}
        metricKeys={metricKeys}
        categoricalKeys={categoricalKeys}
        metricDisplayNames={metricDisplayNames}
        categoricalValuesByKey={categoricalValuesByKey}
        derivedMetric={derivedMetric}
        rankDisabledReason={derivedRankDisabledReason}
        onApplyDerivedMetric={onApplyDerivedMetric}
        onRankByDerivedMetric={onRankByDerivedMetric}
      />
      {metricKeys.length > 0 && (
        <MetricRangePanel
          items={items}
          filteredItems={filteredItems}
          metricKeys={metricKeys}
          metricDisplayNames={metricDisplayNames}
          facets={facets}
          itemPopulationComplete={itemPopulationComplete}
          selectedItems={selectedItems}
          selectedValuesByKey={selectedValuesByKey}
          selectedMetric={selectedMetric}
          onSelectMetric={onSelectMetric}
          filters={filters}
          onChangeRange={onChangeRange}
        />
      )}
      {categoricalPanel}
      {attributesPanel}
    </div>
  )
}

function categoricalValuesFromFacets(
  facets: BrowseFacetsPayload | null,
  categoricalKeys: readonly string[],
): Map<string, string[]> | undefined {
  if (!facets) return undefined
  return new Map(categoricalKeys.map((key) => [
    key,
    (facets.categoricals[key]?.values ?? []).map((entry) => entry.value),
  ]))
}

function SelectedMetricsPanel({
  selectedValuesByKey,
  selectedItems,
  totalItems,
  metricKeys,
  metricDisplayNames,
}: SelectedMetricsPanelProps) {
  const summary = useMemo(() => {
    if (!selectedValuesByKey.size) return null
    const keys = metricKeys.length
      ? metricKeys.filter((key) => selectedValuesByKey.has(key))
      : Array.from(selectedValuesByKey.keys()).sort()
    const entries = keys.map((key) => {
      const categorySummary = selectedCategorySummary(selectedItems, key)
      if (categorySummary) {
        return { key, text: categorySummary, count: selectedValuesByKey.get(key)?.length ?? 0 }
      }
      const values = selectedValuesByKey.get(key) ?? []
      const min = Math.min(...values)
      const max = Math.max(...values)
      const avg = values.reduce((sum, v) => sum + v, 0) / Math.max(1, values.length)
      return { key, value: values[0], min, max, avg, count: values.length }
    })
    return { entries, totalItems }
  }, [selectedValuesByKey, selectedItems, metricKeys, totalItems])

  if (!summary) return null

  const { entries, totalItems: summaryTotalItems } = summary
  const show = entries.slice(0, MAX_SELECTED_METRICS)
  const remaining = entries.length - show.length
  const isMulti = summaryTotalItems > 1

  return (
    <div className="ui-card">
      <div className="ui-card-header">
        <div className="ui-section-title">Selected metrics</div>
        <div className="text-[11px] text-muted">{summaryTotalItems} item{summaryTotalItems === 1 ? '' : 's'}</div>
      </div>
      <div className="space-y-1 text-[12px]">
        {show.map((entry) => (
          <div key={entry.key} className="flex flex-wrap items-baseline justify-between gap-x-2 gap-y-0.5 min-w-0">
            <span className="text-muted min-w-0 flex-1 basis-[7rem] truncate" title={getMetricDisplayName(entry.key, metricDisplayNames)}>
              {getMetricDisplayName(entry.key, metricDisplayNames)}
            </span>
            <span className="text-text text-right tabular-nums min-w-0 flex-1 basis-[6rem] whitespace-normal break-words">
              {'text' in entry ? entry.text : isMulti ? `${formatNumber(entry.min)} – ${formatNumber(entry.max)}` : formatNumber(entry.value)}
              {!('text' in entry) && isMulti && (
                <span className="text-[11px] text-muted ml-1 inline-block">
                  avg {formatNumber(entry.avg)}
                  {entry.count !== summaryTotalItems ? ` · ${entry.count}/${summaryTotalItems}` : ''}
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

function selectedCategorySummary(items: BrowseItemPayload[], key: string): string | null {
  const counts = new Map<string, number>()
  for (const item of items) {
    const label = item.metric_labels?.[key]
    if (!label) continue
    counts.set(label, (counts.get(label) ?? 0) + 1)
  }
  if (!counts.size) return null
  return Array.from(counts.entries())
    .sort(([a], [b]) => a.localeCompare(b))
    .map(([label, count]) => count > 1 ? `${label} (${count})` : label)
    .join(', ')
}
