import type { BrowseItemPayload } from '../../../lib/types'

export type Comparator<T> = (a: T, b: T) => number

function getAddedMs(item: BrowseItemPayload): number {
  return item.addedAt ? Date.parse(item.addedAt) : 0
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

export function sortByMetric(key: string): Comparator<BrowseItemPayload> {
  return (a, b) => {
    const va = a.metrics?.[key]
    const vb = b.metrics?.[key]
    if (va == null && vb == null) return sortByName(a, b)
    if (va == null) return 1
    if (vb == null) return -1
    if (va === vb) return sortByName(a, b)
    return va - vb
  }
}
