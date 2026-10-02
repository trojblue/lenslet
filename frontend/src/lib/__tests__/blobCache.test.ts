import { describe, expect, it, vi } from 'vitest'
import { BlobLRUCache } from '../blobCache'

function pendingBlob() {
  let resolve!: (blob: Blob) => void
  let reject!: (error: Error) => void
  const promise = new Promise<Blob>((yes, no) => {
    resolve = yes
    reject = no
  })
  return { promise, resolve, reject, abort: vi.fn() }
}

const invalidations = [
  ['cancel', (cache: BlobLRUCache) => cache.cancelPrefetch('/folder/image')],
  ['clear', (cache: BlobLRUCache) => cache.clear()],
  ['refresh folder', (cache: BlobLRUCache) => cache.evictPrefix('/folder')],
] as const

describe('blob cache request ownership', () => {
  it.each(invalidations)('%s prevents a late completion from repopulating the cache', async (_name, invalidate) => {
    const cache = new BlobLRUCache(1024)
    const request = pendingBlob()
    const result = cache.getOrFetch('/folder/image', () => request)
    invalidate(cache)
    const stale = new Blob(['stale'])
    request.resolve(stale)

    // A fetch that cannot be aborted may still fulfill its original consumer.
    await expect(result).resolves.toBe(stale)
    expect(request.abort).toHaveBeenCalledOnce()
    expect(cache.has('/folder/image')).toBe(false)
    expect(cache.getTotalBytes()).toBe(0)
  })

  it.each(['resolve', 'reject'] as const)('old %s leaves a replacement request deduplicated', async (settlement) => {
    const cache = new BlobLRUCache(1024)
    const oldRequest = pendingBlob()
    const oldResult = cache.getOrFetch('/folder/image', () => oldRequest).catch(() => undefined)
    cache.cancelPrefetch('/folder/image')
    const newRequest = pendingBlob()
    const newResult = cache.getOrFetch('/folder/image', () => newRequest)
    if (settlement === 'resolve') oldRequest.resolve(new Blob(['stale']))
    else oldRequest.reject(new Error('aborted'))
    await oldResult

    const redundantFetch = vi.fn(() => Promise.resolve(new Blob(['redundant'])))
    expect(cache.getOrFetch('/folder/image', redundantFetch)).toBe(newResult)
    expect(redundantFetch).not.toHaveBeenCalled()
    const fresh = new Blob(['fresh'])
    newRequest.resolve(fresh)
    await expect(newResult).resolves.toBe(fresh)
    expect(cache.get('/folder/image')).toBe(fresh)
    expect(cache.getTotalBytes()).toBe(fresh.size)
  })

  it('does not overwrite a completed replacement with an older response', async () => {
    const cache = new BlobLRUCache(1024)
    const oldRequest = pendingBlob()
    const oldResult = cache.getOrFetch('/folder/image', () => oldRequest)
    cache.clear()
    const fresh = new Blob(['fresh image'])
    await cache.getOrFetch('/folder/image', () => Promise.resolve(fresh))
    oldRequest.resolve(new Blob(['old']))
    await oldResult
    expect(cache.get('/folder/image')).toBe(fresh)
    expect(cache.getTotalBytes()).toBe(fresh.size)
  })

  it('shares prefetch failure truthfully with foreground consumers and permits retry', async () => {
    const cache = new BlobLRUCache(1024)
    const request = pendingBlob()
    cache.prefetch('/image', () => request)
    const duplicate = vi.fn(() => Promise.resolve(new Blob(['duplicate'])))
    const foreground = cache.getOrFetch('/image', duplicate)
    const failure = new Error('network failed')
    request.reject(failure)
    await expect(foreground).rejects.toBe(failure)
    expect(duplicate).not.toHaveBeenCalled()
    expect(cache.has('/image')).toBe(false)
    const retry = new Blob(['retry'])
    await expect(cache.getOrFetch('/image', () => Promise.resolve(retry))).resolves.toBe(retry)
  })

  it('ignores synchronous prefetch errors without occupying a cache slot', () => {
    const cache = new BlobLRUCache(1024)
    expect(() => cache.prefetch('/image', () => { throw new Error('offline') })).not.toThrow()
    expect(cache.isInflight('/image')).toBe(false)
  })

  it('invalidates ownership before invoking an abort callback that starts a replacement', async () => {
    const cache = new BlobLRUCache(1024)
    const oldRequest = pendingBlob()
    const replacement = pendingBlob()
    let replacementResult: Promise<Blob> | undefined
    oldRequest.abort.mockImplementation(() => {
      replacementResult = cache.getOrFetch('/folder/image', () => replacement)
    })
    const oldResult = cache.getOrFetch('/folder/image', () => oldRequest)
    cache.cancelPrefetch('/folder/image')
    expect(replacementResult).not.toBe(oldResult)
    expect(cache.isInflight('/folder/image')).toBe(true)
    const fresh = new Blob(['fresh'])
    replacement.resolve(fresh)
    await expect(replacementResult).resolves.toBe(fresh)
    oldRequest.resolve(new Blob(['old']))
    await oldResult
    expect(cache.get('/folder/image')).toBe(fresh)
  })
})
