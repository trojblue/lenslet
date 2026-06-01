import { afterEach, describe, expect, it, vi } from 'vitest'
import { api, buildFolderQuery } from '../client'
import {
  folderQueryKey,
  shouldRemoveRecursiveFolderQuery,
  shouldRetainRecursiveFolderQuery,
  type UseFolderOptions,
} from '../folders'

afterEach(() => {
  vi.restoreAllMocks()
})

describe('folder api query helpers', () => {
  it('builds recursive query params', () => {
    const query = buildFolderQuery('/shots', { recursive: true })
    const params = new URLSearchParams(query)

    expect(params.get('path')).toBe('/shots')
    expect(params.get('recursive')).toBe('1')
  })

  it('builds recursive count-only query params', () => {
    const query = buildFolderQuery('/shots', { recursive: true, countOnly: true })
    const params = new URLSearchParams(query)

    expect(params.get('recursive')).toBe('1')
    expect(params.get('count_only')).toBe('1')
  })

  it('fetches folder paths from the dedicated endpoint', async () => {
    const fetchSpy = vi.spyOn(globalThis, 'fetch').mockResolvedValue(
      new Response(
        JSON.stringify({ paths: ['/', '/shots', '/shots/day-1'] }),
        { status: 200, headers: { 'content-type': 'application/json' } },
      ),
    )

    await expect(api.getFolderPaths()).resolves.toEqual({
      paths: ['/', '/shots', '/shots/day-1'],
    })
    expect(fetchSpy).toHaveBeenCalledTimes(1)
    expect(String(fetchSpy.mock.calls[0][0])).toContain('/folders/paths')
  })

  it('fetches recursive folder counts as numbers', async () => {
    const fetchSpy = vi.spyOn(globalThis, 'fetch').mockResolvedValue(
      new Response(
        JSON.stringify({ path: '/shots', generated_at: 1, items: [], folders: [], total_items: 42 }),
        { status: 200, headers: { 'content-type': 'application/json' } },
      ),
    )

    await expect(api.getFolderCount('/shots')).resolves.toBe(42)
    const url = new URL(String(fetchSpy.mock.calls[0][0]), 'http://localhost')
    expect(url.pathname).toBe('/folders')
    expect(url.searchParams.get('path')).toBe('/shots')
    expect(url.searchParams.get('recursive')).toBe('1')
    expect(url.searchParams.get('count_only')).toBe('1')
  })

  it('separates recursive cache keys from non-recursive', () => {
    expect(folderQueryKey('/shots', { recursive: true })).toEqual(['folder', '/shots', 'recursive'])
    expect(folderQueryKey('/shots', { recursive: false })).toEqual(['folder', '/shots'])
  })

  it('keeps useFolder options scoped to recursive loading and query enablement', () => {
    const options = {
      recursive: true,
      enabled: false,
    } satisfies UseFolderOptions

    expect(folderQueryKey('/shots', options)).toEqual(['folder', '/shots', 'recursive'])
  })

  it('retains only current/root recursive queries', () => {
    expect(shouldRetainRecursiveFolderQuery(['folder', '/shots', 'recursive'], '/shots')).toBe(true)
    expect(shouldRetainRecursiveFolderQuery(['folder', '/', 'recursive'], '/shots')).toBe(true)
    expect(shouldRetainRecursiveFolderQuery(['folder', '/other', 'recursive'], '/shots')).toBe(false)
    expect(shouldRetainRecursiveFolderQuery(['folder', '/', 'recursive'], '/shots', false)).toBe(false)
  })

  it('removes only stale recursive folder queries', () => {
    expect(shouldRemoveRecursiveFolderQuery(['folder', '/shots', 'recursive'], '/shots')).toBe(false)
    expect(shouldRemoveRecursiveFolderQuery(['folder', '/other', 'recursive'], '/shots')).toBe(true)
    expect(shouldRemoveRecursiveFolderQuery(['folder', '/shots'], '/shots')).toBe(false)
    expect(shouldRemoveRecursiveFolderQuery(['search', '/shots'], '/shots')).toBe(false)
    expect(shouldRemoveRecursiveFolderQuery('folder', '/shots')).toBe(false)
  })
})
