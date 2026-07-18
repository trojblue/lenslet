import { describe, expect, it, vi } from 'vitest'
import { ThumbnailObjectUrlCache } from '../thumbnailObjectUrlCache'

function createCache(maxEntries = 2, maxBytes = 10) {
  let sequence = 0
  const revokeObjectURL = vi.fn()
  const cache = new ThumbnailObjectUrlCache(
    { maxEntries, maxBytes },
    {
      createObjectURL: () => `blob:test-${sequence += 1}`,
      revokeObjectURL,
    },
  )
  return { cache, revokeObjectURL }
}

describe('ThumbnailObjectUrlCache', () => {
  it('reuses one URL and decoded state across zero-ref remounts', () => {
    const { cache, revokeObjectURL } = createCache()
    const blob = new Blob(['abc'])
    const first = cache.acquire('/a.jpg', blob)
    first.markDecoded()
    const url = first.url
    first.release()

    const second = cache.acquireExisting('/a.jpg')
    expect(second?.url).toBe(url)
    expect(second?.decoded).toBe(true)
    second?.release()
    expect(revokeObjectURL).not.toHaveBeenCalled()
  })

  it('never evicts active entries and trims temporary overflow after release', () => {
    const { cache, revokeObjectURL } = createCache(1, 3)
    const active = cache.acquire('/a.jpg', new Blob(['aaa']))
    const overflow = cache.acquire('/b.jpg', new Blob(['bbb']))

    expect(cache.getSize()).toBe(2)
    overflow.release()
    expect(cache.getSize()).toBe(1)
    const reacquired = cache.acquireExisting('/a.jpg')
    expect(reacquired?.url).toBe(active.url)
    reacquired?.release()
    expect(revokeObjectURL).toHaveBeenCalledWith(overflow.url)
    active.release()
  })

  it('defers invalidation revocation until the last lease releases', () => {
    const { cache, revokeObjectURL } = createCache()
    const lease = cache.acquire('/folder/a.jpg', new Blob(['a']))
    cache.evictPrefix('/folder')

    expect(cache.acquireExisting('/folder/a.jpg')).toBeNull()
    expect(revokeObjectURL).not.toHaveBeenCalled()
    lease.release()
    lease.release()
    expect(revokeObjectURL).toHaveBeenCalledTimes(1)
  })

  it('replaces a key with a new URL and fresh decoded state', () => {
    const { cache, revokeObjectURL } = createCache()
    const first = cache.acquire('/a.jpg', new Blob(['a']))
    first.markDecoded()
    first.release()
    const second = cache.acquire('/a.jpg', new Blob(['b']))

    expect(second.url).not.toBe(first.url)
    expect(second.decoded).toBe(false)
    expect(revokeObjectURL).toHaveBeenCalledWith(first.url)
    second.release()
  })
})
