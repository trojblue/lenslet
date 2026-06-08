import { startTransition, useCallback, useEffect, useMemo, useRef, useState } from 'react'
import { useQueryClient } from '@tanstack/react-query'
import { shouldRemoveRecursiveFolderQuery, useFolder, useFolderCount } from '../../api/folders'
import { buildCanonicalSearchRequest, useSearch } from '../../api/search'
import { useEmbeddings } from '../../api/embeddings'
import { api, cancelBrowseRequests } from '../../api/client'
import { useDebounced } from '../../shared/hooks/useDebounced'
import { applyFilters, applySort } from '../../features/browse/model/apply'
import { FetchError } from '../../lib/fetcher'
import {
  resolveCategoricalKeys,
  resolveDerivedMetricTotalItems,
  resolveMetricKeys,
} from '../model/appShellSelectors'
import {
  evaluateDerivedMetric,
  getDerivedMetricInputKeys,
  type DerivedMetricEvaluation,
} from '../../features/metrics/model/derivedMetric'
import {
  completeBrowseLoad,
  startBrowseLoad,
} from '../../lib/browseHotpath'
import type {
  EmbeddingRejected,
  EmbeddingSearchItem,
  EmbeddingSpec,
  BrowseFolderPayload,
  BrowseItemPayload,
  StarRating,
  ViewState,
} from '../../lib/types'
import { buildFallbackItem } from '../utils/appShellHelpers'

const FOLDER_PAGE_SIZE = 5000

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
  scanStableMode?: boolean
  viewState: ViewState
  randomSeed: number
  localStarOverrides: Record<string, StarRating>
  sessionResetToken?: number
  onFolderHydratedSnapshot?: (path: string, snapshot: BrowseFolderPayload) => void
  getCachedHydratedSnapshot?: (path: string) => BrowseFolderPayload | null
}

type UseAppDataScopeResult = {
  data: BrowseFolderPayload | undefined
  refetch: () => Promise<unknown>
  isLoading: boolean
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
}

function getEmbeddingsError(isError: boolean, error: unknown): string | null {
  if (!isError) return null
  if (error instanceof FetchError) return error.message
  if (error instanceof Error) return error.message
  return 'Failed to load embeddings.'
}

function mergeFolderPage(
  current: BrowseFolderPayload,
  page: BrowseFolderPayload,
): BrowseFolderPayload {
  const seen = new Set(current.items.map((item) => item.path))
  const items = [...current.items]
  for (const item of page.items) {
    if (seen.has(item.path)) continue
    seen.add(item.path)
    items.push(item)
  }
  const metricKeys = Array.from(new Set([
    ...(current.metric_keys ?? []),
    ...(page.metric_keys ?? []),
  ])).sort()
  const categoricalKeys = Array.from(new Set([
    ...(current.categorical_keys ?? []),
    ...(page.categorical_keys ?? []),
  ])).sort()
  return {
    ...current,
    items,
    metric_keys: metricKeys,
    categorical_keys: categoricalKeys,
    total_items: page.total_items ?? current.total_items,
    offset: 0,
    limit: items.length,
  }
}

export function useAppDataScope({
  current,
  query,
  similarityState,
  scanStableMode = false,
  viewState,
  randomSeed,
  localStarOverrides,
  sessionResetToken = 0,
  onFolderHydratedSnapshot,
  getCachedHydratedSnapshot,
}: UseAppDataScopeParams): UseAppDataScopeResult {
  const queryClient = useQueryClient()
  const {
    data: recursiveFolderData,
    refetch: refetchRecursiveFolder,
    isLoading,
    isError,
  } = useFolder(current, { recursive: true, offset: 0, limit: FOLDER_PAGE_SIZE })
  const { data: rootCount } = useFolderCount('/', { enabled: current !== '/' })
  const [data, setData] = useState<BrowseFolderPayload | undefined>()
  const [isLoadingMoreFolderItems, setIsLoadingMoreFolderItems] = useState(false)
  const loadTokenRef = useRef(0)
  const pageRequestTokenRef = useRef(0)
  const refetch = useCallback(() => {
    pageRequestTokenRef.current += 1
    setIsLoadingMoreFolderItems(false)
    return refetchRecursiveFolder()
  }, [refetchRecursiveFolder])

  useEffect(() => {
    queryClient.removeQueries({
      predicate: ({ queryKey }) => shouldRemoveRecursiveFolderQuery(queryKey, current, false),
    })
  }, [current, queryClient])

  useEffect(() => {
    loadTokenRef.current += 1
    pageRequestTokenRef.current += 1
    setIsLoadingMoreFolderItems(false)
    startBrowseLoad({ requestId: loadTokenRef.current, path: current })
    const cachedSnapshot = getCachedHydratedSnapshot?.(current) ?? null
    setData(cachedSnapshot ?? undefined)
  }, [current, getCachedHydratedSnapshot, sessionResetToken])

  useEffect(() => {
    return () => {
      cancelBrowseRequests()
    }
  }, [current])

  useEffect(() => {
    if (!recursiveFolderData) return
    const requestId = loadTokenRef.current
    startTransition(() => {
      setData(recursiveFolderData)
      onFolderHydratedSnapshot?.(recursiveFolderData.path, recursiveFolderData)
    })
    completeBrowseLoad(requestId)
  }, [onFolderHydratedSnapshot, recursiveFolderData])

  const similarityActive = similarityState !== null
  const debouncedQ = useDebounced(query, 250)
  const searchRequest = useMemo(() => (
    similarityActive ? null : buildCanonicalSearchRequest(debouncedQ, current)
  ), [similarityActive, debouncedQ, current])
  const searching = searchRequest !== null
  const normalizedQ = searchRequest?.q ?? ''
  const search = useSearch(searchRequest?.q ?? '', searchRequest?.path ?? current)
  const embeddingsQuery = useEmbeddings()
  const embeddings = embeddingsQuery.data?.embeddings ?? []
  const embeddingsRejected = embeddingsQuery.data?.rejected ?? []
  const embeddingsAvailable = embeddings.length > 0
  const embeddingsError = getEmbeddingsError(embeddingsQuery.isError, embeddingsQuery.error)

  const rawPoolItems = useMemo((): BrowseItemPayload[] => {
    const base = searching ? (search.data?.items ?? []) : (data?.items ?? [])
    return base.map((it) => ({
      ...it,
      star: localStarOverrides[it.path] !== undefined ? localStarOverrides[it.path] : it.star,
    }))
  }, [searching, search.data, data, localStarOverrides])

  const rawPoolItemsByPath = useMemo(() => {
    const map = new Map<string, BrowseItemPayload>()
    for (const it of rawPoolItems) {
      map.set(it.path, it)
    }
    const extras = search.data?.items ?? []
    for (const it of extras) {
      if (map.has(it.path)) continue
      const star = localStarOverrides[it.path] !== undefined ? localStarOverrides[it.path] : it.star
      map.set(it.path, { ...it, star })
    }
    return map
  }, [rawPoolItems, search.data, localStarOverrides])

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
      data?.metric_keys,
      similarityActive,
      rawSimilarityItems,
      derivedMetricInputKeys.metricKeys,
    )
  ), [data?.metric_keys, derivedMetricInputKeys.metricKeys, similarityActive, rawSimilarityItems])
  const sourceCategoricalKeys = useMemo(() => (
    resolveCategoricalKeys(
      data?.categorical_keys,
      similarityActive,
      rawSimilarityItems,
      derivedMetricInputKeys.categoricalKeys,
    )
  ), [data?.categorical_keys, derivedMetricInputKeys.categoricalKeys, similarityActive, rawSimilarityItems])
  const derivedMetric = useMemo(() => {
    const sourceItems = similarityActive ? rawSimilarityItems : rawPoolItems
    return evaluateDerivedMetric({
      items: sourceItems,
      metricKeys: sourceMetricKeys,
      categoricalKeys: sourceCategoricalKeys,
      spec: viewState.derivedMetric ?? null,
      loadedCount: sourceItems.length,
      totalItems: resolveDerivedMetricTotalItems(
        searching,
        similarityActive,
        sourceItems.length,
        data?.total_items,
      ),
    })
  }, [
    data?.total_items,
    rawPoolItems,
    rawSimilarityItems,
    searching,
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
    const filtered = applyFilters(poolItems, viewState.filters)
    if (scanStableMode) return filtered
    return applySort(filtered, viewState.sort, randomSeed)
  }, [similarityState, similarityItems, poolItems, scanStableMode, viewState.filters, viewState.sort, randomSeed])

  const totalCount = similarityState ? similarityItems.length : poolItems.length
  const filteredCount = items.length
  const scopeTotal = data?.total_items ?? data?.items.length ?? totalCount
  const rootTotal = current === '/'
    ? scopeTotal
    : (rootCount ?? scopeTotal)
  const hasMoreFolderItems = (
    !similarityActive
    && !searching
    && typeof data?.total_items === 'number'
    && data.items.length < data.total_items
  )
  const loadMoreFolderItems = useCallback(() => {
    if (isLoadingMoreFolderItems || !data || !hasMoreFolderItems) return
    const loadedCount = data.items.length
    const requestToken = pageRequestTokenRef.current + 1
    pageRequestTokenRef.current = requestToken
    setIsLoadingMoreFolderItems(true)
    api.getFolder(current, {
      recursive: true,
      offset: loadedCount,
      limit: FOLDER_PAGE_SIZE,
    })
      .then((page) => {
        if (pageRequestTokenRef.current !== requestToken) return
        if (page.path !== data.path) return
        const merged = mergeFolderPage(data, page)
        startTransition(() => {
          setData(merged)
          onFolderHydratedSnapshot?.(merged.path, merged)
        })
      })
      .catch(() => {})
      .finally(() => {
        if (pageRequestTokenRef.current === requestToken) {
          setIsLoadingMoreFolderItems(false)
        }
      })
  }, [current, data, hasMoreFolderItems, isLoadingMoreFolderItems, onFolderHydratedSnapshot])

  return {
    data,
    refetch,
    isLoading,
    isError,
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
    metricDisplayNames: derivedMetric.metricDisplayNames,
    derivedMetric,
    items,
    totalCount,
    filteredCount,
    scopeTotal,
    rootTotal,
    hasMoreFolderItems,
    isLoadingMoreFolderItems,
    loadMoreFolderItems,
  }
}
