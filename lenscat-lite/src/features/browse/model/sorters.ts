import type { Item } from '../../../lib/types'

export type Comparator<T> = (a: T, b: T) => number

export const sortByName: Comparator<Item> = (a,b) => a.name.localeCompare(b.name)

export const sortByAdded: Comparator<Item> = (a,b) => {
  const ta = a.addedAt ? Date.parse(a.addedAt) : 0
  const tb = b.addedAt ? Date.parse(b.addedAt) : 0
  if (ta === tb) return sortByName(a,b)
  return ta - tb
}


