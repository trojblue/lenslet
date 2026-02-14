import { startTransition, useCallback, useEffect, useMemo, useRef, useState } from 'react'
import { useQueryClient } from '@tanstack/react-query'
import { shouldRemoveRecursiveFolderQuery, useFolder, useFolderCount } from '../../shared/api/folders'
import { buildCanonicalSearchRequest, useSearch } from '../../shared/api/search'
import { useEmbeddings } from '../../shared/api/embeddings'
import { cancelBrowseRequests } from '../../shared/api/client'
import { useDebounced } from '../../shared/hooks/useDebounced'
import { applyFilters, applySort } from '../../features/browse/model/apply'
import { FetchError } from '../../lib/fetcher'
import {
  completeBrowseLoad,
  startBrowseLoad,
} from '../../lib/browseHotpath'
import type {
  EmbeddingRejected,
  EmbeddingSearchItem,
  EmbeddingSpec,
  FolderIndex,
  Item,
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
  scanStableMode?: boolean
  viewState: ViewState
  randomSeed: number
  localStarOverrides: Record<string, StarRating>
  sessionResetToken?: number
  onFolderHydratedSnapshot?: (path: string, snapshot: FolderIndex) => void
  getCachedHydratedSnapshot?: (path: string) => FolderIndex | null
}

type UseAppDataScopeResult = {
  data: FolderIndex | undefined
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
  poolItems: Item[]
  similarityItems: Item[]
  items: Item[]
  totalCount: number
  filteredCount: number
  scopeTotal: number
  rootTotal: number
}

function getEmbeddingsError(isError: boolean, error: unknown): string | null {
  if (!isError) return null
  if (error instanceof FetchError) return error.message
  if (error instanceof Error) return error.message
  return 'Failed to load embeddings.'
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
  } = useFolder(current, true)
  const { data: rootCount } = useFolderCount('/', { enabled: current !== '/' })
  const [data, setData] = useState<FolderIndex | undefined>()
  const loadTokenRef = useRef(0)
  const refetch = useCallback(() => refetchRecursiveFolder(), [refetchRecursiveFolder])

  useEffect(() => {
    queryClient.removeQueries({
      predicate: ({ queryKey }) => shouldRemoveRecursiveFolderQuery(queryKey, current, false),
    })
  }, [current, queryClient])

  useEffect(() => {
    loadTokenRef.current += 1
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

  const poolItems = useMemo((): Item[] => {
    const base = searching ? (search.data?.items ?? []) : (data?.items ?? [])
    return base.map((it) => ({
      ...it,
      star: localStarOverrides[it.path] !== undefined ? localStarOverrides[it.path] : it.star,
    }))
  }, [searching, search.data, data, localStarOverrides])

  const poolItemsByPath = useMemo(() => {
    const map = new Map<string, Item>()
    for (const it of poolItems) {
      map.set(it.path, it)
    }
    const extras = search.data?.items ?? []
    for (const it of extras) {
      if (map.has(it.path)) continue
      const star = localStarOverrides[it.path] !== undefined ? localStarOverrides[it.path] : it.star
      map.set(it.path, { ...it, star })
    }
    return map
  }, [poolItems, search.data, localStarOverrides])

  const similarityItems = useMemo((): Item[] => {
    if (!similarityState) return []
    return similarityState.items.map((entry) => {
      const existing = poolItemsByPath.get(entry.path)
      if (existing) return existing
      return buildFallbackItem(entry.path, localStarOverrides[entry.path])
    })
  }, [similarityState, poolItemsByPath, localStarOverrides])

  const items = useMemo((): Item[] => {
    if (similarityState) {
      return applyFilters(similarityItems, viewState.filters)
    }
    const filtered = applyFilters(poolItems, viewState.filters)
    if (scanStableMode) return filtered
    return applySort(filtered, viewState.sort, randomSeed)
  }, [similarityState, similarityItems, poolItems, scanStableMode, viewState.filters, viewState.sort, randomSeed])

  const totalCount = similarityState ? similarityItems.length : poolItems.length
  const filteredCount = items.length
  const scopeTotal = data?.totalItems ?? data?.items.length ?? totalCount
  const rootTotal = current === '/'
    ? scopeTotal
    : (rootCount?.totalItems ?? rootCount?.items.length ?? scopeTotal)
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
    items,
    totalCount,
    filteredCount,
    scopeTotal,
    rootTotal,
  }
}
