import React, { useCallback, useEffect, useMemo, useState } from 'react'
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
import Dropdown from '../../../shared/ui/Dropdown'
import MetricCategoryCard from './MetricCategoryCard'
import MetricHistogramCard from './MetricHistogramCard'
import VirtualFieldList from './VirtualFieldList'

interface MetricRangePanelProps {
  items: BrowseItemPayload[]
  filteredItems: BrowseItemPayload[]
  metricKeys: string[]
  metricDisplayNames?: MetricDisplayNames | null
  facets?: BrowseFacetsPayload | null
  populationItemsComplete?: boolean
  filteredItemsComplete?: boolean
  selectedItems?: BrowseItemPayload[]
  selectedValuesByKey?: MetricValuesByKey | null
  selectedMetric?: string
  onSelectMetric: (key: string) => void
  filters: FilterAST
  onChangeRange: (key: string, range: Range | null) => void
  onFacetFieldsChange?: (keys: string[]) => void
}

const EMPTY_VALUES_BY_KEY: MetricValuesByKey = new Map()

export default function MetricRangePanel({
  items,
  filteredItems,
  metricKeys,
  metricDisplayNames,
  facets = null,
  populationItemsComplete = true,
  filteredItemsComplete = true,
  selectedItems,
  selectedValuesByKey,
  selectedMetric,
  onSelectMetric,
  filters,
  onChangeRange,
  onFacetFieldsChange,
}: MetricRangePanelProps) {
  const [showAll, setShowAll] = useState(false)
  const [visibleMetricKeys, setVisibleMetricKeys] = useState<string[]>([])
  const activeMetric = selectedMetric && metricKeys.includes(selectedMetric) ? selectedMetric : metricKeys[0]
  const scopedMetricKeys = useMemo(() => (
    showAll ? visibleMetricKeys : activeMetric ? [activeMetric] : []
  ), [showAll, visibleMetricKeys, activeMetric])
  const populationValuesByKey = useMemo(
    () => populationItemsComplete ? collectMetricValuesByKey(items, scopedMetricKeys) : EMPTY_VALUES_BY_KEY,
    [items, populationItemsComplete, scopedMetricKeys]
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
          filteredItemsComplete,
        )
      }
      if (!populationItemsComplete) return new Map()
      return collectMetricCategoriesByKey(items, filteredItems, selectedItems, scopedMetricKeys)
    },
    [facets, filteredItems, filteredItemsComplete, items, populationItemsComplete, selectedItems, scopedMetricKeys]
  )
  const selectedValues = selectedValuesByKey ?? EMPTY_VALUES_BY_KEY
  const metricOptions = useMemo(() => (
    metricKeys.map((key) => ({
      value: key,
      label: getMetricDisplayName(key, metricDisplayNames),
      keywords: [key],
    }))
  ), [metricDisplayNames, metricKeys])

  useEffect(() => {
    if (!showAll) onFacetFieldsChange?.(activeMetric ? [activeMetric] : [])
  }, [activeMetric, onFacetFieldsChange, showAll])

  const handleVisibleKeysChange = useCallback((keys: string[]) => {
    setVisibleMetricKeys(keys)
    onFacetFieldsChange?.(keys)
  }, [onFacetFieldsChange])

  const renderMetricCard = (key: string, showTitle = false) => {
    const categories = getMetricCategories(categoriesByKey, key)
    const metricFacet = facets?.metrics[key] ?? null
    const facetHistogram = metricHistogramFromFacet(metricFacet?.histogram)
    const showFilteredCounts = filteredItemsComplete
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
            data-metric-show-all
          >
            {showAll ? 'Show one' : 'Show all'}
          </button>
        </div>
        {showAll ? (
          <div className="ui-input ui-input-readonly w-full flex items-center text-xs">
            All metrics
          </div>
        ) : (
          <div data-metric-selector>
            <Dropdown
              value={activeMetric ?? ''}
              onChange={onSelectMetric}
              options={metricOptions}
              aria-label="Metric"
              title={activeMetric ? getMetricDisplayName(activeMetric, metricDisplayNames) : 'Metric'}
              triggerClassName="w-full justify-between"
              width="trigger"
              searchable="auto"
              searchPlaceholder="Search metrics..."
              emptyMessage="No matching metrics"
            />
          </div>
        )}
      </div>

      {showAll ? (
        <VirtualFieldList
          keys={metricKeys}
          estimateSize={340}
          kind="metric"
          onVisibleKeysChange={handleVisibleKeysChange}
          renderCard={(key) => renderMetricCard(key, true)}
        />
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
