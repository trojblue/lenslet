import { describe, it, expect } from 'vitest'
import { sortByMetric } from '../sorters'
import type { Item } from '../../../../lib/types'

const baseItem = (overrides: Partial<Item>): Item => ({
  path: 'a',
  name: 'a',
  type: 'image/jpeg',
  w: 0,
  h: 0,
  size: 0,
  hasThumb: true,
  hasMeta: true,
  ...overrides,
})

describe('sortByMetric', () => {
  it('sorts ascending and places missing values last', () => {
    const items = [
      baseItem({ path: 'a', name: 'a', metrics: { score: 0.2 } }),
      baseItem({ path: 'b', name: 'b', metrics: {} }),
      baseItem({ path: 'c', name: 'c', metrics: { score: 0.9 } }),
    ]
    const sorted = [...items].sort(sortByMetric('score'))
    expect(sorted.map((i) => i.path)).toEqual(['a', 'c', 'b'])
  })
})
