import { describe, it, expect } from 'vitest'
import { applyFilterAst, setMetricRangeFilter, setStarFilter } from '../filters'
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

describe('filter AST', () => {
  it('filters by star ratings', () => {
    const items = [
      baseItem({ path: 'a', star: 5 }),
      baseItem({ path: 'b', star: 3 }),
      baseItem({ path: 'c', star: 0 }),
    ]
    const filters = setStarFilter({ and: [] }, [5])
    const result = applyFilterAst(items, filters)
    expect(result.map((i) => i.path)).toEqual(['a'])
  })

  it('filters by metric range', () => {
    const items = [
      baseItem({ path: 'a', metrics: { score: 0.9 } }),
      baseItem({ path: 'b', metrics: { score: 0.4 } }),
      baseItem({ path: 'c', metrics: { score: null } }),
    ]
    const filters = setMetricRangeFilter({ and: [] }, 'score', { min: 0.5, max: 1.0 })
    const result = applyFilterAst(items, filters)
    expect(result.map((i) => i.path)).toEqual(['a'])
  })
})
