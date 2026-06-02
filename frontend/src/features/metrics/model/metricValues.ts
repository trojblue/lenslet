import type { BrowseItemPayload } from '../../../lib/types'

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
      if (raw == null || Number.isNaN(raw)) continue
      const existing = valuesByKey.get(key)
      if (existing) existing.push(raw)
      else valuesByKey.set(key, [raw])
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
      const raw = metrics[bucket.key]
      if (raw == null || Number.isNaN(raw)) continue
      bucket.values.push(raw)
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
    const rawCode = item.metrics?.[key]
    if (!label || rawCode == null || Number.isNaN(rawCode)) continue
    let bucket = byCode.get(rawCode)
    if (!bucket) {
      bucket = {
        code: rawCode,
        label,
        populationCount: 0,
        filteredCount: 0,
        selectedCount: 0,
      }
      byCode.set(rawCode, bucket)
    }
    bucket[countKey] += 1
  }
}
