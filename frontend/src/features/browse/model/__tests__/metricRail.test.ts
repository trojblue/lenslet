import { describe, expect, it } from 'vitest'
import type { BrowseItemPayload } from '../../../../lib/types'
import {
  closestMetricPathForValue,
  computeMetricRailHistogram,
  metricRailProgressFromValue,
  metricValueAtProgress,
  metricValueFromRailProgress,
} from '../metricRail'

function makeItem(path: string, score: number | null): BrowseItemPayload {
  return {
    path,
    name: path.split('/').pop() ?? path,
    mime: 'image/jpeg',
    width: 1,
    height: 1,
    size: 1,
    has_thumbnail: true,
    has_metadata: true,
    metrics: { score },
  }
}

describe('metric rail model', () => {
  it('maps rail progress through the metric value domain in both sort directions', () => {
    const domain = { min: 0, max: 100 }

    expect(metricValueFromRailProgress(0.25, domain, 'asc')).toBe(25)
    expect(metricValueFromRailProgress(0.25, domain, 'desc')).toBe(75)
    expect(metricRailProgressFromValue(25, domain, 'asc')).toBe(0.25)
    expect(metricRailProgressFromValue(75, domain, 'desc')).toBe(0.25)
  })

  it('chooses the nearest metric item instead of treating histogram y as rank progress', () => {
    const items = [
      makeItem('/high.jpg', 100),
      makeItem('/mid.jpg', 65),
      makeItem('/low.jpg', 4),
      makeItem('/missing.jpg', null),
    ]

    expect(closestMetricPathForValue(items, 'score', 63)).toBe('/mid.jpg')
    expect(closestMetricPathForValue(items, 'score', 2)).toBe('/low.jpg')
  })

  it('keeps the scroll marker tied to the nearest visible ordered metric value', () => {
    expect(metricValueAtProgress([100, 80, null, 20], 0.66)).toBe(80)
    expect(metricValueAtProgress([100, 80, null, 20], 0.5)).toBe(80)
  })

  it('builds a value-domain histogram from finite values', () => {
    const histogram = computeMetricRailHistogram([0, 0, 1, 2], 2)

    expect(histogram).toEqual({
      bins: [2, 2],
      min: 0,
      max: 2,
      count: 4,
    })
  })
})
