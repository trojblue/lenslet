import { useInfiniteQuery, useQueries, useQuery, useQueryClient, type QueryClient } from '@tanstack/react-query'
import { api } from './client'
import { usePollingEnabled } from './polling'
import { normalizeSearchQuery, normalizeSearchScopePath } from './search'
import { normalizeFilterAst } from '../features/browse/model/filters'
import { normalizeDerivedMetricSpec } from '../features/metrics/model/derivedMetric'
import { browseEntityStore, type BrowseEntityRequest } from '../app/model/browseEntityStore'
import type {
  BrowseFacetsPayload,
  BrowseFacetFields,
  BrowseFieldCapabilitiesPayload,
  BrowseFolderPayload,
  BrowseQueryPage,
  BrowseQueryRequest,
  BrowseQueryResponse,
  BrowseWindowProjection,
  DerivedMetricViewSpec,
  FilterAST,
  SortSpec,
} from '../lib/types'
import type { GetFolderOptions } from './client'

export const DEFAULT_FOLDER_GC_TIME_MS = 5 * 60_000
export const RECURSIVE_FOLDER_GC_TIME_MS = 60_000
export const BACKEND_BROWSE_PAGE_SIZE = 1000
type RecursiveFolderQueryKey = readonly ['folder', string, 'recursive', number, number | null, 'items' | 'count']

type FolderQueryOptions = {
  recursive?: boolean
  countOnly?: boolean
  offset?: number
  limit?: number
}

export type BrowseQueryOptions = {
  path: string
  recursive?: boolean
  filters: FilterAST
  sort: SortSpec
  textQuery?: string | null
  randomSeed?: string | number | null
  derivedMetric?: DerivedMetricViewSpec | null
  limit?: number
  unsupportedToken?: string | null
  projection?: BrowseWindowProjection
  facetFields?: BrowseFacetFields
}

export type AnalysisQueryKey = readonly [
  'analysis-query',
  string,
  'recursive' | 'direct',
  FilterAST,
  SortSpec,
  string,
  string | number | null,
  DerivedMetricViewSpec | null,
  string | null,
]

export type WindowRequestToken = readonly [
  'folder-query',
  AnalysisQueryKey,
  number,
  number,
  string,
  string | null,
]

export const folderQueryKey = (
  path: string,
  options?: FolderQueryOptions,
) => (
  options?.recursive
    ? [
      'folder',
      path,
      'recursive',
      options.offset ?? 0,
      options.limit ?? null,
      options.countOnly ? 'count' : 'items',
    ] as const
    : ['folder', path] as const
)

export function normalizeBrowseQueryFilters(filters: FilterAST | null | undefined): FilterAST {
  return normalizeFilterAst(filters) ?? { and: [] }
}

function normalizeUnsupportedToken(value: string | null | undefined): string | null {
  const token = value?.trim().replace(/\s+/g, ' ') ?? ''
  return token || null
}

function normalizeProjection(projection: BrowseWindowProjection | undefined): BrowseWindowProjection {
  return {
    metric_keys: normalizeFieldKeys(projection?.metric_keys),
    categorical_keys: normalizeFieldKeys(projection?.categorical_keys),
  }
}

function normalizeFacetFields(fields: BrowseFacetFields): BrowseFacetFields {
  return {
    metric_keys: normalizeFieldKeys(fields.metric_keys),
    categorical_keys: normalizeFieldKeys(fields.categorical_keys),
  }
}

function normalizeFieldKeys(values: readonly string[] | undefined): string[] {
  return Array.from(new Set(
    (values ?? []).map((value) => value.trim()).filter(Boolean),
  )).sort()
}

export function buildBrowseQueryRequest(
  options: BrowseQueryOptions,
  offset = 0,
): BrowseQueryRequest {
  const limit = options.limit ?? BACKEND_BROWSE_PAGE_SIZE
  const textQuery = normalizeSearchQuery(options.textQuery ?? '')
  const derivedMetric = normalizeDerivedMetricSpec(options.derivedMetric ?? null)
  const facetFields = options.facetFields ? normalizeFacetFields(options.facetFields) : null
  return {
    path: normalizeSearchScopePath(options.path),
    recursive: options.recursive ?? true,
    offset,
    limit,
    filters: normalizeBrowseQueryFilters(options.filters),
    sort: options.sort,
    text_query: textQuery || null,
    random_seed: options.randomSeed ?? null,
    derived_metric: derivedMetric,
    unsupported_metric_intent: normalizeUnsupportedToken(options.unsupportedToken),
    projection: normalizeProjection(options.projection),
    ...(facetFields ? { facet_fields: facetFields } : {}),
  }
}

function activeRandomSeedForAnalysis(request: BrowseQueryRequest): string | number | null {
  if (request.sort.kind !== 'builtin' || request.sort.key !== 'random') return null
  return request.random_seed ?? null
}

function analysisQueryKeyFromRequest(
  request: BrowseQueryRequest,
  unsupportedToken: string | null | undefined,
): AnalysisQueryKey {
  return [
    'analysis-query',
    request.path,
    request.recursive ? 'recursive' : 'direct',
    request.filters,
    request.sort,
    request.text_query ?? '',
    activeRandomSeedForAnalysis(request),
    request.derived_metric ?? null,
    normalizeUnsupportedToken(unsupportedToken),
  ] as const
}

export const analysisQueryKey = (options: BrowseQueryOptions): AnalysisQueryKey => (
  analysisQueryKeyFromRequest(
    buildBrowseQueryRequest(options, 0),
    options.unsupportedToken,
  )
)

export const folderFacetsQueryKey = (options: BrowseQueryOptions) => {
  const analysisKey = analysisQueryKey(options)
  return options.facetFields
    ? ['folder-facets', analysisKey, normalizeFacetFields(options.facetFields)] as const
    : ['folder-facets', analysisKey] as const
}

export const windowRequestToken = (
  options: BrowseQueryOptions,
  offset = 0,
  generationToken: string | null = null,
): WindowRequestToken => {
  const request = buildBrowseQueryRequest(options, offset)
  return [
    'folder-query',
    analysisQueryKeyFromRequest(request, options.unsupportedToken),
    request.offset,
    request.limit,
    JSON.stringify(request.projection),
    generationToken,
  ] as const
}

export const browseQueryKey = (options: BrowseQueryOptions) => windowRequestToken(options, 0)

let activeSemanticQueryKey = ''
let activeSemanticQueryRevision = Date.now() * 1000

export function semanticQueryRevision(key: AnalysisQueryKey): number {
  const serialized = JSON.stringify(key)
  if (serialized !== activeSemanticQueryKey) {
    activeSemanticQueryKey = serialized
    activeSemanticQueryRevision += 1
  }
  return activeSemanticQueryRevision
}

export function resetSemanticQueryRevisionForTests(): void {
  activeSemanticQueryKey = ''
  activeSemanticQueryRevision = Date.now() * 1000
}

function parseRecursiveFolderQueryKey(queryKey: readonly unknown[]): RecursiveFolderQueryKey | null {
  if (queryKey[0] !== 'folder' || queryKey[2] !== 'recursive') return null
  if (typeof queryKey[1] !== 'string') return null
  return queryKey as RecursiveFolderQueryKey
}

export function isRecursiveFolderQueryKey(queryKey: readonly unknown[]): boolean {
  return parseRecursiveFolderQueryKey(queryKey) !== null
}

export function shouldRetainRecursiveFolderQuery(
  queryKey: readonly unknown[],
  currentPath: string,
  keepRoot = true,
): boolean {
  if (!isRecursiveFolderQueryKey(queryKey)) return true
  const recursiveKey = parseRecursiveFolderQueryKey(queryKey)
  if (recursiveKey == null) return false
  const [, keyPath] = recursiveKey
  if (keyPath === currentPath) return true
  if (keepRoot && keyPath === '/') return true
  return false
}

export function shouldRemoveRecursiveFolderQuery(
  queryKey: unknown,
  currentPath: string,
  keepRoot = true,
): boolean {
  if (!Array.isArray(queryKey)) return false
  if (queryKey[0] !== 'folder') return false
  return !shouldRetainRecursiveFolderQuery(queryKey, currentPath, keepRoot)
}

const FALLBACK_REFETCH_INTERVAL = 15_000

function fetchFolder(path: string, options?: GetFolderOptions): Promise<BrowseFolderPayload> {
  return api.getFolder(path, options)
}

export function normalizeBrowseQueryPage(
  response: BrowseQueryResponse,
  entityRequest?: BrowseEntityRequest,
): BrowseQueryPage {
  browseEntityStore.ingest(response.items, entityRequest)
  const { items, ...page } = response
  return { ...page, item_paths: items.map((item) => item.path) }
}

export function pruneBrowseQueryVariants(
  queryClient: QueryClient,
  path: string,
  activeKey: readonly unknown[],
  retain = 3,
): void {
  const activeHash = JSON.stringify(activeKey)
  const candidates = queryClient.getQueryCache().findAll({ queryKey: ['folder-query'] })
    .filter((query) => {
      const key = query.queryKey
      const analysis = Array.isArray(key) ? key[1] : null
      return Array.isArray(analysis) && analysis[1] === path
    })
    .sort((a, b) => (
      b.state.dataUpdatedAt - a.state.dataUpdatedAt
      || a.queryHash.localeCompare(b.queryHash)
    ))
  const keep = new Set<string>([activeHash])
  for (const query of candidates) {
    if (keep.size >= retain) break
    keep.add(JSON.stringify(query.queryKey))
  }
  for (const query of candidates) {
    if (keep.has(JSON.stringify(query.queryKey))) continue
    queryClient.removeQueries({ queryKey: query.queryKey, exact: true })
  }
}

export function useBrowseQuery(options: BrowseQueryOptions & { enabled?: boolean }) {
  const pollingEnabled = usePollingEnabled()
  const queryClient = useQueryClient()
  const queryKey = browseQueryKey(options)
  const queryRevision = semanticQueryRevision(analysisQueryKey(options))
  return useInfiniteQuery<BrowseQueryPage>({
    queryKey,
    queryFn: async ({ pageParam, signal }) => {
      const offset = typeof pageParam === 'number' ? pageParam : 0
      const request = buildBrowseQueryRequest(options, offset)
      const entityRequest = browseEntityStore.beginRequest(request.projection)
      const response = await api.queryFolder(
        request,
        { signal, queryRevision },
      )
      const page = normalizeBrowseQueryPage(response, entityRequest)
      pruneBrowseQueryVariants(queryClient, response.path, queryKey)
      return page
    },
    initialPageParam: 0,
    getNextPageParam: (lastPage) => {
      const loadedThrough = lastPage.offset + lastPage.item_paths.length
      return loadedThrough < lastPage.filtered_total ? loadedThrough : undefined
    },
    enabled: options.enabled ?? true,
    staleTime: 0,
    gcTime: RECURSIVE_FOLDER_GC_TIME_MS,
    retry: 1,
    retryDelay: (attempt) => Math.min(1000 * Math.pow(2, attempt), 5000),
    refetchOnWindowFocus: false,
    refetchInterval: pollingEnabled ? FALLBACK_REFETCH_INTERVAL : false,
    refetchIntervalInBackground: pollingEnabled,
  })
}

export type UseFolderOptions = FolderQueryOptions & {
  enabled?: boolean
}

export function useFolder(path: string, options?: UseFolderOptions) {
  const pollingEnabled = usePollingEnabled()
  const folderOptions: GetFolderOptions = {
    recursive: options?.recursive ?? false,
    countOnly: options?.countOnly,
    offset: options?.offset,
    limit: options?.limit,
  }
  const recursiveQuery = !!folderOptions.recursive
  return useQuery({
    queryKey: folderQueryKey(path, folderOptions),
    queryFn: () => fetchFolder(path, folderOptions),
    enabled: options?.enabled ?? true,
    staleTime: 10_000,
    gcTime: recursiveQuery ? RECURSIVE_FOLDER_GC_TIME_MS : DEFAULT_FOLDER_GC_TIME_MS,
    retry: 2,
    retryDelay: (attempt) => Math.min(1000 * Math.pow(2, attempt), 5000),
    refetchOnWindowFocus: false,
    refetchInterval: pollingEnabled ? FALLBACK_REFETCH_INTERVAL : false,
    refetchIntervalInBackground: pollingEnabled,
  })
}

export function useFolderFacets(options: BrowseQueryOptions & { enabled?: boolean }) {
  const pollingEnabled = usePollingEnabled()
  const { enabled = true, ...queryOptions } = options
  const queryRevision = semanticQueryRevision(analysisQueryKey(queryOptions))
  const batches = facetFieldBatches(queryOptions.facetFields)
  const results = useQueries({
    queries: batches.map((facetFields) => {
      const batchOptions = facetFields ? { ...queryOptions, facetFields } : queryOptions
      return {
        queryKey: folderFacetsQueryKey(batchOptions),
        queryFn: ({ signal }: { signal: AbortSignal }) => api.queryFolderFacets(
          buildBrowseQueryRequest(batchOptions, 0),
          { signal, queryRevision },
        ),
        enabled,
        staleTime: 10_000,
        gcTime: RECURSIVE_FOLDER_GC_TIME_MS,
        retry: 2,
        retryDelay: (attempt: number) => Math.min(1000 * Math.pow(2, attempt), 5000),
        refetchOnWindowFocus: false,
        refetchInterval: pollingEnabled ? FALLBACK_REFETCH_INTERVAL : false,
        refetchIntervalInBackground: pollingEnabled,
      }
    }),
  })
  return {
    data: mergeBrowseFacetPayloads(
      results.flatMap((result) => result.data ? [result.data as BrowseFacetsPayload] : []),
    ),
    isLoading: results.some((result) => result.isLoading),
    isFetching: results.some((result) => result.isFetching),
    isError: results.some((result) => result.isError),
    error: results.find((result) => result.error)?.error ?? null,
    refetch: () => Promise.all(results.map((result) => result.refetch())),
  }
}

export function facetFieldBatches(fields: BrowseFacetFields | undefined): Array<BrowseFacetFields | undefined> {
  if (!fields) return [undefined]
  const normalized = normalizeFacetFields(fields)
  const entries = [
    ...normalized.metric_keys.map((key) => ({ kind: 'metric' as const, key })),
    ...normalized.categorical_keys.map((key) => ({ kind: 'categorical' as const, key })),
  ]
  const batches: BrowseFacetFields[] = []
  for (let offset = 0; offset < entries.length; offset += 24) {
    const batch = entries.slice(offset, offset + 24)
    batches.push({
      metric_keys: batch.filter((entry) => entry.kind === 'metric').map((entry) => entry.key),
      categorical_keys: batch
        .filter((entry) => entry.kind === 'categorical')
        .map((entry) => entry.key),
    })
  }
  return batches
}

export function mergeBrowseFacetPayloads(
  payloads: readonly BrowseFacetsPayload[],
): BrowseFacetsPayload | undefined {
  const first = payloads[0]
  if (!first) return undefined
  const metricKeys = new Set<string>()
  const categoricalKeys = new Set<string>()
  const fields = new Set<string>()
  const dependencyMetricKeys = new Set<string>()
  const dependencyCategoricalKeys = new Set<string>()
  for (const payload of payloads) {
    payload.metric_keys.forEach((key) => metricKeys.add(key))
    payload.categorical_keys.forEach((key) => categoricalKeys.add(key))
    payload.dependency_manifest.fields.forEach((key) => fields.add(key))
    payload.dependency_manifest.metric_keys.forEach((key) => dependencyMetricKeys.add(key))
    payload.dependency_manifest.categorical_keys.forEach((key) => dependencyCategoricalKeys.add(key))
  }
  return {
    ...first,
    metric_keys: Array.from(metricKeys).sort(),
    categorical_keys: Array.from(categoricalKeys).sort(),
    metrics: Object.assign({}, ...payloads.map((payload) => payload.metrics)),
    categoricals: Object.assign({}, ...payloads.map((payload) => payload.categoricals)),
    field_capabilities: mergeFacetFieldCapabilities(payloads),
    dependency_manifest: {
      fields: Array.from(fields).sort(),
      metric_keys: Array.from(dependencyMetricKeys).sort(),
      categorical_keys: Array.from(dependencyCategoricalKeys).sort(),
      unknown: payloads.some((payload) => payload.dependency_manifest.unknown),
    },
  }
}

function mergeFacetFieldCapabilities(
  payloads: readonly BrowseFacetsPayload[],
): BrowseFacetsPayload['field_capabilities'] {
  const capabilities = payloads.flatMap((payload) => (
    payload.field_capabilities ? [payload.field_capabilities] : []
  ))
  const first = capabilities[0]
  if (!first) return null
  const mergeKeys = (key: keyof typeof first) => Array.from(new Set(
    capabilities.flatMap((entry) => {
      const value = entry[key]
      return Array.isArray(value) ? value as string[] : []
    }),
  )).sort()
  return {
    ...first,
    metrics: Object.assign({}, ...capabilities.map((entry) => entry.metrics)),
    categoricals: Object.assign({}, ...capabilities.map((entry) => entry.categoricals)),
    display_metrics: mergeKeys('display_metrics'),
    sortable_metrics: mergeKeys('sortable_metrics'),
    filterable_metrics: mergeKeys('filterable_metrics'),
    numeric_formula_inputs: mergeKeys('numeric_formula_inputs'),
    categorical_inputs: mergeKeys('categorical_inputs'),
  }
}

type UseFolderCountOptions = {
  enabled?: boolean
}

export function useFolderCount(path: string, options?: UseFolderCountOptions) {
  const pollingEnabled = usePollingEnabled()
  return useQuery({
    queryKey: ['folder-count', path] as const,
    queryFn: () => api.getFolderCount(path),
    enabled: options?.enabled ?? true,
    staleTime: 10_000,
    gcTime: DEFAULT_FOLDER_GC_TIME_MS,
    retry: 2,
    retryDelay: (attempt) => Math.min(1000 * Math.pow(2, attempt), 5000),
    refetchOnWindowFocus: false,
    refetchInterval: pollingEnabled ? FALLBACK_REFETCH_INTERVAL : false,
    refetchIntervalInBackground: pollingEnabled,
  })
}

export function useFolderFields(path: string, options?: UseFolderCountOptions) {
  return useQuery<BrowseFieldCapabilitiesPayload>({
    queryKey: ['folder-fields', normalizeSearchScopePath(path)] as const,
    queryFn: () => api.getFolderFields(path),
    enabled: options?.enabled ?? true,
    staleTime: 30_000,
    gcTime: DEFAULT_FOLDER_GC_TIME_MS,
    retry: 2,
    retryDelay: (attempt) => Math.min(1000 * Math.pow(2, attempt), 5000),
    refetchOnWindowFocus: false,
  })
}

export function usePrefetchFolder() {
  const queryClient = useQueryClient()
  
  return (path: string, recursive = false) => {
    const folderOptions: GetFolderOptions = { recursive }
    queryClient.prefetchQuery({
      queryKey: folderQueryKey(path, folderOptions),
      queryFn: () => fetchFolder(path, folderOptions),
      staleTime: 10_000,
      gcTime: recursive ? RECURSIVE_FOLDER_GC_TIME_MS : DEFAULT_FOLDER_GC_TIME_MS,
    })
  }
}

export function useInvalidateFolder() {
  const queryClient = useQueryClient()
  
  return (path: string, recursive = false) => {
    queryClient.invalidateQueries({ queryKey: folderQueryKey(path, { recursive }) })
  }
}

export function useOptimisticFolderUpdate() {
  const queryClient = useQueryClient()
  
  return (
    path: string,
    updater: (old: BrowseFolderPayload | undefined) => BrowseFolderPayload | undefined,
    recursive = false
  ) => {
    const key = folderQueryKey(path, { recursive })
    const previous = queryClient.getQueryData<BrowseFolderPayload>(key)
    queryClient.setQueryData<BrowseFolderPayload | undefined>(key, updater)
    return () => queryClient.setQueryData(key, previous)
  }
}
