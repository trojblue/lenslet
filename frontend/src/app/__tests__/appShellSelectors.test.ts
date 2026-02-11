import { describe, expect, it } from 'vitest'
import type { Item } from '../../lib/types'
import {
  buildStarCounts,
  collectMetricKeys,
  getDisplayItemCount,
  getDisplayTotalCount,
  getSimilarityCountLabel,
  getSimilarityQueryLabel,
  hasMetricSortValues,
} from '../model/appShellSelectors'

function makeItem(path: string, options?: { star?: Item['star']; metrics?: Item['metrics'] }): Item {
  return {
    path,
    name: path.split('/').pop() ?? path,
    type: 'image/jpeg',
    w: 100,
    h: 100,
    size: 1,
    hasThumb: true,
    hasMeta: true,
    star: options?.star,
    metrics: options?.metrics,
  }
}

describe('appShellSelectors', () => {
  it('detects whether a metric sort key has numeric values', () => {
    const items = [
      makeItem('/a.jpg', { metrics: { score: null } }),
      makeItem('/b.jpg', { metrics: { score: Number.NaN } }),
      makeItem('/c.jpg', { metrics: { score: 0.42 } }),
    ]

    expect(hasMetricSortValues(items, null)).toBe(false)
    expect(hasMetricSortValues(items, 'other')).toBe(false)
    expect(hasMetricSortValues(items, 'score')).toBe(true)
  })

  it('builds star counts from base stars and local overrides', () => {
    const items = [
      makeItem('/a.jpg', { star: 2 }),
      makeItem('/b.jpg', { star: null }),
      makeItem('/c.jpg', { star: 5 }),
    ]

    const counts = buildStarCounts(items, {
      '/a.jpg': 4,
      '/b.jpg': null,
    })

    expect(counts).toEqual({
      '0': 1,
      '1': 0,
      '2': 0,
      '3': 0,
      '4': 1,
      '5': 1,
    })
  })

  it('collects sorted metric keys and stops scanning when the limit is reached with keys present', () => {
    const items = Array.from({ length: 300 }, (_, index) => {
      if (index === 0) {
        return makeItem(`/item-${index}.jpg`, { metrics: { score: 1, quality: 2 } })
      }
      if (index === 299) {
        return makeItem(`/item-${index}.jpg`, { metrics: { lateKey: 3 } })
      }
      return makeItem(`/item-${index}.jpg`)
    })

    expect(collectMetricKeys(items)).toEqual(['quality', 'score'])
  })

  it('continues scanning past the limit when no metric keys have been found yet', () => {
    const items = Array.from({ length: 300 }, (_, index) => {
      if (index === 260) {
        return makeItem(`/item-${index}.jpg`, { metrics: { score: 1 } })
      }
      return makeItem(`/item-${index}.jpg`)
    })

    expect(collectMetricKeys(items)).toEqual(['score'])
  })

  it('formats display counts for similarity and standard browsing modes', () => {
    expect(getDisplayItemCount(true, false, 12, 90)).toBe(12)
    expect(getDisplayItemCount(false, true, 12, 90)).toBe(12)
    expect(getDisplayItemCount(false, false, 12, 90)).toBe(90)

    expect(getDisplayTotalCount(true, false, 50, 90, 400, '/nested')).toBe(50)
    expect(getDisplayTotalCount(false, true, 50, 90, 400, '/nested')).toBe(90)
    expect(getDisplayTotalCount(false, false, 50, 90, 400, '/nested')).toBe(400)
    expect(getDisplayTotalCount(false, false, 50, 90, 400, '/')).toBe(90)
  })

  it('formats similarity labels from query path/vector and active filter state', () => {
    expect(getSimilarityQueryLabel({ queryPath: '/set/cat.jpg', queryVector: null })).toBe('cat.jpg')
    expect(getSimilarityQueryLabel({ queryPath: null, queryVector: 'abc' })).toBe('Vector query')
    expect(getSimilarityQueryLabel({ queryPath: null, queryVector: null })).toBeNull()
    expect(getSimilarityQueryLabel(null)).toBeNull()

    expect(getSimilarityCountLabel(false, 0, 3, 10)).toBeNull()
    expect(getSimilarityCountLabel(true, 0, 3, 10)).toBe('10')
    expect(getSimilarityCountLabel(true, 2, 3, 10)).toBe('3 of 10')
  })
})
