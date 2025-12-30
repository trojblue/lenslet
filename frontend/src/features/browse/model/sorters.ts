import type { Item } from '../../../lib/types'

export type Comparator<T> = (a: T, b: T) => number

export const sortByName: Comparator<Item> = (a,b) => a.name.localeCompare(b.name)

export const sortByAdded: Comparator<Item> = (a,b) => {
  const ta = a.addedAt ? Date.parse(a.addedAt) : 0
  const tb = b.addedAt ? Date.parse(b.addedAt) : 0
  if (ta === tb) return sortByName(a,b)
  return ta - tb
}

export const sortByMetric = (key: string): Comparator<Item> => {
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

