import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'
import { api } from '../client'
import { fileCache } from '../../lib/blobCache'
import { resetBrowseRequestBudgetForTests } from '../requestBudget'

function resetPrefetchTestState(): void {
  fileCache.clear()
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
