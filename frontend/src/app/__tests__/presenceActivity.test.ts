import { describe, expect, it } from 'vitest'
import type { Item } from '../../lib/types'
import { buildRecentSummary, buildRecentTouchesDisplay, type RecentActivity } from '../presenceActivity'

function makeItem(path: string, name: string): Item {
  return {
    path,
    name,
    type: 'image/jpeg',
    w: 100,
    h: 100,
    size: 1,
    hasThumb: true,
    hasMeta: true,
  }
}

describe('presenceActivity helpers', () => {
  it('builds an off-view summary with unique paths and display labels', () => {
    const activity: RecentActivity[] = [
      { path: '/set/cat.jpg', ts: 10, kind: 'item-updated' },
      { path: '/set/cat.jpg', ts: 11, kind: 'metrics-updated' },
      { path: '/set/dog.jpg', ts: 12, kind: 'item-updated' },
      { path: '/set/missing.jpg', ts: 13, kind: 'item-updated' },
    ]
    const items = [
      makeItem('/set/cat.jpg', 'cat'),
      makeItem('/set/dog.jpg', 'dog'),
    ]

    expect(buildRecentSummary(activity, items)).toEqual({
      count: 3,
      names: ['cat', 'dog'],
      extra: 1,
    })
  })

  it('returns null summary for empty off-view activity', () => {
    expect(buildRecentSummary([], [makeItem('/set/cat.jpg', 'cat')])).toBeNull()
  })

  it('formats recent touch rows with item names and fallback labels', () => {
    const activity: RecentActivity[] = [
      { path: '/set/cat.jpg', ts: 1000, kind: 'item-updated' },
      { path: '/set/unknown.jpg', ts: 2000, kind: 'metrics-updated' },
    ]
    const items = [makeItem('/set/cat.jpg', 'cat')]

    const rows = buildRecentTouchesDisplay(activity, items, 5000, (ts, now) => `${now - ts}ms`)
    expect(rows).toEqual([
      { path: '/set/cat.jpg', label: 'cat', timeLabel: '4000ms' },
      { path: '/set/unknown.jpg', label: 'unknown.jpg', timeLabel: '3000ms' },
    ])
  })
})
