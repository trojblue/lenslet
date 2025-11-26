import type { Item } from '../../../lib/types'
import { byStars } from './filters'
import { sortByAdded, sortByName } from './sorters'

export function applyFilters(items: Item[], stars: number[] | null) {
  return items.filter(byStars(stars))
}

export function applySort(items: Item[], kind: 'name'|'added', dir: 'asc'|'desc') {
  const cmp = kind === 'name' ? sortByName : sortByAdded
  const arr = [...items].sort(cmp)
  return dir === 'desc' ? arr.reverse() : arr
}


