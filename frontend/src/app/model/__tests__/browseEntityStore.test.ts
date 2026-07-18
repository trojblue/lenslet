import { describe, expect, it, vi } from 'vitest'
import type { BrowseItemPayload } from '../../../lib/types'
import { BrowseEntityStore } from '../browseEntityStore'

function item(path: string, star: BrowseItemPayload['star'] = null): BrowseItemPayload {
  return {
    path,
    name: path,
    mime: 'image/jpeg',
    width: 8,
    height: 6,
    size: 1,
    has_thumbnail: true,
    has_metadata: true,
    star,
  }
}

describe('BrowseEntityStore', () => {
  it('patches one immutable entity and notifies only its path', () => {
    const store = new BrowseEntityStore()
    store.ingest([item('/a.jpg'), item('/b.jpg')])
    const beforeA = store.get('/a.jpg')
    const beforeB = store.get('/b.jpg')
    const onA = vi.fn()
    const onB = vi.fn()
    store.subscribe('/a.jpg', onA)
    store.subscribe('/b.jpg', onB)

    expect(store.patch({ path: '/a.jpg', star: 4 })).toBe(true)

    expect(store.get('/a.jpg')).not.toBe(beforeA)
    expect(store.get('/a.jpg')?.star).toBe(4)
    expect(store.get('/b.jpg')).toBe(beforeB)
    expect(onA).toHaveBeenCalledTimes(1)
    expect(onB).not.toHaveBeenCalled()
  })

  it('ingests duplicate paths deterministically with last value winning', () => {
    const store = new BrowseEntityStore()

    expect(store.ingest([item('/b.jpg'), item('/a.jpg', 1), item('/a.jpg', 3)])).toEqual([
      '/a.jpg',
      '/b.jpg',
    ])
    expect(store.get('/a.jpg')?.star).toBe(3)
  })

  it('seeds missing presentation payloads without replacing live entities', () => {
    const store = new BrowseEntityStore()
    const onA = vi.fn()
    store.ingest([item('/a.jpg', 4)])
    store.subscribe('/a.jpg', onA)

    expect(store.seed([item('/a.jpg', 1), item('/b.jpg', 2)])).toEqual(['/b.jpg'])
    expect(store.get('/a.jpg')?.star).toBe(4)
    expect(store.get('/b.jpg')?.star).toBe(2)
    expect(onA).not.toHaveBeenCalled()
  })

  it('retains fields from cached projection variants while replacing requested keys', () => {
    const store = new BrowseEntityStore()
    const metricA = store.beginRequest({ metric_keys: ['metric_a'], categorical_keys: ['group_a'] })
    store.ingest([{
      ...item('/a.jpg'),
      metrics: { metric_a: 1 },
      categoricals: { group_a: 'one' },
    }], metricA)
    const metricB = store.beginRequest({ metric_keys: ['metric_b'], categorical_keys: ['group_b'] })
    store.ingest([{
      ...item('/a.jpg'),
      metrics: { metric_b: 2 },
      categoricals: { group_b: 'two' },
    }], metricB)

    expect(store.get('/a.jpg')?.metrics).toEqual({ metric_a: 1, metric_b: 2 })
    expect(store.get('/a.jpg')?.categoricals).toEqual({ group_a: 'one', group_b: 'two' })

    const refreshedA = store.beginRequest({ metric_keys: ['metric_a'], categorical_keys: ['group_a'] })
    store.ingest([{
      ...item('/a.jpg'),
      metrics: { metric_a: 3 },
      categoricals: {},
    }], refreshedA)
    expect(store.get('/a.jpg')?.metrics).toEqual({ metric_a: 3, metric_b: 2 })
    expect(store.get('/a.jpg')?.categoricals).toEqual({ group_b: 'two' })
  })

  it('rejects stale request ingestion and preserves patches accepted after request start', () => {
    const store = new BrowseEntityStore()
    store.ingest([item('/a.jpg')])
    const stale = store.beginRequest()
    const fresh = store.beginRequest()
    store.ingest([{ ...item('/a.jpg'), name: 'fresh' }], fresh)
    store.ingest([{ ...item('/a.jpg'), name: 'stale' }], stale)
    expect(store.get('/a.jpg')?.name).toBe('fresh')

    const beforeMutation = store.beginRequest()
    store.patch({ path: '/a.jpg', star: 5 })
    store.ingest([{ ...item('/a.jpg'), name: 'new core', star: null }], beforeMutation)
    expect(store.get('/a.jpg')?.name).toBe('new core')
    expect(store.get('/a.jpg')?.star).toBe(5)
  })

  it('replaces only sidecar-owned metric keys and preserves projected static metrics', () => {
    const store = new BrowseEntityStore()
    store.ingest([{
      ...item('/a.jpg'),
      metrics: { static_score: 0.8, annotation_score: 2 },
      mutable_metric_keys: ['annotation_score'],
    }])

    store.patch(
      { path: '/a.jpg', metrics: { reviewer_score: 4 } },
      { replaceMutableMetrics: true },
    )

    expect(store.get('/a.jpg')?.metrics).toEqual({ static_score: 0.8, reviewer_score: 4 })
    expect(store.get('/a.jpg')?.mutable_metric_keys).toEqual(['reviewer_score'])

    store.patch(
      { path: '/a.jpg', metrics: {} },
      { replaceMutableMetrics: true },
    )
    expect(store.get('/a.jpg')?.metrics).toEqual({ static_score: 0.8 })
    expect(store.get('/a.jpg')?.mutable_metric_keys).toEqual([])
  })

  it('retains active entities and bounds unreferenced entities by count and TTL', () => {
    let now = 0
    const store = new BrowseEntityStore(() => now, 2, 100)
    const owner = {}
    store.setActivePaths(owner, ['/a.jpg'])
    store.ingest([item('/a.jpg'), item('/b.jpg'), item('/c.jpg'), item('/d.jpg')])

    expect(store.get('/a.jpg')).toBeDefined()
    expect(store.evict('/a.jpg')).toBe(false)
    expect(store.size()).toBe(3)

    now = 101
    store.prune()
    expect(store.size()).toBe(1)
    expect(store.get('/a.jpg')).toBeDefined()

    store.release(owner)
    now = 202
    store.prune()
    expect(store.size()).toBe(0)
  })
})
