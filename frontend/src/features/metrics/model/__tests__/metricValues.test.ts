import { describe, expect, it } from 'vitest'
import type { BrowseItemPayload } from '../../../../lib/types'
import {
  collectMetricCategoriesByKey,
  collectMetricValuesByKey,
  getMetricCategories,
  getMetricValues,
} from '../metricValues'

function makeItem(
  metrics?: Record<string, number | null>,
  metricLabels?: Record<string, string>,
): BrowseItemPayload {
  return {
    path: '/tmp/example.jpg',
    name: 'example.jpg',
    mime: 'image/jpeg',
    width: 1,
    height: 1,
    size: 1,
    has_thumbnail: false,
    has_metadata: false,
    metrics,
    metric_labels: metricLabels,
  }
}

describe('metrics value map utilities', () => {
  it('collects values by metric key and drops null or non-finite inputs', () => {
    const valuesByKey = collectMetricValuesByKey([
      makeItem({ score: 1.2, quality: 0.9 }),
      makeItem({ score: null, quality: Number.NaN }),
      makeItem({ score: Number.POSITIVE_INFINITY, quality: Number.NEGATIVE_INFINITY }),
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
        makeItem({ score: Number.POSITIVE_INFINITY }),
        makeItem({ score: Number.NEGATIVE_INFINITY }),
        makeItem({ score: 4 }),
        makeItem(),
      ],
      ['score']
    )

    expect(getMetricValues(valuesByKey, 'score')).toEqual([1.2, 4])
  })

  it('collects category counts by metric key', () => {
    const categoriesByKey = collectMetricCategoriesByKey(
      [
        makeItem({ style: 0 }, { style: 'anime' }),
        makeItem({ style: 1 }, { style: 'photographic' }),
        makeItem({ style: 0 }, { style: 'anime' }),
        makeItem({ style: Number.POSITIVE_INFINITY }, { style: 'invalid' }),
      ],
      [
        makeItem({ style: 0 }, { style: 'anime' }),
        makeItem({ style: Number.NaN }, { style: 'invalid' }),
      ],
      [
        makeItem({ style: 1 }, { style: 'photographic' }),
        makeItem({ style: Number.NEGATIVE_INFINITY }, { style: 'invalid' }),
      ],
      ['style'],
    )

    expect(getMetricCategories(categoriesByKey, 'style')).toEqual([
      { code: 0, label: 'anime', populationCount: 2, filteredCount: 1, selectedCount: 0 },
      { code: 1, label: 'photographic', populationCount: 1, filteredCount: 0, selectedCount: 1 },
    ])
  })
})
