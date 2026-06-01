import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'
import { api } from '../client'
import { BlobLRUCache, fileCache, thumbCache } from '../../lib/blobCache'
import { resetBrowseRequestBudgetForTests, runWithRequestBudget } from '../requestBudget'

function resetPrefetchTestState(): void {
  fileCache.clear()
  thumbCache.clear()
  resetBrowseRequestBudgetForTests()
  vi.restoreAllMocks()
}

function requireAbortSignal(signal: AbortSignal | null): AbortSignal {
  if (signal === null) {
    throw new Error('expected fetch to receive an abort signal')
  }
  return signal
}

describe('file prefetch api contract', () => {
  beforeEach(resetPrefetchTestState)
  afterEach(resetPrefetchTestState)

  it('skips prefetch for non-viewer/non-compare contexts', async () => {
    const fetchSpy = vi.spyOn(globalThis, 'fetch')

    // @ts-expect-error verifies the runtime guard for malformed callers.
    await api.prefetchFile('/a.jpg', 'invalid')

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

describe('blob cache promise contract', () => {
  it('returns a resolved promise for cache hits without calling the fetcher', async () => {
    const cache = new BlobLRUCache(1024)
    const cached = new Blob([new Uint8Array([1, 2, 3])])
    const fetcher = vi.fn(async () => new Blob([new Uint8Array([9])]))
    cache.set('/cached.jpg', cached)

    const promise = cache.getOrFetch('/cached.jpg', fetcher)

    expect(promise).toBeInstanceOf(Promise)
    await expect(promise).resolves.toBe(cached)
    expect(fetcher).not.toHaveBeenCalled()
  })

  it('converts synchronous fetcher failures into rejected promises', async () => {
    const cache = new BlobLRUCache(1024)

    await expect(
      cache.getOrFetch('/boom.jpg', () => {
        throw new Error('boom')
      }),
    ).rejects.toThrow('boom')
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

  it('fetches hover previews from the original file route without thumb cache use', async () => {
    const fetchSpy = vi.spyOn(globalThis, 'fetch').mockResolvedValue(
      new Response(new Blob([new Uint8Array([4, 5, 6])]), { status: 200, headers: { 'content-type': 'image/jpeg' } }),
    )

    const request = api.getHoverPreview('/hover-preview.jpg')
    const blob = await request.promise

    expect(blob.size).toBe(3)
    expect(fetchSpy).toHaveBeenCalledTimes(1)
    expect(String(fetchSpy.mock.calls[0][0])).toContain('/file?path=%2Fhover-preview.jpg')
    expect(String(fetchSpy.mock.calls[0][0])).not.toContain('/thumb')
    expect(fileCache.has('/hover-preview.jpg')).toBe(false)
    expect(thumbCache.has('/hover-preview.jpg')).toBe(false)
  })

  it('serves hover previews from existing full-file cache without starting a shared abortable request', async () => {
    fileCache.set('/cached-hover.jpg', new Blob([new Uint8Array([7, 8, 9, 10])]))
    const fetchSpy = vi.spyOn(globalThis, 'fetch')

    const request = api.getHoverPreview('/cached-hover.jpg')
    const blob = await request.promise

    expect(blob.size).toBe(4)
    expect(fetchSpy).not.toHaveBeenCalled()
    expect(request.abort).toBeUndefined()
  })

  it('aborts uncached hover file requests without writing to shared caches', async () => {
    let requestSignal: AbortSignal | null = null
    const fetchSpy = vi.spyOn(globalThis, 'fetch').mockImplementation((_url, init) => {
      requestSignal = init?.signal instanceof AbortSignal ? init.signal : null
      return new Promise<Response>((_resolve, reject) => {
        requestSignal?.addEventListener('abort', () => {
          reject(new DOMException('request aborted', 'AbortError'))
        })
      })
    })

    const request = api.getHoverPreview('/abort-hover.jpg')
    request.promise.catch(() => {
      // Expected abort path.
    })
    await Promise.resolve()
    request.abort?.()

    expect(fetchSpy).toHaveBeenCalledTimes(1)
    expect(String(fetchSpy.mock.calls[0][0])).toContain('/file?path=%2Fabort-hover.jpg')
    expect(requireAbortSignal(requestSignal).aborted).toBe(true)
    await expect(request.promise).rejects.toMatchObject({ name: 'AbortError' })
    expect(fileCache.has('/abort-hover.jpg')).toBe(false)
    expect(thumbCache.has('/abort-hover.jpg')).toBe(false)
  })
})
