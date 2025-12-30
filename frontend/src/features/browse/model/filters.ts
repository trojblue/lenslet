import type { FilterAST, FilterClause, Item } from '../../../lib/types'

export function applyFilterAst(items: Item[], filters: FilterAST | null): Item[] {
  if (!filters || !filters.and.length) return items
  return items.filter((it) => matchesAll(it, filters.and))
}

function matchesAll(item: Item, clauses: FilterClause[]): boolean {
  for (const clause of clauses) {
    if (!matchesClause(item, clause)) return false
  }
  return true
}

function matchesClause(item: Item, clause: FilterClause): boolean {
  if ('stars' in clause) {
    const active = clause.stars
    if (!active || !active.length) return true
    const val = item.star ?? 0
    return active.includes(val)
  }
  if ('metricRange' in clause) {
    const { key, min, max } = clause.metricRange
    const raw = item.metrics?.[key]
    if (raw == null) return false
    if (raw < min) return false
    if (raw > max) return false
    return true
  }
  return true
}

export function getStarFilter(filters: FilterAST): number[] {
  const clause = filters.and.find((c) => 'stars' in c) as { stars: number[] } | undefined
  return clause?.stars ?? []
}

export function setStarFilter(filters: FilterAST, stars: number[]): FilterAST {
  const rest = filters.and.filter((c) => !('stars' in c))
  if (!stars.length) return { and: rest }
  return { and: [{ stars }, ...rest] }
}

export function getMetricRangeFilter(filters: FilterAST, key: string): { min: number; max: number } | null {
  const clause = filters.and.find((c) => 'metricRange' in c && c.metricRange.key === key) as
    | { metricRange: { key: string; min: number; max: number } }
    | undefined
  return clause?.metricRange ?? null
}

export function setMetricRangeFilter(
  filters: FilterAST,
  key: string,
  range: { min: number; max: number } | null
): FilterAST {
  const rest = filters.and.filter((c) => !('metricRange' in c && c.metricRange.key === key))
  if (!range) return { and: rest }
  return { and: [{ metricRange: { key, min: range.min, max: range.max } }, ...rest] }
}

export function countActiveFilters(filters: FilterAST): number {
  return filters.and.length
}

