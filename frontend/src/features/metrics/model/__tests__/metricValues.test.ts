import { describe, expect, it } from 'vitest'
import type { Item } from '../../../../lib/types'
import {
  collectMetricValuesByKey,
  getMetricValues,
} from '../metricValues'

function makeItem(metrics?: Record<string, number | null>): Item {
  return {
    path: '/tmp/example.jpg',
    name: 'example.jpg',
    type: 'image/jpeg',
    w: 1,
    h: 1,
    size: 1,
    hasThumb: false,
    hasMeta: false,
    metrics,
  }
}

describe('metrics value map utilities', () => {
  it('collects values by metric key and drops null/NaN inputs', () => {
    const valuesByKey = collectMetricValuesByKey([
      makeItem({ score: 1.2, quality: 0.9 }),
      makeItem({ score: null, quality: Number.NaN }),
      makeItem({ score: 4.8 }),
      makeItem(),
    ])

    expect(getMetricValues(valuesByKey, 'score')).toEqual([1.2, 4.8])
    expect(getMetricValues(valuesByKey, 'quality')).toEqual([0.9])
    expect(getMetricValues(valuesByKey, 'missing')).toEqual([])
  })

  it('restricts collection to provided metric key set', () => {
    const valuesByKey = collectMetricValuesByKey(
      [
        makeItem({ score: 1, quality: 5 }),
        makeItem({ score: 2, quality: 6 }),
      ],
      ['quality']
    )

    expect(Array.from(valuesByKey.keys())).toEqual(['quality'])
    expect(getMetricValues(valuesByKey, 'quality')).toEqual([5, 6])
    expect(getMetricValues(valuesByKey, 'score')).toEqual([])
  })

  it('collects one scoped key with finite-value filtering', () => {
    const valuesByKey = collectMetricValuesByKey(
      [
        makeItem({ score: 1.2 }),
        makeItem({ score: null }),
        makeItem({ score: Number.NaN }),
        makeItem({ score: 4 }),
        makeItem(),
      ],
      ['score']
    )

    expect(getMetricValues(valuesByKey, 'score')).toEqual([1.2, 4])
  })
})
