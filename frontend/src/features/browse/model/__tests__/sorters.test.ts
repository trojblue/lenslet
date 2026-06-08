import { describe, it, expect } from 'vitest'
import { sortByMetric } from '../sorters'
import { applySort } from '../apply'
import type { BrowseItemPayload } from '../../../../lib/types'

const baseItem = (overrides: Partial<BrowseItemPayload>): BrowseItemPayload => ({
  path: 'a',
  name: 'a',
  mime: 'image/jpeg',
  width: 0,
  height: 0,
  size: 0,
  has_thumbnail: true,
  has_metadata: true,
  ...overrides,
})

const metricItems = (): BrowseItemPayload[] => [
  baseItem({ path: 'a', name: 'a', metrics: { score: 0.2 } }),
  baseItem({ path: 'b', name: 'b', metrics: {} }),
  baseItem({ path: 'c', name: 'c', metrics: { score: Number.NaN } }),
  baseItem({ path: 'd', name: 'd', metrics: { score: 0.9 } }),
  baseItem({ path: 'e', name: 'e', metrics: { score: Number.POSITIVE_INFINITY } }),
  baseItem({ path: 'f', name: 'f', metrics: { score: Number.NEGATIVE_INFINITY } }),
  baseItem({ path: 'g', name: 'g', metrics: { score: null } }),
]

describe('sortByMetric', () => {
  it('sorts ascending and places missing or non-finite values last', () => {
    const items = metricItems()
    const sorted = [...items].sort(sortByMetric('score'))
    expect(sorted.map((i) => i.path)).toEqual(['a', 'd', 'b', 'c', 'e', 'f', 'g'])
  })

  it('sorts descending and still places missing or non-finite values last', () => {
    const items = metricItems()
    const sorted = [...items].sort(sortByMetric('score', 'desc'))
    expect(sorted.map((i) => i.path)).toEqual(['d', 'a', 'b', 'c', 'e', 'f', 'g'])
  })

  it('keeps invalid metric values last when applySort handles descending direction', () => {
    const items = metricItems()
    const sorted = applySort(items, { kind: 'metric', key: 'score', dir: 'desc' })
    expect(sorted.map((i) => i.path)).toEqual(['d', 'a', 'b', 'c', 'e', 'f', 'g'])
  })
})
