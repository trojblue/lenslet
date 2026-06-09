import type { BrowseFacetsPayload, BrowseItemPayload } from '../../../lib/types'

export type CategoricalBucket = {
  value: string
  populationCount: number
  filteredCount: number
  selectedCount: number
}

export type CategoricalBucketsByKey = Map<string, CategoricalBucket[]>

const EMPTY_BUCKETS: CategoricalBucket[] = []

export function collectCategoricalBucketsByKey(
  populationItems: BrowseItemPayload[],
  filteredItems: BrowseItemPayload[],
  selectedItems: BrowseItemPayload[] | undefined,
  categoricalKeys: readonly string[],
): CategoricalBucketsByKey {
  const bucketsByKey: CategoricalBucketsByKey = new Map()
  for (const key of categoricalKeys) {
    const byValue = new Map<string, CategoricalBucket>()
    addCategoricalCounts(byValue, key, populationItems, 'populationCount')
    if (!byValue.size) continue
    addCategoricalCounts(byValue, key, filteredItems, 'filteredCount')
    if (selectedItems?.length) {
      addCategoricalCounts(byValue, key, selectedItems, 'selectedCount')
    }
    bucketsByKey.set(key, Array.from(byValue.values()).sort(compareBuckets))
  }
  return bucketsByKey
}

export function collectCategoricalBucketsFromFacets(
  facets: BrowseFacetsPayload,
  filteredItems: BrowseItemPayload[],
  selectedItems: BrowseItemPayload[] | undefined,
  categoricalKeys: readonly string[],
  includeFilteredCounts: boolean,
): CategoricalBucketsByKey {
  const bucketsByKey: CategoricalBucketsByKey = new Map()
  for (const key of categoricalKeys) {
    const facet = facets.categoricals[key]
    if (!facet?.values.length) continue
    const byValue = new Map<string, CategoricalBucket>()
    for (const valueFacet of facet.values) {
      const value = valueFacet.value.trim()
      if (!value) continue
      byValue.set(value, {
        value,
        populationCount: valueFacet.population_count,
        filteredCount: 0,
        selectedCount: 0,
      })
    }
    if (includeFilteredCounts) {
      addCategoricalCounts(byValue, key, filteredItems, 'filteredCount')
    }
    if (selectedItems?.length) {
      addCategoricalCounts(byValue, key, selectedItems, 'selectedCount')
    }
    bucketsByKey.set(key, Array.from(byValue.values()).sort(compareBuckets))
  }
  return bucketsByKey
}

export function getCategoricalBuckets(
  bucketsByKey: CategoricalBucketsByKey,
  key: string,
): CategoricalBucket[] {
  return bucketsByKey.get(key) ?? EMPTY_BUCKETS
}

function addCategoricalCounts(
  byValue: Map<string, CategoricalBucket>,
  key: string,
  items: BrowseItemPayload[],
  countKey: 'populationCount' | 'filteredCount' | 'selectedCount',
): void {
  for (const item of items) {
    const raw = item.categoricals?.[key]
    const value = raw?.trim()
    if (!value) continue
    let bucket = byValue.get(value)
    if (!bucket) {
      bucket = {
        value,
        populationCount: 0,
        filteredCount: 0,
        selectedCount: 0,
      }
      byValue.set(value, bucket)
    }
    bucket[countKey] += 1
  }
}

function compareBuckets(a: CategoricalBucket, b: CategoricalBucket): number {
  if (b.populationCount !== a.populationCount) return b.populationCount - a.populationCount
  return a.value.localeCompare(b.value)
}
