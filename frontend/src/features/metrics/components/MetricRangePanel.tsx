import React, { useMemo, useState } from 'react'
import type { FilterAST, BrowseFacetsPayload, BrowseItemPayload, MetricDisplayNames } from '../../../lib/types'
import { getMetricDisplayName } from '../../../lib/metricDisplay'
import type { Range } from '../model/histogram'
import {
  collectMetricCategoriesByKey,
  collectMetricCategoriesFromFacets,
  collectMetricValuesByKey,
  getMetricCategories,
  getMetricValues,
  metricHistogramFromFacet,
  type MetricValuesByKey,
} from '../model/metricValues'
import MetricCategoryCard from './MetricCategoryCard'
import MetricHistogramCard from './MetricHistogramCard'

interface MetricRangePanelProps {
  items: BrowseItemPayload[]
  filteredItems: BrowseItemPayload[]
  metricKeys: string[]
  metricDisplayNames?: MetricDisplayNames | null
  facets?: BrowseFacetsPayload | null
  itemPopulationComplete?: boolean
  selectedItems?: BrowseItemPayload[]
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
  metricDisplayNames,
  facets = null,
  itemPopulationComplete = true,
  selectedItems,
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
    () => itemPopulationComplete ? collectMetricValuesByKey(items, scopedMetricKeys) : EMPTY_VALUES_BY_KEY,
    [itemPopulationComplete, items, scopedMetricKeys]
  )
  const filteredValuesByKey = useMemo(
    () => collectMetricValuesByKey(filteredItems, scopedMetricKeys),
    [filteredItems, scopedMetricKeys]
  )
  const categoriesByKey = useMemo(
    () => {
      if (facets) {
        return collectMetricCategoriesFromFacets(
          facets,
          filteredItems,
          selectedItems,
          scopedMetricKeys,
          itemPopulationComplete,
        )
      }
      if (!itemPopulationComplete) return new Map()
      return collectMetricCategoriesByKey(items, filteredItems, selectedItems, scopedMetricKeys)
    },
    [facets, filteredItems, itemPopulationComplete, items, selectedItems, scopedMetricKeys]
  )
  const selectedValues = selectedValuesByKey ?? EMPTY_VALUES_BY_KEY

  const renderMetricCard = (key: string, showTitle = false) => {
    const categories = getMetricCategories(categoriesByKey, key)
    const metricFacet = facets?.metrics[key] ?? null
    const facetHistogram = metricHistogramFromFacet(metricFacet?.histogram)
    const showFilteredCounts = itemPopulationComplete
    if (categories.length) {
      return (
        <MetricCategoryCard
          key={key}
          metricKey={key}
          metricLabel={getMetricDisplayName(key, metricDisplayNames)}
          categories={categories}
          filters={filters}
          onChangeRange={onChangeRange}
          showTitle={showTitle}
          showFilteredCounts={showFilteredCounts}
        />
      )
    }
    return (
      <MetricHistogramCard
        key={key}
        metricKey={key}
        metricLabel={getMetricDisplayName(key, metricDisplayNames)}
        populationValues={facets ? [] : getMetricValues(populationValuesByKey, key)}
        filteredValues={showFilteredCounts ? getMetricValues(filteredValuesByKey, key) : []}
        populationHistogram={facetHistogram}
        selectedValues={getMetricValues(selectedValues, key)}
        filters={filters}
        onChangeRange={onChangeRange}
        showTitle={showTitle}
        showFilteredCounts={showFilteredCounts}
      />
    )
  }

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
              <option key={key} value={key}>{getMetricDisplayName(key, metricDisplayNames)}</option>
            ))}
          </select>
        )}
      </div>

      {showAll ? (
        <div className="space-y-3">
          {metricKeys.map((key) => renderMetricCard(key, true))}
        </div>
      ) : (
        activeMetric ? (
          renderMetricCard(activeMetric)
        ) : (
          <div className="text-sm text-muted">No values found for this metric.</div>
        )
      )}
    </>
  )
}
