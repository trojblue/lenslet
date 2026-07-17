import React, { useCallback, useEffect, useMemo, useState } from 'react'
import type { FilterAST, BrowseFacetsPayload, BrowseItemPayload } from '../../../lib/types'
import {
  collectCategoricalBucketsByKey,
  collectCategoricalBucketsFromFacets,
  getCategoricalBuckets,
} from '../model/categoricalValues'
import Dropdown from '../../../shared/ui/Dropdown'
import CategoricalCard from './CategoricalCard'
import VirtualFieldList from './VirtualFieldList'

interface CategoricalPanelProps {
  items: BrowseItemPayload[]
  filteredItems: BrowseItemPayload[]
  categoricalKeys: string[]
  facets?: BrowseFacetsPayload | null
  itemPopulationComplete?: boolean
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
  itemPopulationComplete = true,
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
          itemPopulationComplete,
        )
      }
      if (!itemPopulationComplete) return new Map()
      return collectCategoricalBucketsByKey(items, filteredItems, selectedItems, scopedCategoricalKeys)
    },
    [facets, filteredItems, itemPopulationComplete, items, selectedItems, scopedCategoricalKeys]
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

  const renderCategoricalCard = (key: string, showTitle = false) => (
    <CategoricalCard
      key={key}
      categoricalKey={key}
      buckets={getCategoricalBuckets(bucketsByKey, key)}
      filters={filters}
      onChangeValues={onChangeValues}
      showTitle={showTitle}
      showFilteredCounts={itemPopulationComplete}
    />
  )

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
          estimateSize={420}
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
