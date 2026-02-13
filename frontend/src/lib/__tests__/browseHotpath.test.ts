import { beforeEach, describe, expect, it } from 'vitest'
import {
  completeBrowseHydration,
  getBrowseHotpathSnapshot,
  markFirstGridItemVisible,
  markFirstThumbnailRendered,
  reportBrowseRequestBudget,
  resetBrowseHotpathForTests,
  startBrowseHydration,
  updateBrowseHydration,
} from '../browseHotpath'

beforeEach(() => {
  resetBrowseHotpathForTests()
})

describe('browse hotpath instrumentation', () => {
  it('records hydration progress and completion', () => {
    startBrowseHydration({
      requestId: 7,
      path: '/',
      loadedPages: 1,
      totalPages: 4,
      loadedItems: 200,
      totalItems: 800,
    })

    let snapshot = getBrowseHotpathSnapshot()
    expect(snapshot.hydration).toMatchObject({
      requestId: 7,
      path: '/',
      loadedPages: 1,
      totalPages: 4,
      loadedItems: 200,
      totalItems: 800,
      completed: false,
    })

    updateBrowseHydration({
      requestId: 7,
      path: '/',
      loadedPages: 2,
      totalPages: 4,
      loadedItems: 400,
      totalItems: 800,
    })
    completeBrowseHydration(7)

    snapshot = getBrowseHotpathSnapshot()
    expect(snapshot.hydration).toMatchObject({
      requestId: 7,
      loadedPages: 2,
      totalPages: 4,
      loadedItems: 400,
      totalItems: 800,
      completed: true,
    })
  })

  it('captures first-thumbnail latency once per hydration request', () => {
    startBrowseHydration({
      requestId: 9,
      path: '/gallery',
      loadedPages: 1,
      totalPages: 1,
      loadedItems: 20,
      totalItems: 20,
    })

    markFirstThumbnailRendered('/gallery/a.jpg')
    markFirstThumbnailRendered('/gallery/b.jpg')

    const snapshot = getBrowseHotpathSnapshot()
    expect(snapshot.firstThumbnailPath).toBe('/gallery/a.jpg')
    expect(snapshot.firstThumbnailLatencyMs).not.toBeNull()
    expect((snapshot.firstThumbnailLatencyMs ?? -1) >= 0).toBe(true)
  })

  it('captures first-grid-item latency once per hydration request', () => {
    startBrowseHydration({
      requestId: 12,
      path: '/',
      loadedPages: 1,
      totalPages: 5,
      loadedItems: 200,
      totalItems: 1_000,
    })

    markFirstGridItemVisible('/root/a.jpg')
    markFirstGridItemVisible('/root/b.jpg')

    const snapshot = getBrowseHotpathSnapshot()
    expect(snapshot.firstGridItemPath).toBe('/root/a.jpg')
    expect(snapshot.firstGridItemLatencyMs).not.toBeNull()
    expect((snapshot.firstGridItemLatencyMs ?? -1) >= 0).toBe(true)
  })

  it('stores in-flight request budget counters', () => {
    reportBrowseRequestBudget({
      limits: { folders: 2, thumb: 8, file: 3 },
      inflight: { folders: 1, thumb: 6, file: 2 },
      queued: { folders: 0, thumb: 4, file: 1 },
      peakInflight: { folders: 2, thumb: 8, file: 3 },
      updatedAtMs: 123,
    })

    expect(getBrowseHotpathSnapshot().requestBudget).toMatchObject({
      inflight: { folders: 1, thumb: 6, file: 2 },
      queued: { folders: 0, thumb: 4, file: 1 },
    })
  })
})
