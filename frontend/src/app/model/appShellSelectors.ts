import type { Item, StarRating } from '../../lib/types'

type SimilarityStateLike = {
  queryPath: string | null
  queryVector: string | null
} | null

export function hasMetricSortValues(items: readonly Item[], metricSortKey: string | null): boolean {
  if (!metricSortKey) return false
  return items.some((item) => {
    const raw = item.metrics?.[metricSortKey]
    return raw != null && !Number.isNaN(raw)
  })
}

export function buildStarCounts(
  items: readonly Item[],
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

export function collectMetricKeys(items: readonly Item[], scanLimit = 250): string[] {
  const keys = new Set<string>()
  let scanned = 0
  for (const item of items) {
    const metrics = item.metrics
    if (metrics) {
      for (const key of Object.keys(metrics)) {
        keys.add(key)
      }
    }
    scanned += 1
    if (scanned >= scanLimit && keys.size > 0) break
  }
  return Array.from(keys).sort()
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
