import { useCallback, useEffect, useMemo, useRef, useState } from 'react'
import { useQueryClient } from '@tanstack/react-query'
import {
  BACKEND_BROWSE_PAGE_SIZE,
  shouldRemoveRecursiveFolderQuery,
  useBrowseQuery,
  useFolderCount,
} from '../../api/folders'
import { buildCanonicalSearchRequest, normalizeSearchScopePath } from '../../api/search'
import { useEmbeddings } from '../../api/embeddings'
import { cancelBrowseRequests } from '../../api/client'
import { useDebounced } from '../../shared/hooks/useDebounced'
import { applyFilters } from '../../features/browse/model/apply'
import { FetchError } from '../../lib/fetcher'
import {
  getBackendBrowseDerivedMetricUnsupportedReason,
  resolveCategoricalKeys,
  resolveMetricKeys,
} from '../model/appShellSelectors'
import {
  evaluateBackendDerivedMetric,
  evaluateDerivedMetric,
  getDerivedMetricInputKeys,
  type DerivedMetricEvaluation,
} from '../../features/metrics/model/derivedMetric'
import {
  completeBrowseLoad,
  startBrowseLoad,
} from '../../lib/browseHotpath'
import type {
  BrowseQueryResponse,
  EmbeddingRejected,
  EmbeddingSearchItem,
  EmbeddingSpec,
  BrowseFolderPayload,
  BrowseItemPayload,
  StarRating,
  ViewState,
} from '../../lib/types'
import { buildFallbackItem } from '../utils/appShellHelpers'

export type SimilarityState = {
  embedding: string
  queryPath: string | null
  queryVector: string | null
  topK: number
  minScore: number | null
  items: EmbeddingSearchItem[]
  createdAt: number
}

type UseAppDataScopeParams = {
  current: string
  query: string
  similarityState: SimilarityState | null
  viewState: ViewState
  randomSeed: number
  urlUnsupportedMetricIntent?: string | null
  localStarOverrides: Record<string, StarRating>
  sessionResetToken?: number
}

type UseAppDataScopeResult = {
  data: BrowseFolderPayload | undefined
  refetch: () => Promise<unknown>
  isLoading: boolean
  isFetching: boolean
  isError: boolean
  searching: boolean
  normalizedQ: string
  similarityActive: boolean
  embeddings: EmbeddingSpec[]
  embeddingsRejected: EmbeddingRejected[]
  embeddingsAvailable: boolean
  embeddingsLoading: boolean
  embeddingsError: string | null
  poolItems: BrowseItemPayload[]
  similarityItems: BrowseItemPayload[]
  metricKeys: string[]
  categoricalKeys: string[]
  browseCapabilityKeysReady: boolean
  metricDisplayNames: DerivedMetricEvaluation['metricDisplayNames']
  derivedMetric: DerivedMetricEvaluation
  items: BrowseItemPayload[]
  totalCount: number
  filteredCount: number
  scopeTotal: number
  rootTotal: number
  hasMoreFolderItems: boolean
  isLoadingMoreFolderItems: boolean
  loadMoreFolderItems: () => void
  browseQueryUnavailableReason: string | null
  analysisUnsupportedMetricIntent: string | null
}

export type BrowseCapabilityKeys = {
  path: string
  metricKeys: string[]
  categoricalKeys: string[]
  ready: boolean
}

function getEmbeddingsError(isError: boolean, error: unknown): string | null {
  if (!isError) return null
  if (error instanceof FetchError) return error.message
  if (error instanceof Error) return error.message
  return 'Failed to load embeddings.'
}

function buildFolderPayloadFromBrowseQuery(
  firstPage: BrowseQueryResponse | undefined,
  items: BrowseItemPayload[],
): BrowseFolderPayload | undefined {
  if (!firstPage) return undefined
  return {
    version: 1,
    path: firstPage.path,
    generated_at: firstPage.generated_at,
    items,
    folders: firstPage.folders,
    metric_keys: firstPage.metric_keys,
    categorical_keys: firstPage.categorical_keys,
    total_items: firstPage.scope_total,
    offset: 0,
    limit: items.length,
  }
}

function emptyBrowseCapabilityKeys(path: string): BrowseCapabilityKeys {
  return {
    path,
    metricKeys: [],
    categoricalKeys: [],
    ready: false,
  }
}

export function resolveBrowseCapabilityKeys(
  currentPath: string,
  firstPage: Pick<
    BrowseQueryResponse,
    'path' | 'metric_keys' | 'categorical_keys' | 'field_capabilities'
  > | undefined,
  previous: BrowseCapabilityKeys,
): BrowseCapabilityKeys {
  const scopePath = normalizeSearchScopePath(currentPath)
  if (firstPage?.path === scopePath) {
    return {
      path: scopePath,
      metricKeys: fieldCapabilityMetricKeys(firstPage),
      categoricalKeys: fieldCapabilityCategoricalKeys(firstPage),
      ready: true,
    }
  }
  if (previous.path === scopePath) return previous
  return emptyBrowseCapabilityKeys(scopePath)
}

function sameBrowseCapabilityKeys(a: BrowseCapabilityKeys, b: BrowseCapabilityKeys): boolean {
  return a.path === b.path
    && a.ready === b.ready
    && sameStringArray(a.metricKeys, b.metricKeys)
    && sameStringArray(a.categoricalKeys, b.categoricalKeys)
}

function sameStringArray(a: readonly string[], b: readonly string[]): boolean {
  if (a.length !== b.length) return false
  return a.every((value, index) => value === b[index])
}

function fieldCapabilityMetricKeys(
  page: Pick<BrowseQueryResponse, 'metric_keys' | 'field_capabilities'>,
): string[] {
  const capabilities = page.field_capabilities
  if (capabilities) return [...capabilities.display_metrics]
  return [...page.metric_keys]
}

function fieldCapabilityCategoricalKeys(
  page: Pick<BrowseQueryResponse, 'categorical_keys' | 'field_capabilities'>,
): string[] {
  const capabilities = page.field_capabilities
  if (capabilities) return [...capabilities.categorical_inputs]
  return [...page.categorical_keys]
}

function folderQueryKeyPath(queryKey: readonly unknown[]): string {
  if (queryKey[0] !== 'folder-query') return ''
  const analysisKey = queryKey[1]
  if (!Array.isArray(analysisKey)) return ''
  return typeof analysisKey[1] === 'string' ? analysisKey[1] : ''
}

export function useAppDataScope({
  current,
  query,
  similarityState,
  viewState,
  randomSeed,
  urlUnsupportedMetricIntent = null,
  localStarOverrides,
  sessionResetToken = 0,
}: UseAppDataScopeParams): UseAppDataScopeResult {
  const queryClient = useQueryClient()
  const loadTokenRef = useRef(0)
  const currentScopePath = useMemo(() => normalizeSearchScopePath(current), [current])
  const [browseCapabilityKeys, setBrowseCapabilityKeys] = useState<BrowseCapabilityKeys>(() => (
    emptyBrowseCapabilityKeys(currentScopePath)
  ))
  const similarityActive = similarityState !== null
  const debouncedQ = useDebounced(query, 250)
  const searchRequest = useMemo(() => (
    similarityActive ? null : buildCanonicalSearchRequest(debouncedQ, current)
  ), [similarityActive, debouncedQ, current])
  const searching = searchRequest !== null
  const normalizedQ = searchRequest?.q ?? ''
  const browseQueryUnavailableReason = useMemo(() => (
    getBackendBrowseDerivedMetricUnsupportedReason(
      viewState.sort,
      viewState.filters,
      similarityActive,
    )
  ), [similarityActive, viewState.filters, viewState.sort])
  const analysisUnsupportedMetricIntent = browseQueryUnavailableReason
    ?? urlUnsupportedMetricIntent
  const browseQuery = useBrowseQuery({
    path: current,
    recursive: true,
    filters: viewState.filters,
    sort: viewState.sort,
    textQuery: normalizedQ,
    randomSeed,
    derivedMetric: viewState.derivedMetric ?? null,
    limit: BACKEND_BROWSE_PAGE_SIZE,
    unsupportedToken: analysisUnsupportedMetricIntent,
    enabled: !similarityActive && browseQueryUnavailableReason === null,
  })
  const { data: rootCount } = useFolderCount('/', { enabled: current !== '/' })
  const refetch = useCallback(() => browseQuery.refetch(), [browseQuery.refetch])

  useEffect(() => {
    queryClient.removeQueries({
      predicate: ({ queryKey }) => {
        if (Array.isArray(queryKey) && queryKey[0] === 'folder-query') {
          const keyPath = folderQueryKeyPath(queryKey)
          return keyPath !== current
        }
        return shouldRemoveRecursiveFolderQuery(queryKey, current, false)
      },
    })
  }, [current, queryClient])

  useEffect(() => {
    loadTokenRef.current += 1
    startBrowseLoad({ requestId: loadTokenRef.current, path: current })
  }, [
    browseQueryUnavailableReason,
    current,
    normalizedQ,
    randomSeed,
    sessionResetToken,
    viewState.filters,
    viewState.sort,
    analysisUnsupportedMetricIntent,
  ])

  useEffect(() => {
    return () => {
      cancelBrowseRequests()
    }
  }, [current])

  useEffect(() => {
    if (!browseQuery.data?.pages[0]) return
    const requestId = loadTokenRef.current
    completeBrowseLoad(requestId)
  }, [browseQuery.data])

  useEffect(() => {
    if (browseQueryUnavailableReason === null) return
    completeBrowseLoad(loadTokenRef.current)
  }, [browseQueryUnavailableReason])

  const embeddingsQuery = useEmbeddings()
  const embeddings = embeddingsQuery.data?.embeddings ?? []
  const embeddingsRejected = embeddingsQuery.data?.rejected ?? []
  const embeddingsAvailable = embeddings.length > 0
  const embeddingsError = getEmbeddingsError(embeddingsQuery.isError, embeddingsQuery.error)

  const firstBrowsePage = browseQuery.data?.pages[0]
  const browseItems = useMemo((): BrowseItemPayload[] => (
    browseQuery.data?.pages.flatMap((page) => page.items) ?? []
  ), [browseQuery.data])

  useEffect(() => {
    setBrowseCapabilityKeys((previous) => {
      const next = resolveBrowseCapabilityKeys(currentScopePath, firstBrowsePage, previous)
      return sameBrowseCapabilityKeys(previous, next) ? previous : next
    })
  }, [currentScopePath, firstBrowsePage])

  const effectiveBrowseCapabilityKeys = useMemo(() => (
    browseCapabilityKeys.path === currentScopePath
      ? browseCapabilityKeys
      : emptyBrowseCapabilityKeys(currentScopePath)
  ), [browseCapabilityKeys, currentScopePath])

  const rawPoolItems = useMemo((): BrowseItemPayload[] => {
    return browseItems.map((it) => ({
      ...it,
      star: localStarOverrides[it.path] !== undefined ? localStarOverrides[it.path] : it.star,
    }))
  }, [browseItems, localStarOverrides])

  const data = useMemo(() => (
    buildFolderPayloadFromBrowseQuery(firstBrowsePage, rawPoolItems)
  ), [firstBrowsePage, rawPoolItems])

  const rawPoolItemsByPath = useMemo(() => {
    const map = new Map<string, BrowseItemPayload>()
    for (const it of rawPoolItems) {
      map.set(it.path, it)
    }
    return map
  }, [rawPoolItems])

  const rawSimilarityItems = useMemo((): BrowseItemPayload[] => {
    if (!similarityState) return []
    return similarityState.items.map((entry) => {
      const existing = rawPoolItemsByPath.get(entry.path)
      if (existing) return existing
      return buildFallbackItem(entry.path, localStarOverrides[entry.path])
    })
  }, [similarityState, rawPoolItemsByPath, localStarOverrides])

  const derivedMetricInputKeys = useMemo(() => (
    getDerivedMetricInputKeys(viewState.derivedMetric)
  ), [viewState.derivedMetric])
  const sourceMetricKeys = useMemo(() => (
    resolveMetricKeys(
      effectiveBrowseCapabilityKeys.metricKeys,
      similarityActive,
      rawSimilarityItems,
      derivedMetricInputKeys.metricKeys,
    )
  ), [
    effectiveBrowseCapabilityKeys.metricKeys,
    derivedMetricInputKeys.metricKeys,
    similarityActive,
    rawSimilarityItems,
  ])
  const sourceCategoricalKeys = useMemo(() => (
    resolveCategoricalKeys(
      effectiveBrowseCapabilityKeys.categoricalKeys,
      similarityActive,
      rawSimilarityItems,
      derivedMetricInputKeys.categoricalKeys,
    )
  ), [
    effectiveBrowseCapabilityKeys.categoricalKeys,
    derivedMetricInputKeys.categoricalKeys,
    similarityActive,
    rawSimilarityItems,
  ])
  const derivedMetric = useMemo(() => {
    if (!similarityActive) {
      return evaluateBackendDerivedMetric({
        items: rawPoolItems,
        metricKeys: sourceMetricKeys,
        categoricalKeys: sourceCategoricalKeys,
        spec: viewState.derivedMetric ?? null,
        backendStatus: firstBrowsePage?.derived_metric_status ?? null,
        loadedCount: rawPoolItems.length,
        totalItems: firstBrowsePage?.filtered_total ?? rawPoolItems.length,
      })
    }
    const sourceItems = rawSimilarityItems
    return evaluateDerivedMetric({
      items: sourceItems,
      metricKeys: sourceMetricKeys,
      categoricalKeys: sourceCategoricalKeys,
      spec: viewState.derivedMetric ?? null,
      loadedCount: sourceItems.length,
      totalItems: sourceItems.length,
    })
  }, [
    firstBrowsePage?.derived_metric_status,
    firstBrowsePage?.filtered_total,
    rawPoolItems,
    rawSimilarityItems,
    similarityActive,
    sourceCategoricalKeys,
    sourceMetricKeys,
    viewState.derivedMetric,
  ])
  const poolItems = similarityActive ? rawPoolItems : derivedMetric.items
  const similarityItems = similarityActive ? derivedMetric.items : rawSimilarityItems
  const metricKeys = derivedMetric.metricKeys
  const categoricalKeys = derivedMetric.categoricalKeys

  const items = useMemo((): BrowseItemPayload[] => {
    if (similarityState) {
      return applyFilters(similarityItems, viewState.filters)
    }
    return poolItems
  }, [similarityState, similarityItems, poolItems, viewState.filters])

  const totalCount = similarityState ? similarityItems.length : (firstBrowsePage?.scope_total ?? poolItems.length)
  const filteredCount = similarityState ? items.length : (firstBrowsePage?.filtered_total ?? items.length)
  const scopeTotal = firstBrowsePage?.scope_total ?? data?.total_items ?? data?.items.length ?? totalCount
  const rootTotal = current === '/'
    ? scopeTotal
    : (rootCount ?? scopeTotal)
  const hasMoreFolderItems = (
    !similarityActive
    && browseQueryUnavailableReason === null
    && items.length < filteredCount
  )
  const loadMoreFolderItems = useCallback(() => {
    if (!hasMoreFolderItems || browseQuery.isFetchingNextPage) return
    void browseQuery.fetchNextPage()
  }, [browseQuery, hasMoreFolderItems])

  return {
    data,
    refetch,
    isLoading: browseQuery.isLoading,
    isFetching: browseQuery.isFetching && !browseQuery.isFetchingNextPage,
    isError: browseQuery.isError,
    searching,
    normalizedQ,
    similarityActive,
    embeddings,
    embeddingsRejected,
    embeddingsAvailable,
    embeddingsLoading: embeddingsQuery.isLoading,
    embeddingsError,
    poolItems,
    similarityItems,
    metricKeys,
    categoricalKeys,
    browseCapabilityKeysReady: effectiveBrowseCapabilityKeys.ready,
    metricDisplayNames: derivedMetric.metricDisplayNames,
    derivedMetric,
    items,
    totalCount,
    filteredCount,
    scopeTotal,
    rootTotal,
    hasMoreFolderItems,
    isLoadingMoreFolderItems: browseQuery.isFetchingNextPage,
    loadMoreFolderItems,
    browseQueryUnavailableReason,
    analysisUnsupportedMetricIntent,
  }
}
