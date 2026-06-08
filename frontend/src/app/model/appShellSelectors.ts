import type { BrowseItemPayload, SortSpec, StarRating } from '../../lib/types'
import { finiteMetricValue } from '../../lib/metrics'
import { isDerivedMetricKey, type DerivedMetricStatus } from '../../features/metrics/model/derivedMetric'

type SimilarityStateLike = {
  queryPath: string | null
  queryVector: string | null
} | null

export function hasMetricSortValues(items: readonly BrowseItemPayload[], metricSortKey: string | null): boolean {
  if (!metricSortKey) return false
  return items.some((item) => finiteMetricValue(item.metrics?.[metricSortKey]) != null)
}

function hasAllRequiredKeys(keys: Set<string>, requiredKeys: Set<string>): boolean {
  for (const key of requiredKeys) {
    if (!keys.has(key)) return false
  }
  return true
}

function collectSimilarityMetricKeys(
  items: readonly BrowseItemPayload[],
  scanLimit = 250,
  requiredMetricKeys: readonly string[] = [],
): string[] {
  const keys = new Set<string>()
  const requiredKeys = new Set(requiredMetricKeys.filter((key) => !isDerivedMetricKey(key)))
  let scanned = 0
  for (const item of items) {
    const metrics = item.metrics
    if (metrics) {
      for (const key of Object.keys(metrics)) {
        if (isDerivedMetricKey(key)) continue
        keys.add(key)
      }
    }
    scanned += 1
    if (scanned >= scanLimit && keys.size > 0 && hasAllRequiredKeys(keys, requiredKeys)) break
  }
  return Array.from(keys).sort()
}

function collectSimilarityCategoricalKeys(
  items: readonly BrowseItemPayload[],
  scanLimit = 250,
  requiredCategoricalKeys: readonly string[] = [],
): string[] {
  const keys = new Set<string>()
  const requiredKeys = new Set(requiredCategoricalKeys)
  let scanned = 0
  for (const item of items) {
    const categoricals = item.categoricals
    if (categoricals) {
      for (const key of Object.keys(categoricals)) {
        keys.add(key)
      }
    }
    scanned += 1
    if (scanned >= scanLimit && keys.size > 0 && hasAllRequiredKeys(keys, requiredKeys)) break
  }
  return Array.from(keys).sort()
}

export function resolveMetricKeys(
  folderMetricKeys: readonly string[] | undefined,
  similarityActive: boolean,
  similarityItems: readonly BrowseItemPayload[],
  requiredMetricKeys: readonly string[] = [],
): string[] {
  if (!similarityActive) return folderMetricKeys ? folderMetricKeys.filter((key) => !isDerivedMetricKey(key)) : []
  return collectSimilarityMetricKeys(similarityItems, 250, requiredMetricKeys)
}

export function resolveSelectedMetricKey(
  selectedMetric: string | undefined,
  metricKeys: readonly string[],
  derivedMetricKey: string | null = null,
): string | undefined {
  if (selectedMetric && (metricKeys.includes(selectedMetric) || selectedMetric === derivedMetricKey)) {
    return selectedMetric
  }
  return metricKeys[0]
}

export function shouldResetUnavailableMetricSort(
  sort: SortSpec,
  metricKeys: readonly string[],
  similarityActive: boolean,
  derivedMetricKey: string | null = null,
  derivedMetricStatus: DerivedMetricStatus = 'none',
): boolean {
  if (similarityActive) return false
  if (sort.kind !== 'metric') return false
  if (metricKeys.includes(sort.key)) return false
  if (isDerivedMetricKey(sort.key)) {
    return !(derivedMetricKey === sort.key && derivedMetricStatus !== 'none')
  }
  return true
}

export function resolveCategoricalKeys(
  folderCategoricalKeys: readonly string[] | undefined,
  similarityActive: boolean,
  similarityItems: readonly BrowseItemPayload[],
  requiredCategoricalKeys: readonly string[] = [],
): string[] {
  if (!similarityActive) return folderCategoricalKeys ? [...folderCategoricalKeys] : []
  return collectSimilarityCategoricalKeys(similarityItems, 250, requiredCategoricalKeys)
}

export function resolveDerivedMetricTotalItems(
  searching: boolean,
  similarityActive: boolean,
  loadedCount: number,
  folderTotalItems: number | null | undefined,
): number {
  if (similarityActive || searching) return loadedCount
  return folderTotalItems ?? loadedCount
}

export function buildStarCounts(
  items: readonly BrowseItemPayload[],
  localStarOverrides: Record<string, StarRating>
): Record<string, number> {
  const counts: Record<string, number> = { '0': 0, '1': 0, '2': 0, '3': 0, '4': 0, '5': 0 }
  for (const item of items) {
    const star = localStarOverrides[item.path] ?? item.star ?? 0
    const key = String(star)
    counts[key] = (counts[key] || 0) + 1
  }
  return counts
}

export function getDisplayItemCount(
  similarityActive: boolean,
  showFilteredCounts: boolean,
  filteredCount: number,
  scopeTotal: number
): number {
  if (similarityActive) return filteredCount
  return showFilteredCounts ? filteredCount : scopeTotal
}

export function getDisplayTotalCount(
  similarityActive: boolean,
  showFilteredCounts: boolean,
  totalCount: number,
  scopeTotal: number,
  rootTotal: number,
  current: string
): number {
  if (similarityActive) return totalCount
  if (showFilteredCounts) return scopeTotal
  return current === '/' ? scopeTotal : rootTotal
}

export function getSimilarityQueryLabel(similarityState: SimilarityStateLike): string | null {
  if (!similarityState) return null
  if (similarityState.queryPath) {
    const parts = similarityState.queryPath.split('/').filter(Boolean)
    return parts.length ? parts[parts.length - 1] : similarityState.queryPath
  }
  if (similarityState.queryVector) return 'Vector query'
  return null
}

export function getSimilarityCountLabel(
  similarityActive: boolean,
  activeFilterCount: number,
  filteredCount: number,
  totalCount: number
): string | null {
  if (!similarityActive) return null
  if (activeFilterCount > 0) return `${filteredCount} of ${totalCount}`
  return `${totalCount}`
}
