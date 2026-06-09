import type { BrowseFacetsPayload, BrowseItemPayload, MetricHistogramFacet } from '../../../lib/types'
import type { Histogram } from './histogram'
import { finiteMetricValue } from '../../../lib/metrics'

export type MetricValuesByKey = Map<string, number[]>
export type MetricCategoryBucket = {
  code: number
  label: string
  populationCount: number
  filteredCount: number
  selectedCount: number
}
export type MetricCategoriesByKey = Map<string, MetricCategoryBucket[]>

const EMPTY_VALUES: number[] = []
const EMPTY_CATEGORIES: MetricCategoryBucket[] = []

export function collectMetricValuesByKey(items: BrowseItemPayload[], metricKeys?: readonly string[]): MetricValuesByKey {
  if (metricKeys?.length) {
    return collectMetricValuesForKeys(items, metricKeys)
  }

  const valuesByKey: MetricValuesByKey = new Map()

  for (const it of items) {
    const metrics = it.metrics
    if (!metrics) continue
    for (const [key, raw] of Object.entries(metrics)) {
      const value = finiteMetricValue(raw)
      if (value == null) continue
      const existing = valuesByKey.get(key)
      if (existing) existing.push(value)
      else valuesByKey.set(key, [value])
    }
  }

  return valuesByKey
}

function collectMetricValuesForKeys(items: BrowseItemPayload[], metricKeys: readonly string[]): MetricValuesByKey {
  const buckets = metricKeys.map((key) => ({ key, values: [] as number[] }))

  for (const it of items) {
    const metrics = it.metrics
    if (!metrics) continue
    for (const bucket of buckets) {
      const value = finiteMetricValue(metrics[bucket.key])
      if (value == null) continue
      bucket.values.push(value)
    }
  }

  const valuesByKey: MetricValuesByKey = new Map()
  for (const bucket of buckets) {
    if (bucket.values.length) valuesByKey.set(bucket.key, bucket.values)
  }
  return valuesByKey
}

export function getMetricValues(valuesByKey: MetricValuesByKey, key: string): number[] {
  return valuesByKey.get(key) ?? EMPTY_VALUES
}

export function collectMetricCategoriesByKey(
  populationItems: BrowseItemPayload[],
  filteredItems: BrowseItemPayload[],
  selectedItems: BrowseItemPayload[] | undefined,
  metricKeys: readonly string[],
): MetricCategoriesByKey {
  const categoriesByKey: MetricCategoriesByKey = new Map()
  for (const key of metricKeys) {
    const byCode = new Map<number, MetricCategoryBucket>()
    addCategoryCounts(byCode, key, populationItems, 'populationCount')
    if (!byCode.size) continue
    addCategoryCounts(byCode, key, filteredItems, 'filteredCount')
    if (selectedItems?.length) {
      addCategoryCounts(byCode, key, selectedItems, 'selectedCount')
    }
    categoriesByKey.set(key, Array.from(byCode.values()).sort((a, b) => a.code - b.code))
  }
  return categoriesByKey
}

export function collectMetricCategoriesFromFacets(
  facets: BrowseFacetsPayload,
  filteredItems: BrowseItemPayload[],
  selectedItems: BrowseItemPayload[] | undefined,
  metricKeys: readonly string[],
  includeFilteredCounts: boolean,
): MetricCategoriesByKey {
  const categoriesByKey: MetricCategoriesByKey = new Map()
  for (const key of metricKeys) {
    const facet = facets.metrics[key]
    if (!facet?.categories.length) continue
    const byCode = new Map<number, MetricCategoryBucket>()
    for (const category of facet.categories) {
      byCode.set(category.code, {
        code: category.code,
        label: category.label,
        populationCount: category.population_count,
        filteredCount: 0,
        selectedCount: 0,
      })
    }
    if (includeFilteredCounts) {
      addCategoryCounts(byCode, key, filteredItems, 'filteredCount')
    }
    if (selectedItems?.length) {
      addCategoryCounts(byCode, key, selectedItems, 'selectedCount')
    }
    categoriesByKey.set(key, Array.from(byCode.values()).sort((a, b) => a.code - b.code))
  }
  return categoriesByKey
}

export function metricHistogramFromFacet(
  facet: MetricHistogramFacet | null | undefined,
): Histogram | null {
  if (!facet || !facet.bins.length || facet.count <= 0) return null
  return {
    bins: [...facet.bins],
    min: facet.min,
    max: facet.max,
    count: facet.count,
  }
}

export function getMetricCategories(categoriesByKey: MetricCategoriesByKey, key: string): MetricCategoryBucket[] {
  return categoriesByKey.get(key) ?? EMPTY_CATEGORIES
}

function addCategoryCounts(
  byCode: Map<number, MetricCategoryBucket>,
  key: string,
  items: BrowseItemPayload[],
  countKey: 'populationCount' | 'filteredCount' | 'selectedCount',
): void {
  for (const item of items) {
    const label = item.metric_labels?.[key]
    const code = finiteMetricValue(item.metrics?.[key])
    if (!label || code == null) continue
    let bucket = byCode.get(code)
    if (!bucket) {
      bucket = {
        code,
        label,
        populationCount: 0,
        filteredCount: 0,
        selectedCount: 0,
      }
      byCode.set(code, bucket)
    }
    bucket[countKey] += 1
  }
}
