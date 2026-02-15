import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'
import { api } from '../client'
import { fileCache, thumbCache } from '../../lib/blobCache'
import { resetBrowseRequestBudgetForTests, runWithRequestBudget } from '../requestBudget'

function resetPrefetchTestState(): void {
  fileCache.clear()
  thumbCache.clear()
  resetBrowseRequestBudgetForTests()
  vi.restoreAllMocks()
}

describe('file prefetch api contract', () => {
  beforeEach(resetPrefetchTestState)
  afterEach(resetPrefetchTestState)

  it('skips prefetch for non-viewer/non-compare contexts', async () => {
    const fetchSpy = vi.spyOn(globalThis, 'fetch')

    await api.prefetchFile('/a.jpg', 'invalid' as any)

    expect(fetchSpy).not.toHaveBeenCalled()
    expect(fileCache.has('/a.jpg')).toBe(false)
  })

  it('sends prefetch context header and caches the blob when successful', async () => {
    const fetchSpy = vi.spyOn(globalThis, 'fetch').mockResolvedValue(
      new Response(new Blob([new Uint8Array([1, 2, 3])]), { status: 200, headers: { 'content-type': 'image/jpeg' } }),
    )

    await api.prefetchFile('/b.jpg', 'viewer')

    expect(fetchSpy).toHaveBeenCalledTimes(1)
    const [url, init] = fetchSpy.mock.calls[0]
    expect(String(url)).toContain('/file?path=%2Fb.jpg')
    expect((init?.headers as Record<string, string>)['x-lenslet-prefetch']).toBe('viewer')
    expect(fileCache.has('/b.jpg')).toBe(true)
  })

  it('does not refetch when file is already cached', async () => {
    fileCache.set('/c.jpg', new Blob([new Uint8Array([9])]))
    const fetchSpy = vi.spyOn(globalThis, 'fetch')

    await api.prefetchFile('/c.jpg', 'compare')

    expect(fetchSpy).not.toHaveBeenCalled()
  })
})

describe('thumb prefetch api contract', () => {
  beforeEach(resetPrefetchTestState)
  afterEach(resetPrefetchTestState)

  it('prefetches thumbnails when thumb queue is healthy', async () => {
    const fetchSpy = vi.spyOn(globalThis, 'fetch').mockResolvedValue(
      new Response(new Blob([new Uint8Array([7, 8, 9])]), { status: 200, headers: { 'content-type': 'image/webp' } }),
    )

    api.prefetchThumb('/thumb-ok.webp')
    await Promise.resolve()

    expect(fetchSpy).toHaveBeenCalledTimes(1)
    expect(String(fetchSpy.mock.calls[0][0])).toContain('/thumb?path=%2Fthumb-ok.webp')
  })

  it('skips thumbnail prefetch when thumb queue is saturated', async () => {
    const fetchSpy = vi.spyOn(globalThis, 'fetch').mockResolvedValue(
      new Response(new Blob([new Uint8Array([1])]), { status: 200, headers: { 'content-type': 'image/webp' } }),
    )

    const blockers = Array.from({ length: 300 }, (_, idx) => {
      const task = runWithRequestBudget('thumb', () => ({
        promise: new Promise<Blob>(() => {}),
      }))
      task.promise.catch(() => {
        // Ignore cleanup cancellation rejections in test.
      })
      return task
    })

    api.prefetchThumb('/thumb-skip.webp')
    await Promise.resolve()

    expect(fetchSpy).not.toHaveBeenCalled()

    for (const task of blockers) {
      task.abort?.()
    }
  })
})
