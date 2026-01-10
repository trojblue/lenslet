import type { Item } from '../../../lib/types'

export type Comparator<T> = (a: T, b: T) => number

const getAddedMs = (item: Item): number => (item.addedAt ? Date.parse(item.addedAt) : 0)

export function sortByName(a: Item, b: Item): number {
  return a.name.localeCompare(b.name)
}

export function sortByAdded(a: Item, b: Item): number {
  const ta = getAddedMs(a)
  const tb = getAddedMs(b)
  if (ta === tb) return sortByName(a, b)
  return ta - tb
}

export function sortByMetric(key: string): Comparator<Item> {
  return (a, b) => {
    const va = a.metrics?.[key]
    const vb = b.metrics?.[key]
    const aMissing = va == null
    const bMissing = vb == null
    if (aMissing && bMissing) return sortByName(a, b)
    if (aMissing) return 1
    if (bMissing) return -1
    if (va === vb) return sortByName(a, b)
    return (va as number) - (vb as number)
  }
}
