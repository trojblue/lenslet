import type { Item, SortDir, SortKey } from '../../../lib/types'
import { byStars } from './filters'
import { sortByAdded, sortByName } from './sorters'

export function applyFilters(items: Item[], stars: number[] | null) {
  return items.filter(byStars(stars))
}

function mulberry32(seed: number): () => number {
  let t = seed >>> 0
  return () => {
    t += 0x6d2b79f5
    let r = Math.imul(t ^ (t >>> 15), 1 | t)
    r ^= r + Math.imul(r ^ (r >>> 7), 61 | r)
    return ((r ^ (r >>> 14)) >>> 0) / 4294967296
  }
}

function shuffleWithSeed<T>(items: T[], seed: number): T[] {
  const rng = mulberry32(seed || 1)
  const arr = [...items]
  for (let i = arr.length - 1; i > 0; i -= 1) {
    const j = Math.floor(rng() * (i + 1))
    ;[arr[i], arr[j]] = [arr[j], arr[i]]
  }
  return arr
}

export function applySort(items: Item[], kind: SortKey, dir: SortDir, randomSeed?: number) {
  if (kind === 'random') {
    const seed = randomSeed ?? Date.now()
    return shuffleWithSeed(items, seed)
  }

  const cmp = kind === 'name' ? sortByName : sortByAdded
  const arr = [...items].sort(cmp)
  return dir === 'desc' ? arr.reverse() : arr
}

