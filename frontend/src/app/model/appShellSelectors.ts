import type { BrowseItemPayload, FilterAST, SortSpec, StarRating } from '../../lib/types'
import { finiteMetricValue } from '../../lib/metrics'
import {
  isDerivedMetricKey,
  type DerivedMetricEvaluation,
  type DerivedMetricStatus,
} from '../../features/metrics/model/derivedMetric'

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

function derivedMetricKeyIsUsable(
  key: string,
  derivedMetric: DerivedMetricEvaluation,
): boolean {
  return derivedMetric.key === key
    && derivedMetric.status === 'valid'
    && derivedMetric.validCount > 0
}

export function getUnavailableDerivedMetricFilterKeys(
  filters: FilterAST,
  derivedMetric: DerivedMetricEvaluation,
): string[] {
  const keys = new Set<string>()
  for (const clause of filters.and) {
    if (!('metricRange' in clause)) continue
    const key = clause.metricRange.key
    if (!isDerivedMetricKey(key)) continue
    if (!derivedMetricKeyIsUsable(key, derivedMetric)) {
      keys.add(key)
    }
  }
  return Array.from(keys).sort()
}

function formatInputList(keys: readonly string[]): string {
  return keys.length ? keys.join(', ') : 'unknown inputs'
}

export function buildDerivedMetricWarning(
  sort: SortSpec,
  filters: FilterAST,
  derivedMetric: DerivedMetricEvaluation,
): string | null {
  const sortKey = sort.kind === 'metric' && isDerivedMetricKey(sort.key) ? sort.key : null
  const unavailableFilterKeys = getUnavailableDerivedMetricFilterKeys(filters, derivedMetric)
  const referencesDerivedMetric = sortKey !== null || unavailableFilterKeys.length > 0
  if (!referencesDerivedMetric) return null

  const referencedKeys = new Set(unavailableFilterKeys)
  if (sortKey) referencedKeys.add(sortKey)
  const referencesStaleKey = Array.from(referencedKeys).some((key) => key !== derivedMetric.key)

  if (referencesStaleKey) {
    return 'Saved derived score is unavailable in this view.'
  }

  if (derivedMetric.status === 'invalid') {
    return derivedMetric.invalidReasons[0] ?? 'Saved derived score definition is invalid.'
  }

  if (derivedMetric.status === 'unavailable') {
    const missing = [
      ...derivedMetric.missingMetricKeys,
      ...derivedMetric.missingCategoricalKeys,
    ].sort()
    return `Derived score inputs unavailable in this view: ${formatInputList(missing)}.`
  }

  if (derivedMetric.status === 'valid' && derivedMetric.validCount === 0) {
    return 'Derived score has no valid values in this view.'
  }

  if (sortKey && derivedMetric.partialLoadWarning) {
    const total = derivedMetric.totalItems ?? derivedMetric.loadedCount
    return `Derived score ranks only the ${derivedMetric.loadedCount} loaded items out of ${total}.`
  }

  return null
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
