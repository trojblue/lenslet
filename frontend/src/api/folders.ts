import { useInfiniteQuery, useQuery, useQueryClient } from '@tanstack/react-query'
import { api } from './client'
import { usePollingEnabled } from './polling'
import { normalizeSearchQuery, normalizeSearchScopePath } from './search'
import { normalizeFilterAst } from '../features/browse/model/filters'
import { normalizeDerivedMetricSpec } from '../features/metrics/model/derivedMetric'
import type {
  BrowseFacetsPayload,
  BrowseFolderPayload,
  BrowseQueryRequest,
  BrowseQueryResponse,
  DerivedMetricViewSpec,
  FilterAST,
  SortSpec,
} from '../lib/types'
import type { GetFolderOptions } from './client'

export const DEFAULT_FOLDER_GC_TIME_MS = 5 * 60_000
export const RECURSIVE_FOLDER_GC_TIME_MS = 60_000
export const BACKEND_BROWSE_PAGE_SIZE = 1000
export const BACKEND_BROWSE_METRIC_SORT_LIMIT = 50_000
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

export const folderFacetsQueryKey = (path: string, recursive = true) => (
  ['folder-facets', path, recursive ? 'recursive' : 'direct'] as const
)

export function normalizeBrowseQueryFilters(filters: FilterAST | null | undefined): FilterAST {
  return normalizeFilterAst(filters) ?? { and: [] }
}

export function buildBrowseQueryRequest(
  options: BrowseQueryOptions,
  offset = 0,
): BrowseQueryRequest {
  const limit = options.limit ?? BACKEND_BROWSE_PAGE_SIZE
  const textQuery = normalizeSearchQuery(options.textQuery ?? '')
  const derivedMetric = normalizeDerivedMetricSpec(options.derivedMetric ?? null)
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
    request.derived_metric,
    unsupportedToken ?? null,
  ] as const
}

export const analysisQueryKey = (options: BrowseQueryOptions): AnalysisQueryKey => (
  analysisQueryKeyFromRequest(
    buildBrowseQueryRequest(options, 0),
    options.unsupportedToken,
  )
)

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
    generationToken,
  ] as const
}

export const browseQueryKey = (options: BrowseQueryOptions) => windowRequestToken(options, 0)

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

export function useBrowseQuery(options: BrowseQueryOptions & { enabled?: boolean }) {
  const pollingEnabled = usePollingEnabled()
  const queryKey = browseQueryKey(options)
  return useInfiniteQuery<BrowseQueryResponse>({
    queryKey,
    queryFn: ({ pageParam, signal }) => {
      const offset = typeof pageParam === 'number' ? pageParam : 0
      return api.queryFolder(
        buildBrowseQueryRequest(options, offset),
        { signal },
      )
    },
    initialPageParam: 0,
    getNextPageParam: (lastPage) => {
      const loadedThrough = lastPage.offset + lastPage.items.length
      return loadedThrough < lastPage.filtered_total ? loadedThrough : undefined
    },
    enabled: options.enabled ?? true,
    staleTime: 3_000,
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

export function useFolderFacets(path: string, options?: { recursive?: boolean; enabled?: boolean }) {
  const pollingEnabled = usePollingEnabled()
  const recursive = options?.recursive ?? true
  return useQuery<BrowseFacetsPayload>({
    queryKey: folderFacetsQueryKey(path, recursive),
    queryFn: () => api.getFolderFacets(path, { recursive }),
    enabled: options?.enabled ?? true,
    staleTime: 10_000,
    gcTime: RECURSIVE_FOLDER_GC_TIME_MS,
    retry: 2,
    retryDelay: (attempt) => Math.min(1000 * Math.pow(2, attempt), 5000),
    refetchOnWindowFocus: false,
    refetchInterval: pollingEnabled ? FALLBACK_REFETCH_INTERVAL : false,
    refetchIntervalInBackground: pollingEnabled,
  })
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
