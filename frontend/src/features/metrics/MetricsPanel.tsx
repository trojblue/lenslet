import React, { useEffect, useMemo, useState } from 'react'
import type { BrowseFacetFields, FilterAST, BrowseFacetsPayload, BrowseItemPayload, MetricDisplayNames } from '../../lib/types'
import AttributesPanel from './components/AttributesPanel'
import CategoricalPanel from './components/CategoricalPanel'
import MetricRangePanel from './components/MetricRangePanel'
import type { Range } from './model/histogram'
import {
  collectMetricValuesByKey,
  type MetricValuesByKey,
} from './model/metricValues'
import type {
  FacetFieldQueryStates,
  FacetQueryState,
} from './model/facetPresentation'

interface MetricsPanelProps {
  items: BrowseItemPayload[]
  filteredItems: BrowseItemPayload[]
  metricKeys: string[]
  categoricalKeys: string[]
  metricDisplayNames?: MetricDisplayNames | null
  facets?: BrowseFacetsPayload | null
  facetsState?: FacetQueryState
  facetFieldStates?: FacetFieldQueryStates
  populationItemsComplete?: boolean
  filteredItemsComplete?: boolean
  selectedItems?: BrowseItemPayload[]
  selectedMetric?: string
  onSelectMetric: (key: string) => void
  filters: FilterAST
  onChangeRange: (key: string, range: Range | null) => void
  onChangeCategoricalValues: (key: string, values: string[] | null) => void
  onChangeFilters: (filters: FilterAST) => void
  onFacetFieldsChange?: (fields: BrowseFacetFields) => void
}

export default function MetricsPanel({
  items,
  filteredItems,
  metricKeys,
  categoricalKeys,
  metricDisplayNames,
  facets = null,
  facetsState = 'settled',
  facetFieldStates,
  populationItemsComplete = true,
  filteredItemsComplete = true,
  selectedItems,
  selectedMetric,
  onSelectMetric,
  filters,
  onChangeRange,
  onChangeCategoricalValues,
  onChangeFilters,
  onFacetFieldsChange,
}: MetricsPanelProps) {
  const [metricFacetKeys, setMetricFacetKeys] = useState<string[]>([])
  const [categoricalFacetKeys, setCategoricalFacetKeys] = useState<string[]>([])
  useEffect(() => {
    onFacetFieldsChange?.({
      metric_keys: metricFacetKeys,
      categorical_keys: categoricalFacetKeys,
    })
  }, [categoricalFacetKeys, metricFacetKeys, onFacetFieldsChange])
  const selectedValuesByKey = useMemo(() => (
    selectedItems?.length ? collectMetricValuesByKey(selectedItems, metricKeys) : null
  ), [selectedItems, metricKeys])
  const attributesPanel = (
    <AttributesPanel
      filters={filters}
      onChangeFilters={onChangeFilters}
    />
  )
  const categoricalPanel = (
    <CategoricalPanel
      items={items}
      filteredItems={filteredItems}
      categoricalKeys={categoricalKeys}
      facets={facets}
      facetsState={facetsState}
      facetFieldStates={facetFieldStates}
      populationItemsComplete={populationItemsComplete}
      filteredItemsComplete={filteredItemsComplete}
      selectedItems={selectedItems}
      filters={filters}
      onChangeValues={onChangeCategoricalValues}
      onFacetFieldsChange={setCategoricalFacetKeys}
    />
  )

  if (!metricKeys.length && !categoricalKeys.length) {
    return (
      <div className="h-full flex flex-col gap-3 p-3 overflow-auto scrollbar-thin">
        {attributesPanel}
        <div className="p-4 text-sm text-muted">
          No metrics or categoricals found in this dataset.
        </div>
      </div>
    )
  }

  return (
    <div className="h-full flex flex-col gap-3 p-3 overflow-auto scrollbar-thin">
      {metricKeys.length > 0 && (
        <MetricRangePanel
          items={items}
          filteredItems={filteredItems}
          metricKeys={metricKeys}
          metricDisplayNames={metricDisplayNames}
          facets={facets}
          facetsState={facetsState}
          facetFieldStates={facetFieldStates}
          populationItemsComplete={populationItemsComplete}
          filteredItemsComplete={filteredItemsComplete}
          selectedItems={selectedItems}
          selectedValuesByKey={selectedValuesByKey}
          selectedMetric={selectedMetric}
          onSelectMetric={onSelectMetric}
          filters={filters}
          onChangeRange={onChangeRange}
          onFacetFieldsChange={setMetricFacetKeys}
        />
      )}
      {categoricalPanel}
      {attributesPanel}
    </div>
  )
}
