import React, { useCallback, useMemo } from 'react'
import type { FilterAST, BrowseFacetsPayload, BrowseItemPayload } from '../../../lib/types'
import {
  collectCategoricalBucketsByKey,
  collectCategoricalBucketsFromFacets,
  getCategoricalBuckets,
} from '../model/categoricalValues'
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
import Dropdown from '../../../shared/ui/Dropdown'
import CategoricalCard from './CategoricalCard'
import VirtualFieldList from './VirtualFieldList'

interface CategoricalPanelProps {
  active?: boolean
  items: BrowseItemPayload[]
  filteredItems: BrowseItemPayload[]
  categoricalKeys: string[]
  facets?: BrowseFacetsPayload | null
  facetsState?: FacetQueryState
  facetFieldStates?: FacetFieldQueryStates
  populationItemsComplete?: boolean
  filteredItemsComplete?: boolean
  selectedItems?: BrowseItemPayload[]
  filters: FilterAST
  demand: MetricsFacetDemand['categorical']
  presentationResetKey?: string
  onChangeValues: (key: string, values: string[] | null) => void
  onDemandAction: (action: MetricsFacetDemandAction) => void
}

type CategoricalFieldValue = {
  buckets: ReturnType<typeof getCategoricalBuckets>
  showFilteredCounts: boolean
}

export default function CategoricalPanel({
  active = true,
  items,
  filteredItems,
  categoricalKeys,
  facets = null,
  facetsState = 'settled',
  facetFieldStates,
  populationItemsComplete = true,
  filteredItemsComplete = true,
  selectedItems,
  filters,
  demand,
  presentationResetKey = 'default',
  onChangeValues,
  onDemandAction,
}: CategoricalPanelProps) {
  const activeCategorical = demand.selectedKey && categoricalKeys.includes(demand.selectedKey)
    ? demand.selectedKey
    : categoricalKeys[0]
  const scopedCategoricalKeys = useMemo(() => (
    !active ? [] : demand.showAll ? demand.visibleKeys : activeCategorical ? [activeCategorical] : []
  ), [active, activeCategorical, demand.showAll, demand.visibleKeys])
  const bucketsByKey = useMemo(
    () => {
      if (!active) return new Map()
      if (facets) {
        return collectCategoricalBucketsFromFacets(
          facets,
          filteredItems,
          selectedItems,
          scopedCategoricalKeys,
          filteredItemsComplete,
        )
      }
      if (!populationItemsComplete) return new Map()
      return collectCategoricalBucketsByKey(items, filteredItems, selectedItems, scopedCategoricalKeys)
    },
    [active, facets, filteredItems, filteredItemsComplete, items, populationItemsComplete, selectedItems, scopedCategoricalKeys]
  )
  const localBucketsByKey = useMemo(
    () => active && populationItemsComplete
      ? collectCategoricalBucketsByKey(items, filteredItems, selectedItems, scopedCategoricalKeys)
      : new Map(),
    [active, filteredItems, items, populationItemsComplete, scopedCategoricalKeys, selectedItems],
  )
  const categoricalOptions = useMemo(() => (
    categoricalKeys.map((key) => ({
      value: key,
      label: key,
      keywords: [key],
    }))
  ), [categoricalKeys])

  const categoricalFieldValue = useCallback((key: string): {
    state: FacetFieldState
    value: CategoricalFieldValue
  } => {
    if (!active) {
      return {
        state: 'pending',
        value: { buckets: [], showFilteredCounts: false },
      }
    }
    const hasFacet = Object.prototype.hasOwnProperty.call(facets?.categoricals ?? {}, key)
    const facetBuckets = getCategoricalBuckets(bucketsByKey, key)
    const localBuckets = getCategoricalBuckets(localBucketsByKey, key)
    return {
      state: resolveFacetFieldState({
        facetDataState: !hasFacet
          ? 'absent'
          : facetBuckets.length > 0
            ? 'ready'
            : 'empty',
        localDataState: !populationItemsComplete
          ? 'absent'
          : localBuckets.length > 0
            ? 'ready'
            : 'empty',
        queryState: facetFieldQueryState(facetFieldStates, 'categoricals', key, facetsState),
      }),
      value: {
        buckets: hasFacet ? facetBuckets : localBuckets,
        showFilteredCounts: filteredItemsComplete,
      },
    }
  }, [
    active,
    bucketsByKey,
    facetFieldStates,
    facets,
    facetsState,
    filteredItemsComplete,
    localBucketsByKey,
    populationItemsComplete,
  ])
  const requestedField = useMemo(() => {
    const key = activeCategorical ?? ''
    const field = key
      ? categoricalFieldValue(key)
      : { state: 'empty' as const, value: { buckets: [], showFilteredCounts: false } }
    return { key, ...field }
  }, [activeCategorical, categoricalFieldValue])
  const { presentation: presentedField, retained } = useFacetFieldPresentation(
    requestedField,
    presentationResetKey,
  )
  const cachedCategoricalKeys = useMemo(() => Array.from(new Set([
    ...scopedCategoricalKeys,
    ...(activeCategorical ? [activeCategorical] : []),
  ])), [activeCategorical, scopedCategoricalKeys])
  const cachedCategoricalCandidates = useMemo(() => cachedCategoricalKeys.map((key) => ({
    key,
    ...categoricalFieldValue(key),
  })), [cachedCategoricalKeys, categoricalFieldValue])
  const cachedCategoricalPresentations = useFacetFieldPresentations(
    cachedCategoricalCandidates,
    categoricalKeys,
    presentationResetKey,
  )

  const handleVisibleKeysChange = useCallback((keys: string[]) => {
    if (!keys.length) return
    onDemandAction({
      type: 'set-visible-keys',
      kind: 'categorical',
      schemaKey: facetSchemaKey(categoricalKeys),
      schemaRevision: demand.schemaRevision,
      keys,
    })
  }, [categoricalKeys, demand.schemaRevision, onDemandAction])

  if (!categoricalKeys.length) return null

  const renderCategoricalCard = (
    key: string,
    showTitle = false,
    field = categoricalFieldValue(key),
    fieldRetained = false,
    requestedKey = fieldRetained ? activeCategorical : key,
  ) => {
    return (
      <div
        aria-busy={fieldRetained || undefined}
        aria-disabled={fieldRetained || undefined}
        data-facet-requested-field={requestedKey}
        data-facet-presented-field={key}
        ref={(element) => {
          if (fieldRetained) element?.setAttribute('inert', '')
          else element?.removeAttribute('inert')
        }}
      >
        <CategoricalCard
          categoricalKey={key}
          buckets={field.value.buckets}
          filters={filters}
          onChangeValues={onChangeValues}
          showTitle={showTitle}
          showFilteredCounts={field.value.showFilteredCounts}
          state={field.state}
        />
      </div>
    )
  }

  const handleCategoricalChange = (key: string) => {
    onDemandAction({ type: 'select-categorical', key })
  }
  const handleShowAllChange = () => {
    onDemandAction({
      type: 'set-show-all',
      kind: 'categorical',
      showAll: !demand.showAll,
    })
  }

  return (
    <>
      <div>
        <div className="flex items-center justify-between gap-2">
          <label className="ui-label">Categorical</label>
          <button
            className="btn btn-sm btn-ghost text-[11px]"
            onClick={handleShowAllChange}
            aria-pressed={demand.showAll}
            data-categorical-show-all
          >
            {demand.showAll ? 'Show one' : 'Show all'}
          </button>
        </div>
        {demand.showAll ? (
          <div className="ui-input ui-input-readonly w-full flex items-center text-xs">
            All categoricals
          </div>
        ) : (
          <div
            data-categorical-selector
            data-facet-requested-field={activeCategorical ?? ''}
            data-facet-presented-field={presentedField.key}
            aria-busy={retained || undefined}
          >
            <Dropdown
              value={presentedField.key}
              onChange={handleCategoricalChange}
              options={categoricalOptions}
              aria-label="Categorical"
              title={presentedField.key || 'Categorical'}
              triggerClassName="w-full justify-between"
              width="trigger"
              searchable="auto"
              searchPlaceholder="Search fields..."
              emptyMessage="No matching fields"
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
          keys={categoricalKeys}
          estimateSize={384}
          kind="categorical"
          schemaRevision={demand.schemaRevision}
          active={active && demand.showAll}
          onVisibleKeysChange={handleVisibleKeysChange}
          renderCard={(key) => {
            const cached = cachedCategoricalPresentations.get(key)
            return renderCategoricalCard(
              key,
              true,
              cached
                ? { state: cached.presentation.state, value: cached.presentation.value }
                : categoricalFieldValue(key),
              cached?.retained ?? false,
              key,
            )
          }}
        />
      </div>
      {!demand.showAll && (
        presentedField.key ? (
          renderCategoricalCard(
            presentedField.key,
            false,
            { state: presentedField.state, value: presentedField.value },
            retained,
          )
        ) : (
          <div className="text-sm text-muted">No values found for this field.</div>
        )
      )}
    </>
  )
}
