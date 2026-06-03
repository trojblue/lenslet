import { describe, expect, it } from 'vitest'
import type { BrowseItemPayload } from '../../../../lib/types'
import {
  collectCategoricalBucketsByKey,
  getCategoricalBuckets,
} from '../categoricalValues'

function makeItem(categoricals?: Record<string, string>): BrowseItemPayload {
  return {
    path: '/tmp/example.jpg',
    name: 'example.jpg',
    mime: 'image/jpeg',
    width: 1,
    height: 1,
    size: 1,
    has_thumbnail: false,
    has_metadata: false,
    categoricals,
  }
}

describe('categorical value utilities', () => {
  it('collects categorical counts by key', () => {
    const bucketsByKey = collectCategoricalBucketsByKey(
      [
        makeItem({ style: 'anime' }),
        makeItem({ style: 'photographic' }),
        makeItem({ style: 'anime' }),
      ],
      [
        makeItem({ style: 'anime' }),
      ],
      [
        makeItem({ style: 'photographic' }),
      ],
      ['style'],
    )

    expect(getCategoricalBuckets(bucketsByKey, 'style')).toEqual([
      { value: 'anime', populationCount: 2, filteredCount: 1, selectedCount: 0 },
      { value: 'photographic', populationCount: 1, filteredCount: 0, selectedCount: 1 },
    ])
  })
})
