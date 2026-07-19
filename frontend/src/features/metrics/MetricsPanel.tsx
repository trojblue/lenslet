import React, { useMemo } from 'react'
import type { FilterAST, BrowseFacetsPayload, BrowseItemPayload, MetricDisplayNames } from '../../lib/types'
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
import type {
  MetricsFacetDemand,
  MetricsFacetDemandAction,
} from './model/facetDemand'
import { resolveMetricsFacetFields } from './model/facetDemand'

interface MetricsPanelProps {
  active?: boolean
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
  facetDemand: MetricsFacetDemand
  presentationResetKey?: string
  onSelectMetric: (key: string) => void
  filters: FilterAST
  onChangeRange: (key: string, range: Range | null) => void
  onChangeCategoricalValues: (key: string, values: string[] | null) => void
  onChangeFilters: (filters: FilterAST) => void
  onFacetDemandAction: (action: MetricsFacetDemandAction) => void
}

export default function MetricsPanel({
  active = true,
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
  facetDemand,
  presentationResetKey = 'default',
  onSelectMetric,
  filters,
  onChangeRange,
  onChangeCategoricalValues,
  onChangeFilters,
  onFacetDemandAction,
}: MetricsPanelProps) {
  const selectedValuesByKey = useMemo(() => (
    active && selectedItems?.length ? collectMetricValuesByKey(selectedItems, metricKeys) : null
  ), [active, selectedItems, metricKeys])
  const requestedFacetFields = useMemo(() => resolveMetricsFacetFields(
    facetDemand,
    selectedMetric,
    metricKeys,
    categoricalKeys,
  ), [categoricalKeys, facetDemand, metricKeys, selectedMetric])
  const attributesPanel = (
    <AttributesPanel
      filters={filters}
      onChangeFilters={onChangeFilters}
    />
  )
  const categoricalPanel = (
    <CategoricalPanel
      active={active}
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
      demand={facetDemand.categorical}
      presentationResetKey={presentationResetKey}
      onChangeValues={onChangeCategoricalValues}
      onDemandAction={onFacetDemandAction}
    />
  )

  if (!metricKeys.length && !categoricalKeys.length) {
    return (
      <div
        className="h-full flex flex-col gap-3 p-3 overflow-auto scrollbar-thin"
        data-metrics-panel
        data-presentation-reset-key={presentationResetKey}
        data-requested-metric-fields={JSON.stringify(requestedFacetFields.metric_keys)}
        data-requested-categorical-fields={JSON.stringify(requestedFacetFields.categorical_keys)}
      >
        {attributesPanel}
        <div className="p-4 text-sm text-muted">
          No metrics or categoricals found in this dataset.
        </div>
      </div>
    )
  }

  return (
    <div
      className="h-full flex flex-col gap-3 p-3 overflow-auto scrollbar-thin"
      data-metrics-panel
      data-presentation-reset-key={presentationResetKey}
      data-metric-field-schema={JSON.stringify(metricKeys)}
      data-categorical-field-schema={JSON.stringify(categoricalKeys)}
      data-requested-metric-fields={JSON.stringify(requestedFacetFields.metric_keys)}
      data-requested-categorical-fields={JSON.stringify(requestedFacetFields.categorical_keys)}
    >
      {metricKeys.length > 0 && (
        <MetricRangePanel
          active={active}
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
          demand={facetDemand.metric}
          presentationResetKey={presentationResetKey}
          onSelectMetric={onSelectMetric}
          filters={filters}
          onChangeRange={onChangeRange}
          onDemandAction={onFacetDemandAction}
        />
      )}
      {categoricalPanel}
      {attributesPanel}
    </div>
  )
}
