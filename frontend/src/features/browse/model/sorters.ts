import type { BrowseItemPayload } from '../../../lib/types'
import { finiteMetricValue } from '../../../lib/metrics'

export type Comparator<T> = (a: T, b: T) => number
type SortDirection = 'asc' | 'desc'

function getAddedMs(item: BrowseItemPayload): number {
  return item.added_at ? Date.parse(item.added_at) : 0
}

export function sortByName(a: BrowseItemPayload, b: BrowseItemPayload): number {
  return a.name.localeCompare(b.name)
}

export function sortByAdded(a: BrowseItemPayload, b: BrowseItemPayload): number {
  const ta = getAddedMs(a)
  const tb = getAddedMs(b)
  if (ta === tb) return sortByName(a, b)
  return ta - tb
}

export function sortByMetric(key: string, dir: SortDirection = 'asc'): Comparator<BrowseItemPayload> {
  return (a, b) => {
    const va = finiteMetricValue(a.metrics?.[key])
    const vb = finiteMetricValue(b.metrics?.[key])
    if (va == null && vb == null) return sortByName(a, b)
    if (va == null) return 1
    if (vb == null) return -1
    if (va === vb) return sortByName(a, b)
    return dir === 'desc' ? vb - va : va - vb
  }
}
