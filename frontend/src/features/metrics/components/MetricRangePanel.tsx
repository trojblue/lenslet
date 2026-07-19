import React, { useCallback, useMemo } from 'react'
import type { FilterAST, BrowseFacetsPayload, BrowseItemPayload, MetricDisplayNames } from '../../../lib/types'
import { getMetricDisplayName } from '../../../lib/metricDisplay'
import type { Range } from '../model/histogram'
import {
  facetFieldQueryState,
  resolveFacetFieldState,
  useFacetFieldPresentation,
  useFacetFieldPresentations,
  type FacetFieldQueryStates,
  type FacetFieldState,
  type FacetQueryState,
} from '../model/facetPresentation'
import {
  facetSchemaKey,
  type MetricsFacetDemand,
  type MetricsFacetDemandAction,
} from '../model/facetDemand'
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
  active?: boolean
  items: BrowseItemPayload[]
  filteredItems: BrowseItemPayload[]
  metricKeys: string[]
  metricDisplayNames?: MetricDisplayNames | null
  facets?: BrowseFacetsPayload | null
  facetsState?: FacetQueryState
  facetFieldStates?: FacetFieldQueryStates
  populationItemsComplete?: boolean
  filteredItemsComplete?: boolean
  selectedItems?: BrowseItemPayload[]
  selectedValuesByKey?: MetricValuesByKey | null
  selectedMetric?: string
  demand: MetricsFacetDemand['metric']
  presentationResetKey?: string
  onSelectMetric: (key: string) => void
  filters: FilterAST
  onChangeRange: (key: string, range: Range | null) => void
  onDemandAction: (action: MetricsFacetDemandAction) => void
}

const EMPTY_VALUES_BY_KEY: MetricValuesByKey = new Map()

type MetricFieldValue = {
  categories: ReturnType<typeof getMetricCategories>
  filteredValues: number[]
  label: string
  populationHistogram: ReturnType<typeof metricHistogramFromFacet>
  populationValues: number[]
  selectedValues: number[]
  showFilteredCounts: boolean
}

export default function MetricRangePanel({
  active = true,
  items,
  filteredItems,
  metricKeys,
  metricDisplayNames,
  facets = null,
  facetsState = 'settled',
  facetFieldStates,
  populationItemsComplete = true,
  filteredItemsComplete = true,
  selectedItems,
  selectedValuesByKey,
  selectedMetric,
  demand,
  presentationResetKey = 'default',
  onSelectMetric,
  filters,
  onChangeRange,
  onDemandAction,
}: MetricRangePanelProps) {
  const activeMetric = selectedMetric && metricKeys.includes(selectedMetric) ? selectedMetric : metricKeys[0]
  const scopedMetricKeys = useMemo(() => (
    !active ? [] : demand.showAll ? demand.visibleKeys : activeMetric ? [activeMetric] : []
  ), [active, activeMetric, demand.showAll, demand.visibleKeys])
  const populationValuesByKey = useMemo(
    () => active && populationItemsComplete
      ? collectMetricValuesByKey(items, scopedMetricKeys)
      : EMPTY_VALUES_BY_KEY,
    [active, items, populationItemsComplete, scopedMetricKeys]
  )
  const filteredValuesByKey = useMemo(
    () => active ? collectMetricValuesByKey(filteredItems, scopedMetricKeys) : EMPTY_VALUES_BY_KEY,
    [active, filteredItems, scopedMetricKeys]
  )
  const categoriesByKey = useMemo(
    () => {
      if (!active) return new Map()
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
    [active, facets, filteredItems, filteredItemsComplete, items, populationItemsComplete, selectedItems, scopedMetricKeys]
  )
  const localCategoriesByKey = useMemo(
    () => active && populationItemsComplete
      ? collectMetricCategoriesByKey(items, filteredItems, selectedItems, scopedMetricKeys)
      : new Map(),
    [active, filteredItems, items, populationItemsComplete, scopedMetricKeys, selectedItems],
  )
  const selectedValues = selectedValuesByKey ?? EMPTY_VALUES_BY_KEY
  const metricOptions = useMemo(() => (
    metricKeys.map((key) => ({
      value: key,
      label: getMetricDisplayName(key, metricDisplayNames),
      keywords: [key],
    }))
  ), [metricDisplayNames, metricKeys])

  const metricFieldValue = useCallback((key: string): {
    state: FacetFieldState
    value: MetricFieldValue
  } => {
    if (!active) {
      return {
        state: 'pending',
        value: {
          categories: [],
          filteredValues: [],
          label: getMetricDisplayName(key, metricDisplayNames),
          populationHistogram: null,
          populationValues: [],
          selectedValues: [],
          showFilteredCounts: false,
        },
      }
    }
    const metricFacet = facets?.metrics[key] ?? null
    const hasFacet = Object.prototype.hasOwnProperty.call(facets?.metrics ?? {}, key)
    const facetCategories = getMetricCategories(categoriesByKey, key)
    const localCategories = getMetricCategories(localCategoriesByKey, key)
    const categories = hasFacet ? facetCategories : localCategories
    const populationHistogram = metricHistogramFromFacet(metricFacet?.histogram)
    const populationValues = getMetricValues(populationValuesByKey, key)
    return {
      state: resolveFacetFieldState({
        facetDataState: !hasFacet
          ? 'absent'
          : facetCategories.length > 0 || populationHistogram !== null
            ? 'ready'
            : 'empty',
        localDataState: !populationItemsComplete
          ? 'absent'
          : localCategories.length > 0 || populationValues.length > 0
            ? 'ready'
            : 'empty',
        queryState: facetFieldQueryState(facetFieldStates, 'metrics', key, facetsState),
      }),
      value: {
        categories,
        filteredValues: filteredItemsComplete ? getMetricValues(filteredValuesByKey, key) : [],
        label: getMetricDisplayName(key, metricDisplayNames),
        populationHistogram,
        populationValues: hasFacet ? [] : populationValues,
        selectedValues: getMetricValues(selectedValues, key),
        showFilteredCounts: filteredItemsComplete,
      },
    }
  }, [
    active,
    categoriesByKey,
    facetFieldStates,
    facets,
    facetsState,
    filteredItemsComplete,
    filteredValuesByKey,
    localCategoriesByKey,
    metricDisplayNames,
    populationItemsComplete,
    populationValuesByKey,
    selectedValues,
  ])
  const requestedField = useMemo(() => {
    const key = activeMetric ?? ''
    const field = key
      ? metricFieldValue(key)
      : {
          state: 'empty' as const,
          value: {
            categories: [],
            filteredValues: [],
            label: '',
            populationHistogram: null,
            populationValues: [],
            selectedValues: [],
            showFilteredCounts: false,
          },
        }
    return { key, ...field }
  }, [activeMetric, metricFieldValue])
  const { presentation: presentedField, retained } = useFacetFieldPresentation(
    requestedField,
    presentationResetKey,
  )
  const cachedMetricKeys = useMemo(() => Array.from(new Set([
    ...scopedMetricKeys,
    ...(activeMetric ? [activeMetric] : []),
  ])), [activeMetric, scopedMetricKeys])
  const cachedMetricCandidates = useMemo(() => cachedMetricKeys.map((key) => ({
    key,
    ...metricFieldValue(key),
  })), [cachedMetricKeys, metricFieldValue])
  const cachedMetricPresentations = useFacetFieldPresentations(
    cachedMetricCandidates,
    metricKeys,
    presentationResetKey,
  )

  const handleVisibleKeysChange = useCallback((keys: string[]) => {
    if (!keys.length) return
    onDemandAction({
      type: 'set-visible-keys',
      kind: 'metric',
      schemaKey: facetSchemaKey(metricKeys),
      schemaRevision: demand.schemaRevision,
      keys,
    })
  }, [demand.schemaRevision, metricKeys, onDemandAction])

  const renderMetricCard = (
    key: string,
    showTitle = false,
    field = metricFieldValue(key),
    fieldRetained = false,
    requestedKey = fieldRetained ? activeMetric : key,
  ) => {
    return (
      <div
        className="ui-card h-96"
        data-metric-card-host={key}
        data-facet-state={field.state}
        data-facet-requested-field={requestedKey}
        data-facet-presented-field={key}
        aria-busy={fieldRetained || undefined}
        aria-disabled={fieldRetained || undefined}
        ref={(element) => {
          if (fieldRetained) element?.setAttribute('inert', '')
          else element?.removeAttribute('inert')
        }}
      >
        {field.value.categories.length ? (
          <MetricCategoryCard
            key={key}
            metricKey={key}
            metricLabel={field.value.label}
            categories={field.value.categories}
            filters={filters}
            onChangeRange={onChangeRange}
            showTitle={showTitle}
            showFilteredCounts={field.value.showFilteredCounts}
            state={field.state}
            embedded
          />
        ) : (
          <MetricHistogramCard
            key={key}
            metricKey={key}
            metricLabel={field.value.label}
            populationValues={field.value.populationValues}
            filteredValues={field.value.filteredValues}
            populationHistogram={field.value.populationHistogram}
            selectedValues={field.value.selectedValues}
            filters={filters}
            onChangeRange={onChangeRange}
            showTitle={showTitle}
            showFilteredCounts={field.value.showFilteredCounts}
            state={field.state}
            embedded
          />
        )}
      </div>
    )
  }

  const handleMetricChange = (key: string) => {
    onSelectMetric(key)
  }
  const handleShowAllChange = () => {
    onDemandAction({
      type: 'set-show-all',
      kind: 'metric',
      showAll: !demand.showAll,
    })
  }

  return (
    <>
      <div>
        <div className="flex items-center justify-between gap-2">
          <label className="ui-label">Metric</label>
          <button
            className="btn btn-sm btn-ghost text-[11px]"
            onClick={handleShowAllChange}
            aria-pressed={demand.showAll}
            data-metric-show-all
          >
            {demand.showAll ? 'Show one' : 'Show all'}
          </button>
        </div>
        {demand.showAll ? (
          <div className="ui-input ui-input-readonly w-full flex items-center text-xs">
            All metrics
          </div>
        ) : (
          <div
            data-metric-selector
            data-facet-requested-field={activeMetric ?? ''}
            data-facet-presented-field={presentedField.key}
            aria-busy={retained || undefined}
          >
            <Dropdown
              value={presentedField.key}
              onChange={handleMetricChange}
              options={metricOptions}
              aria-label="Metric"
              title={presentedField.value.label || 'Metric'}
              triggerClassName="w-full justify-between"
              width="trigger"
              searchable="auto"
              searchPlaceholder="Search metrics..."
              emptyMessage="No matching metrics"
            />
          </div>
        )}
      </div>

      <div
        hidden={!demand.showAll}
        aria-hidden={!demand.showAll || undefined}
        ref={(element) => element?.toggleAttribute('inert', !demand.showAll)}
      >
        <VirtualFieldList
          key={presentationResetKey}
          keys={metricKeys}
          estimateSize={384}
          kind="metric"
          schemaRevision={demand.schemaRevision}
          active={active && demand.showAll}
          onVisibleKeysChange={handleVisibleKeysChange}
          renderCard={(key) => {
            const cached = cachedMetricPresentations.get(key)
            return renderMetricCard(
              key,
              true,
              cached
                ? { state: cached.presentation.state, value: cached.presentation.value }
                : metricFieldValue(key),
              cached?.retained ?? false,
              key,
            )
          }}
        />
      </div>
      {!demand.showAll && (
        presentedField.key ? (
          renderMetricCard(
            presentedField.key,
            false,
            { state: presentedField.state, value: presentedField.value },
            retained,
          )
        ) : (
          <div className="text-sm text-muted">No values found for this metric.</div>
        )
      )}
    </>
  )
}
