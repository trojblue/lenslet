import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'
import {
  getBrowseHotpathSnapshot,
  markFirstGridItemVisible,
  markFirstThumbnailRendered,
  reportBrowseRequestBudget,
  resetBrowseHotpathForTests,
  startBrowseLoad,
} from '../browseHotpath'

beforeEach(() => {
  resetBrowseHotpathForTests()
})

afterEach(() => {
  delete (globalThis as { window?: unknown }).window
})

describe('browse hotpath instrumentation', () => {
  it('does not publish browser globals during module import', async () => {
    vi.resetModules()
    const windowStub: Window = {} as Window
    Object.defineProperty(globalThis, 'window', {
      configurable: true,
      writable: true,
      value: windowStub,
    })

    await import('../browseHotpath')

    expect(windowStub.__lensletBrowseHotpath).toBeUndefined()
  })

  it('captures first-thumbnail latency once per browse request', () => {
    startBrowseLoad({
      requestId: 9,
      path: '/gallery',
    })

    markFirstThumbnailRendered('/gallery/a.jpg')
    markFirstThumbnailRendered('/gallery/b.jpg')

    const snapshot = getBrowseHotpathSnapshot()
    expect(snapshot.firstThumbnailPath).toBe('/gallery/a.jpg')
    expect(snapshot.firstThumbnailLatencyMs).not.toBeNull()
    expect((snapshot.firstThumbnailLatencyMs ?? -1) >= 0).toBe(true)
  })

  it('captures first-grid-item latency once per browse request', () => {
    startBrowseLoad({
      requestId: 12,
      path: '/',
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
