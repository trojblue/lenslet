import React, { useCallback, useEffect, useMemo, useState } from 'react'
import type { FilterAST, BrowseFacetsPayload, BrowseItemPayload } from '../../../lib/types'
import {
  collectCategoricalBucketsByKey,
  collectCategoricalBucketsFromFacets,
  getCategoricalBuckets,
} from '../model/categoricalValues'
import {
  facetFieldQueryState,
  resolveFacetFieldState,
  type FacetFieldQueryStates,
  type FacetQueryState,
} from '../model/facetPresentation'
import Dropdown from '../../../shared/ui/Dropdown'
import CategoricalCard from './CategoricalCard'
import VirtualFieldList from './VirtualFieldList'

interface CategoricalPanelProps {
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
  onChangeValues: (key: string, values: string[] | null) => void
  onFacetFieldsChange?: (keys: string[]) => void
}

export default function CategoricalPanel({
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
  onChangeValues,
  onFacetFieldsChange,
}: CategoricalPanelProps) {
  const [showAll, setShowAll] = useState(false)
  const [visibleCategoricalKeys, setVisibleCategoricalKeys] = useState<string[]>([])
  const [selectedCategorical, setSelectedCategorical] = useState<string | null>(null)
  const activeCategorical = selectedCategorical && categoricalKeys.includes(selectedCategorical)
    ? selectedCategorical
    : categoricalKeys[0]
  const scopedCategoricalKeys = useMemo(() => (
    showAll ? visibleCategoricalKeys : activeCategorical ? [activeCategorical] : []
  ), [showAll, visibleCategoricalKeys, activeCategorical])
  const bucketsByKey = useMemo(
    () => {
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
    [facets, filteredItems, filteredItemsComplete, items, populationItemsComplete, selectedItems, scopedCategoricalKeys]
  )
  const localBucketsByKey = useMemo(
    () => populationItemsComplete
      ? collectCategoricalBucketsByKey(items, filteredItems, selectedItems, scopedCategoricalKeys)
      : new Map(),
    [filteredItems, items, populationItemsComplete, scopedCategoricalKeys, selectedItems],
  )
  const categoricalOptions = useMemo(() => (
    categoricalKeys.map((key) => ({
      value: key,
      label: key,
      keywords: [key],
    }))
  ), [categoricalKeys])

  useEffect(() => {
    if (!showAll) onFacetFieldsChange?.(activeCategorical ? [activeCategorical] : [])
  }, [activeCategorical, onFacetFieldsChange, showAll])

  const handleVisibleKeysChange = useCallback((keys: string[]) => {
    setVisibleCategoricalKeys(keys)
    onFacetFieldsChange?.(keys)
  }, [onFacetFieldsChange])

  if (!categoricalKeys.length) return null

  const renderCategoricalCard = (key: string, showTitle = false) => {
    const hasFacet = Object.prototype.hasOwnProperty.call(facets?.categoricals ?? {}, key)
    const facetBuckets = getCategoricalBuckets(bucketsByKey, key)
    const localBuckets = getCategoricalBuckets(localBucketsByKey, key)
    return (
      <CategoricalCard
        categoricalKey={key}
        buckets={hasFacet ? facetBuckets : localBuckets}
        filters={filters}
        onChangeValues={onChangeValues}
        showTitle={showTitle}
        showFilteredCounts={filteredItemsComplete}
        state={resolveFacetFieldState({
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
        })}
      />
    )
  }

  return (
    <>
      <div>
        <div className="flex items-center justify-between gap-2">
          <label className="ui-label">Categorical</label>
          <button
            className="btn btn-sm btn-ghost text-[11px]"
            onClick={() => setShowAll((v) => !v)}
            aria-pressed={showAll}
            data-categorical-show-all
          >
            {showAll ? 'Show one' : 'Show all'}
          </button>
        </div>
        {showAll ? (
          <div className="ui-input ui-input-readonly w-full flex items-center text-xs">
            All categoricals
          </div>
        ) : (
          <div data-categorical-selector>
            <Dropdown
              value={activeCategorical ?? ''}
              onChange={setSelectedCategorical}
              options={categoricalOptions}
              aria-label="Categorical"
              title={activeCategorical ?? 'Categorical'}
              triggerClassName="w-full justify-between"
              width="trigger"
              searchable="auto"
              searchPlaceholder="Search fields..."
              emptyMessage="No matching fields"
            />
          </div>
        )}
      </div>

      {showAll ? (
        <VirtualFieldList
          keys={categoricalKeys}
          estimateSize={384}
          kind="categorical"
          onVisibleKeysChange={handleVisibleKeysChange}
          renderCard={(key) => renderCategoricalCard(key, true)}
        />
      ) : (
        activeCategorical ? (
          renderCategoricalCard(activeCategorical)
        ) : (
          <div className="text-sm text-muted">No values found for this field.</div>
        )
      )}
    </>
  )
}
