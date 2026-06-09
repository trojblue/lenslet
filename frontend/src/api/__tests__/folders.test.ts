import { afterEach, describe, expect, it, vi } from 'vitest'
import { api, buildFolderQuery } from '../client'
import {
  cancelBrowseRequests,
  getBrowseRequestBudgetSnapshot,
  resetBrowseRequestBudgetForTests,
} from '../requestBudget'
import {
  BACKEND_BROWSE_PAGE_SIZE,
  browseQueryKey,
  buildBrowseQueryRequest,
  folderQueryKey,
  shouldRemoveRecursiveFolderQuery,
  shouldRetainRecursiveFolderQuery,
  type BrowseQueryOptions,
  type UseFolderOptions,
} from '../folders'

afterEach(() => {
  vi.restoreAllMocks()
  cancelBrowseRequests()
  resetBrowseRequestBudgetForTests()
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

  it('fetches folder facets from the dedicated endpoint', async () => {
    const fetchSpy = vi.spyOn(globalThis, 'fetch').mockResolvedValue(
      new Response(
        JSON.stringify({
          version: 1,
          path: '/shots',
          generated_at: 'test',
          total_items: 2,
          metric_keys: [],
          categorical_keys: ['original_source'],
          metrics: {},
          categoricals: {
            original_source: {
              values: [{ value: 'gt', population_count: 2 }],
            },
          },
        }),
        { status: 200, headers: { 'content-type': 'application/json' } },
      ),
    )

    await expect(api.getFolderFacets('/shots')).resolves.toMatchObject({
      path: '/shots',
      categoricals: {
        original_source: {
          values: [{ value: 'gt', population_count: 2 }],
        },
      },
    })
    const url = new URL(String(fetchSpy.mock.calls[0][0]), 'http://localhost')
    expect(url.pathname).toBe('/folders/facets')
    expect(url.searchParams.get('path')).toBe('/shots')
    expect(url.searchParams.get('recursive')).toBe('1')
  })

  it('builds canonical browse-query request bodies', () => {
    const request = buildBrowseQueryRequest({
      path: 'shots',
      recursive: true,
      filters: {
        and: [
          { nameContains: { value: ' cat ' } },
          { categoricalIn: { key: 'source_column', values: ['target'] } },
          { starsIn: { values: [] } },
        ],
      },
      sort: { kind: 'metric', key: 'score', dir: 'desc' },
      textQuery: '  tabby   cat ',
      randomSeed: 123,
    })

    expect(request).toEqual({
      path: '/shots',
      recursive: true,
      offset: 0,
      limit: BACKEND_BROWSE_PAGE_SIZE,
      filters: {
        and: [
          { nameContains: { value: 'cat' } },
          { categoricalIn: { key: 'source_column', values: ['target'] } },
        ],
      },
      sort: { kind: 'metric', key: 'score', dir: 'desc' },
      text_query: 'tabby cat',
      random_seed: 123,
    })
  })

  it('keys browse queries by every authoritative request variable', () => {
    const base: BrowseQueryOptions = {
      path: '/shots',
      recursive: true,
      filters: { and: [] },
      sort: { kind: 'builtin', key: 'added', dir: 'desc' },
      textQuery: '',
      randomSeed: 1,
    }

    const key = (overrides: Partial<BrowseQueryOptions> = {}) => (
      JSON.stringify(browseQueryKey({ ...base, ...overrides }))
    )

    expect(key({ path: '/other' })).not.toBe(key())
    expect(key({ filters: { and: [{ categoricalIn: { key: 'source', values: ['target'] } }] } })).not.toBe(key())
    expect(key({ sort: { kind: 'builtin', key: 'name', dir: 'asc' } })).not.toBe(key())
    expect(key({ textQuery: 'cat' })).not.toBe(key())
    expect(key({ randomSeed: 2 })).not.toBe(key())
    expect(key({ unsupportedToken: 'derived-filter' })).not.toBe(key())
    expect(key({ filters: { and: [{ starsIn: { values: [] } }] } })).toBe(key())
  })

  it('posts browse-query requests with abortable folder request budget coverage', async () => {
    resetBrowseRequestBudgetForTests()
    const controller = new AbortController()
    const fetchSpy = vi.spyOn(globalThis, 'fetch').mockImplementation((_url, init) => (
      new Promise<Response>((_resolve, reject) => {
        const signal = init?.signal as AbortSignal
        expect(signal).toBeInstanceOf(AbortSignal)
        signal.addEventListener('abort', () => {
          const error = new Error('aborted')
          error.name = 'AbortError'
          reject(error)
        })
      })
    ))

    const body = buildBrowseQueryRequest({
      path: '/shots',
      recursive: true,
      filters: { and: [] },
      sort: { kind: 'builtin', key: 'added', dir: 'desc' },
      textQuery: 'cat',
      randomSeed: 7,
    })
    const promise = api.queryFolder(body, { signal: controller.signal })

    expect(getBrowseRequestBudgetSnapshot().inflight.folders).toBe(1)
    const [url, init] = fetchSpy.mock.calls[0]
    expect(new URL(String(url), 'http://localhost').pathname).toBe('/folders/query')
    expect(init?.method).toBe('POST')
    expect(JSON.parse(String(init?.body))).toEqual(body)

    controller.abort()
    await expect(promise).rejects.toMatchObject({ name: 'AbortError' })
    expect(getBrowseRequestBudgetSnapshot().inflight.folders).toBe(0)
  })

  it('dequeues browse-query requests when their caller aborts before a budget slot opens', async () => {
    resetBrowseRequestBudgetForTests()
    const fetchSpy = vi.spyOn(globalThis, 'fetch').mockImplementation((_url, init) => (
      new Promise<Response>((_resolve, reject) => {
        const signal = init?.signal as AbortSignal
        signal.addEventListener('abort', () => {
          const error = new Error('aborted')
          error.name = 'AbortError'
          reject(error)
        })
      })
    ))
    const body = buildBrowseQueryRequest({
      path: '/shots',
      recursive: true,
      filters: { and: [] },
      sort: { kind: 'builtin', key: 'added', dir: 'desc' },
    })
    const first = api.queryFolder(body).catch(() => undefined)
    const second = api.queryFolder({ ...body, offset: 1 }).catch(() => undefined)
    const queuedController = new AbortController()
    const queued = api.queryFolder({ ...body, offset: 2 }, { signal: queuedController.signal })

    expect(fetchSpy).toHaveBeenCalledTimes(2)
    expect(getBrowseRequestBudgetSnapshot().inflight.folders).toBe(2)
    expect(getBrowseRequestBudgetSnapshot().queued.folders).toBe(1)

    queuedController.abort()
    await expect(queued).rejects.toMatchObject({ name: 'AbortError' })
    expect(getBrowseRequestBudgetSnapshot().queued.folders).toBe(0)
    expect(fetchSpy).toHaveBeenCalledTimes(2)

    cancelBrowseRequests(['folders'])
    await Promise.all([first, second])
  })

  it('separates recursive cache keys from non-recursive', () => {
    expect(folderQueryKey('/shots', { recursive: true })).toEqual([
      'folder',
      '/shots',
      'recursive',
      0,
      null,
      'items',
    ])
    expect(folderQueryKey('/shots', { recursive: false })).toEqual(['folder', '/shots'])
  })

  it('keeps useFolder options scoped to recursive loading and query enablement', () => {
    const options = {
      recursive: true,
      enabled: false,
    } satisfies UseFolderOptions

    expect(folderQueryKey('/shots', options)).toEqual([
      'folder',
      '/shots',
      'recursive',
      0,
      null,
      'items',
    ])
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
