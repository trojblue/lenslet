import { describe, it, expect } from 'vitest'
import { sortByMetric } from '../sorters'
import type { BrowseItemPayload } from '../../../../lib/types'

const baseItem = (overrides: Partial<BrowseItemPayload>): BrowseItemPayload => ({
  path: 'a',
  name: 'a',
  mime: 'image/jpeg',
  width: 0,
  height: 0,
  size: 0,
  hasThumbnail: true,
  hasMetadata: true,
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
