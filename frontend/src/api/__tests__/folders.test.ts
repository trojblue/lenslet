import { afterEach, describe, expect, it, vi } from 'vitest'
import { QueryClient } from '@tanstack/react-query'
import { api, buildFolderQuery } from '../client'
import {
  cancelBrowseRequests,
  getBrowseRequestBudgetSnapshot,
  resetBrowseRequestBudgetForTests,
} from '../requestBudget'
import {
  BACKEND_BROWSE_PAGE_SIZE,
  analysisQueryKey,
  browseQueryKey,
  buildBrowseQueryRequest,
  facetFieldBatches,
  folderFacetsQueryKey,
  folderQueryKey,
  mergeBrowseFacetPayloads,
  pruneBrowseQueryVariants,
  resetSemanticQueryRevisionForTests,
  semanticQueryRevision,
  shouldRemoveRecursiveFolderQuery,
  shouldRetainRecursiveFolderQuery,
  windowRequestToken,
  type BrowseQueryOptions,
  type UseFolderOptions,
} from '../folders'

afterEach(() => {
  vi.restoreAllMocks()
  cancelBrowseRequests()
  resetBrowseRequestBudgetForTests()
  resetSemanticQueryRevisionForTests()
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

  it('posts query-shaped folder facets to the dedicated endpoint', async () => {
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

    const body = buildBrowseQueryRequest({
      path: '/shots',
      recursive: true,
      filters: { and: [{ categoricalIn: { key: 'source', values: ['gt'] } }] },
      sort: { kind: 'builtin', key: 'added', dir: 'desc' },
      textQuery: 'cat',
      randomSeed: 7,
    })
    await expect(api.queryFolderFacets(body)).resolves.toMatchObject({
      path: '/shots',
      categoricals: {
        original_source: {
          values: [{ value: 'gt', population_count: 2 }],
        },
      },
    })
    const [requestUrl, init] = fetchSpy.mock.calls[0]
    const url = new URL(String(requestUrl), 'http://localhost')
    expect(url.pathname).toBe('/folders/facets')
    expect(init?.method).toBe('POST')
    expect(JSON.parse(String(init?.body))).toEqual(body)
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
      derived_metric: null,
      unsupported_metric_intent: null,
      projection: { metric_keys: [], categorical_keys: [] },
    })
  })

  it('includes valid derived metrics in browse-query request bodies', () => {
    const request = buildBrowseQueryRequest({
      path: '/shots',
      recursive: true,
      filters: { and: [] },
      sort: { kind: 'metric', key: '@derived/rubric_1', dir: 'desc' },
      derivedMetric: {
        version: 1,
        id: 'rubric_1',
        name: 'Rubric score',
        intercept: 0,
        numericTerms: [{ key: 'q1', weight: 1, missing: 'invalid', zNormalize: false }],
        categoricalTerms: [{ key: 'dataset_from', value: 'gt', weight: 3 }],
      },
    })

    expect(request.derived_metric).toEqual({
      version: 1,
      id: 'rubric_1',
      name: 'Rubric score',
      intercept: 0,
      numericTerms: [{ key: 'q1', weight: 1, missing: 'invalid', zNormalize: false }],
      categoricalTerms: [{ key: 'dataset_from', value: 'gt', weight: 3 }],
    })
  })

  it('keys analysis queries by semantic request variables only', () => {
    const base: BrowseQueryOptions = {
      path: '/shots',
      recursive: true,
      filters: { and: [] },
      sort: { kind: 'builtin', key: 'added', dir: 'desc' },
      textQuery: '',
      randomSeed: 1,
    }

    const key = (overrides: Partial<BrowseQueryOptions> = {}) => (
      JSON.stringify(analysisQueryKey({ ...base, ...overrides }))
    )

    expect(key({ path: '/other' })).not.toBe(key())
    expect(key({ filters: { and: [{ categoricalIn: { key: 'source', values: ['target'] } }] } })).not.toBe(key())
    expect(key({ sort: { kind: 'builtin', key: 'name', dir: 'asc' } })).not.toBe(key())
    expect(key({ textQuery: 'cat' })).not.toBe(key())
    expect(key({ randomSeed: 2 })).toBe(key())
    expect(key({ sort: { kind: 'builtin', key: 'random', dir: 'asc' }, randomSeed: 2 })).not.toBe(
      key({ sort: { kind: 'builtin', key: 'random', dir: 'asc' } }),
    )
    expect(key({
      derivedMetric: {
        version: 1,
        id: 'rubric_1',
        name: 'Rubric score',
        intercept: 0,
        numericTerms: [{ key: 'q1', weight: 1, missing: 'invalid', zNormalize: false }],
        categoricalTerms: [],
      },
    })).not.toBe(key())
    expect(key({ unsupportedToken: 'derived-filter' })).not.toBe(key())
    expect(key({ unsupportedToken: ' derived-filter ' })).toBe(key({ unsupportedToken: 'derived-filter' }))
    expect(key({ projection: { metric_keys: ['score'], categorical_keys: [] } })).toBe(key())
    expect(key({ facetFields: { metric_keys: ['score'], categorical_keys: [] } })).toBe(key())
    expect(key({ filters: { and: [{ starsIn: { values: [] } }] } })).toBe(key())
  })

  it('normalizes facet fields without changing analysis identity', () => {
    const base: BrowseQueryOptions = {
      path: '/shots',
      filters: { and: [] },
      sort: { kind: 'builtin', key: 'added', dir: 'desc' },
    }
    const request = buildBrowseQueryRequest({
      ...base,
      facetFields: {
        metric_keys: [' q2 ', 'q1', 'q1'],
        categorical_keys: ['split'],
      },
    })

    expect(request.facet_fields).toEqual({
      metric_keys: ['q1', 'q2'],
      categorical_keys: ['split'],
    })
    const facetFields = request.facet_fields ?? undefined
    expect(facetFields).toBeDefined()
    expect(analysisQueryKey({ ...base, facetFields })).toEqual(
      analysisQueryKey(base),
    )
    expect(folderFacetsQueryKey({ ...base, facetFields })).not.toEqual(
      folderFacetsQueryKey(base),
    )
  })

  it('splits and merges facet batches at the 24-field boundary', () => {
    const batches = facetFieldBatches({
      metric_keys: Array.from({ length: 30 }, (_, index) => `q${index}`),
      categorical_keys: ['split'],
    })
    expect(batches).toHaveLength(2)
    expect(batches.map((batch) => (
      (batch?.metric_keys.length ?? 0) + (batch?.categorical_keys.length ?? 0)
    ))).toEqual([24, 7])

    const payload = (metricKey: string, categoricalKey?: string) => ({
      version: 1 as const,
      path: '/shots',
      generated_at: 'test',
      total_items: 2,
      metric_keys: [metricKey],
      categorical_keys: categoricalKey ? [categoricalKey] : [],
      metrics: { [metricKey]: { categories: [] } },
      categoricals: categoricalKey
        ? { [categoricalKey]: { values: [{ value: 'train', population_count: 2 }] } }
        : {},
      dependency_manifest: {
        fields: [],
        metric_keys: [metricKey],
        categorical_keys: categoricalKey ? [categoricalKey] : [],
        unknown: false,
      },
    })
    const merged = mergeBrowseFacetPayloads([payload('q1'), payload('q2', 'split')])

    expect(merged?.metric_keys).toEqual(['q1', 'q2'])
    expect(merged?.categorical_keys).toEqual(['split'])
    expect(Object.keys(merged?.metrics ?? {})).toEqual(['q1', 'q2'])
    expect(merged?.categoricals.split.values).toHaveLength(1)
  })

  it('normalizes unsupported metric intent in browse-query request bodies', () => {
    const request = buildBrowseQueryRequest({
      path: '/shots',
      recursive: true,
      filters: { and: [] },
      sort: { kind: 'builtin', key: 'added', dir: 'desc' },
      unsupportedToken: ' derived   filter ',
    })

    expect(request.unsupported_metric_intent).toBe('derived filter')
  })

  it('keeps window request tokens separate from analysis query identity', () => {
    const base: BrowseQueryOptions = {
      path: '/shots',
      recursive: true,
      filters: { and: [] },
      sort: { kind: 'builtin', key: 'added', dir: 'desc' },
      textQuery: 'cat',
      randomSeed: 1,
    }

    const analysis = JSON.stringify(analysisQueryKey(base))
    expect(JSON.stringify(analysisQueryKey({ ...base, limit: 20 }))).toBe(analysis)
    expect(JSON.stringify(windowRequestToken(base, 0))).not.toBe(JSON.stringify(windowRequestToken(base, 20)))
    expect(JSON.stringify(windowRequestToken(base, 0))).not.toBe(JSON.stringify(windowRequestToken({ ...base, limit: 20 }, 0)))
    expect(JSON.stringify(windowRequestToken(base, 0))).not.toBe(JSON.stringify(windowRequestToken(base, 0, 'gen-2')))
    expect(JSON.stringify(windowRequestToken(base, 0))).not.toBe(JSON.stringify(windowRequestToken({
      ...base,
      projection: { metric_keys: ['score'], categorical_keys: [] },
    }, 0)))
    expect(JSON.stringify(browseQueryKey(base))).toBe(JSON.stringify(windowRequestToken(base, 0)))
    expect(JSON.stringify(folderFacetsQueryKey(base))).toBe(JSON.stringify([
      'folder-facets',
      analysisQueryKey(base),
    ]))
  })

  it('increments semantic revisions independently from pagination and projection', () => {
    const base: BrowseQueryOptions = {
      path: '/shots',
      recursive: true,
      filters: { and: [] },
      sort: { kind: 'builtin', key: 'added', dir: 'desc' },
      textQuery: '',
    }
    const firstKey = analysisQueryKey(base)
    const first = semanticQueryRevision(firstKey)

    expect(semanticQueryRevision(analysisQueryKey({ ...base, limit: 20 }))).toBe(first)
    expect(semanticQueryRevision(analysisQueryKey({ ...base, textQuery: 'cat' }))).toBe(first + 1)
    expect(semanticQueryRevision(firstKey)).toBe(first + 2)
  })

  it('retains only the active plus two recent query variants for one path', () => {
    const queryClient = new QueryClient()
    const keys = Array.from({ length: 50 }, (_, index) => [
      'folder-query',
      ['analysis-query', '/shots', 'recursive', { and: [] }, { index }],
      0,
      1000,
      JSON.stringify({ metric_keys: [`metric_${index}`], categorical_keys: [] }),
      null,
    ] as const)
    for (const key of keys) queryClient.setQueryData(key, { item_paths: [] })

    pruneBrowseQueryVariants(queryClient, '/shots', keys[49])

    const retained = queryClient.getQueryCache().findAll({ queryKey: ['folder-query'] })
    expect(retained).toHaveLength(3)
    expect(queryClient.getQueryData(keys[49])).toBeDefined()
  })

  it('starts a reloaded tab above its prior in-memory revision without another storage key', () => {
    const options: BrowseQueryOptions = {
      path: '/shots',
      filters: { and: [] },
      sort: { kind: 'builtin', key: 'added', dir: 'desc' },
    }
    vi.spyOn(Date, 'now').mockReturnValue(100)
    resetSemanticQueryRevisionForTests()
    const beforeReload = semanticQueryRevision(analysisQueryKey(options))
    vi.spyOn(Date, 'now').mockReturnValue(101)
    resetSemanticQueryRevisionForTests()

    expect(semanticQueryRevision(analysisQueryKey(options))).toBeGreaterThan(beforeReload)
  })

  it('uses one client identity with the explicit semantic revision on query requests', async () => {
    const fetchSpy = vi.spyOn(globalThis, 'fetch').mockResolvedValue(
      new Response(JSON.stringify({
        path: '/shots',
        generated_at: 'test',
        generation_token: 'gen',
        request_token: 'req',
        analysis_query_key: 'analysis',
        scope_total: 0,
        filtered_total: 0,
        offset: 0,
        limit: 10,
        items: [],
        folders: [],
        metric_keys: [],
        categorical_keys: [],
      }), { status: 200, headers: { 'content-type': 'application/json' } }),
    )
    const body = buildBrowseQueryRequest({
      path: '/shots',
      filters: { and: [] },
      sort: { kind: 'builtin', key: 'added', dir: 'desc' },
      limit: 10,
    })

    await api.queryFolder(body, { queryRevision: 7 })
    await api.queryFolderFacets(body, { queryRevision: 7 })

    const firstHeaders = new Headers(fetchSpy.mock.calls[0][1]?.headers)
    const secondHeaders = new Headers(fetchSpy.mock.calls[1][1]?.headers)
    expect(firstHeaders.get('X-Lenslet-Query-Revision')).toBe('7')
    expect(secondHeaders.get('X-Lenslet-Query-Revision')).toBe('7')
    expect(firstHeaders.get('X-Lenslet-Client-Session')).toBeTruthy()
    expect(secondHeaders.get('X-Lenslet-Client-Session')).toBe(
      firstHeaders.get('X-Lenslet-Client-Session'),
    )
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
