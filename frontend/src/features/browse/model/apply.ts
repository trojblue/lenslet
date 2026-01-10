import type { FilterAST, Item, SortSpec } from '../../../lib/types'
import { applyFilterAst } from './filters'
import { sortByAdded, sortByMetric, sortByName } from './sorters'

export function applyFilters(items: Item[], filters: FilterAST | null): Item[] {
  return applyFilterAst(items, filters)
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

export function applySort(items: Item[], sort: SortSpec, randomSeed?: number): Item[] {
  if (sort.kind === 'builtin' && sort.key === 'random') {
    const seed = randomSeed ?? Date.now()
    return shuffleWithSeed(items, seed)
  }

  let cmp = sortByAdded
  if (sort.kind === 'metric') {
    cmp = sortByMetric(sort.key)
  } else if (sort.key === 'name') {
    cmp = sortByName
  }
  const arr = [...items].sort(cmp)
  return sort.dir === 'desc' ? arr.reverse() : arr
}
