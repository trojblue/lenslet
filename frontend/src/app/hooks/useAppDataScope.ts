import { useCallback, useEffect, useMemo, useRef, useState } from 'react'
import { useQueryClient } from '@tanstack/react-query'
import {
  BACKEND_BROWSE_PAGE_SIZE,
  browseQueryKey,
  shouldRemoveRecursiveFolderQuery,
  useBrowseQuery,
  useFolderCount,
  useFolderFields,
  type BrowseQueryOptions,
} from '../../api/folders'
import { buildCanonicalSearchRequest, normalizeSearchScopePath } from '../../api/search'
import { useEmbeddings } from '../../api/embeddings'
import { cancelBrowseRequests } from '../../api/client'
import { useDebounced } from '../../shared/hooks/useDebounced'
import { applyFilters } from '../../features/browse/model/apply'
import { FetchError } from '../../lib/fetcher'
import { sanitizePath } from '../../lib/paths'
import {
  getBackendBrowseDerivedMetricUnsupportedReason,
  resolveCategoricalKeys,
  resolveMetricKeys,
} from '../model/appShellSelectors'
import {
  derivedMetricKey,
  evaluateBackendDerivedMetric,
  evaluateDerivedMetric,
  getDerivedMetricInputKeys,
  normalizeDerivedMetricSpec,
  type DerivedMetricEvaluation,
} from '../../features/metrics/model/derivedMetric'
import { browseEntityStore } from '../model/browseEntityStore'
import {
  completeBrowseLoad,
  startBrowseLoad,
} from '../../lib/browseHotpath'
import type {
  BrowseQueryPage,
  BrowseFieldCapabilitiesPayload,
  EmbeddingRejected,
  EmbeddingSearchItem,
  EmbeddingSpec,
  BrowseFolderPayload,
  BrowseItemPayload,
  StarRating,
  ViewState,
  BrowseWindowProjection,
  FilterAST,
} from '../../lib/types'
import { buildFallbackItem } from '../utils/appShellHelpers'

export type SimilarityState = {
  scopePath: string
  sessionResetToken: number
  embedding: string
  queryPath: string | null
  queryVector: string | null
  topK: number
  minScore: number | null
  items: EmbeddingSearchItem[]
  createdAt: number
}

export function resolveActiveSimilarityState(
  state: SimilarityState | null,
  scopePath: string,
  sessionResetToken: number,
): SimilarityState | null {
  if (!state) return null
  return state.scopePath === sanitizePath(scopePath)
    && state.sessionResetToken === sessionResetToken
    ? state
    : null
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
  browseTargetIdentity: string
  browseTargetSettled: boolean
}

export type BrowseCapabilityKeys = {
  path: string
  metricKeys: string[]
  categoricalKeys: string[]
  ready: boolean
}

type BrowseCapabilityFieldSource = Pick<
  BrowseFieldCapabilitiesPayload,
  'path' | 'metric_keys' | 'categorical_keys'
> & {
  field_capabilities?: BrowseFieldCapabilitiesPayload['field_capabilities']
}

function getEmbeddingsError(isError: boolean, error: unknown): string | null {
  if (!isError) return null
  if (error instanceof FetchError) return error.message
  if (error instanceof Error) return error.message
  return 'Failed to load embeddings.'
}

function buildFolderPayloadFromBrowseQuery(
  firstPage: BrowseQueryPage | undefined,
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
  fields: BrowseCapabilityFieldSource | undefined,
  previous: BrowseCapabilityKeys,
): BrowseCapabilityKeys {
  const scopePath = normalizeSearchScopePath(currentPath)
  if (fields?.path === scopePath) {
    return {
      path: scopePath,
      metricKeys: fieldCapabilityMetricKeys(fields),
      categoricalKeys: fieldCapabilityCategoricalKeys(fields),
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
  page: Pick<BrowseCapabilityFieldSource, 'metric_keys' | 'field_capabilities'>,
): string[] {
  const capabilities = page.field_capabilities
  if (capabilities) return [...capabilities.display_metrics]
  return [...page.metric_keys]
}

function fieldCapabilityCategoricalKeys(
  page: Pick<BrowseCapabilityFieldSource, 'categorical_keys' | 'field_capabilities'>,
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

export function browseProjectionForViewState(viewState: ViewState): BrowseWindowProjection {
  const metricKeys: string[] = []
  const categoricalKeys: string[] = []
  const addMetric = (key: string | undefined) => {
    const normalized = key?.trim()
    if (normalized && !metricKeys.includes(normalized)) metricKeys.push(normalized)
  }
  const addCategorical = (key: string | undefined) => {
    const normalized = key?.trim()
    if (normalized && !categoricalKeys.includes(normalized)) categoricalKeys.push(normalized)
  }
  addMetric(viewState.selectedMetric)
  if (viewState.sort.kind === 'metric') addMetric(viewState.sort.key)
  const derived = normalizeDerivedMetricSpec(viewState.derivedMetric)
  if (derived) addMetric(derivedMetricKey(derived))
  for (const clause of viewState.filters.and) {
    if ('metricRange' in clause) addMetric(clause.metricRange.key)
    if ('categoricalIn' in clause) addCategorical(clause.categoricalIn.key)
  }
  return {
    metric_keys: metricKeys.sort(),
    categorical_keys: categoricalKeys.sort(),
  }
}

export function browseProjectionUnavailableReason(
  projection: BrowseWindowProjection,
): string | null {
  if (projection.metric_keys.length > 64) {
    return 'This view needs more than 64 metric columns. Remove metric filters to continue.'
  }
  if (projection.categorical_keys.length > 32) {
    return 'This view needs more than 32 categorical columns. Remove categorical filters to continue.'
  }
  return null
}

function resolveBrowseEntities(
  paths: readonly string[],
): BrowseItemPayload[] {
  return paths.flatMap((path) => {
    const item = browseEntityStore.get(path)
    return item ? [item] : []
  })
}

export function conclusiveClientFilters(filters: FilterAST): FilterAST {
  return {
    and: filters.and.filter((clause) => (
      !('urlContains' in clause) && !('urlNotContains' in clause)
    )),
  }
}

function useBrowseEntities(paths: readonly string[], filters: FilterAST): BrowseItemPayload[] {
  const ownerRef = useRef<object>({})
  const pathKey = paths.join('\u0000')
  const viewKey = `${pathKey}\u0000${JSON.stringify(filters)}`
  const localFilters = useMemo(() => conclusiveClientFilters(filters), [filters])
  const initialItems = useMemo(
    () => resolveBrowseEntities(paths),
    [viewKey], // eslint-disable-line react-hooks/exhaustive-deps
  )
  const [state, setState] = useState(() => ({ key: viewKey, items: initialItems }))
  useEffect(() => {
    const owner = ownerRef.current
    const uniquePaths = Array.from(new Set(paths))
    const orderByPath = new Map(paths.map((path, index) => [path, index]))
    browseEntityStore.setActivePaths(owner, uniquePaths)
    const unsubscribers = uniquePaths.map((path) => browseEntityStore.subscribe(path, () => {
      const entity = browseEntityStore.get(path)
      const visible = entity ? applyFilters([entity], localFilters).length === 1 : false
      setState((previous) => {
        const items = previous.key === viewKey ? previous.items : initialItems
        const currentIndex = items.findIndex((item) => item.path === path)
        if (!visible) {
          if (currentIndex < 0) return previous.key === viewKey ? previous : { key: viewKey, items }
          return { key: viewKey, items: items.filter((_, index) => index !== currentIndex) }
        }
        if (currentIndex >= 0) {
          if (items[currentIndex] === entity) return previous
          const next = [...items]
          next[currentIndex] = entity!
          return { key: viewKey, items: next }
        }
        const targetOrder = orderByPath.get(path) ?? Number.MAX_SAFE_INTEGER
        const insertAt = items.findIndex(
          (item) => (orderByPath.get(item.path) ?? Number.MAX_SAFE_INTEGER) > targetOrder,
        )
        const next = [...items]
        next.splice(insertAt < 0 ? next.length : insertAt, 0, entity!)
        return { key: viewKey, items: next }
      })
    }))
    setState({ key: viewKey, items: resolveBrowseEntities(paths) })
    return () => {
      for (const unsubscribe of unsubscribers) unsubscribe()
      browseEntityStore.release(owner)
    }
  }, [viewKey]) // eslint-disable-line react-hooks/exhaustive-deps
  return state.key === viewKey ? state.items : initialItems
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
  const browseProjection = useMemo(
    () => browseProjectionForViewState(viewState),
    [viewState],
  )
  const browseQueryUnavailableReason = useMemo(() => (
    getBackendBrowseDerivedMetricUnsupportedReason(
      viewState.sort,
      viewState.filters,
      similarityActive,
    ) ?? browseProjectionUnavailableReason(browseProjection)
  ), [browseProjection, similarityActive, viewState.filters, viewState.sort])
  const analysisUnsupportedMetricIntent = browseQueryUnavailableReason
    ?? urlUnsupportedMetricIntent
  const browseQueryOptions = useMemo<BrowseQueryOptions>(() => ({
    path: current,
    recursive: true,
    filters: viewState.filters,
    sort: viewState.sort,
    textQuery: normalizedQ,
    randomSeed,
    derivedMetric: viewState.derivedMetric ?? null,
    limit: BACKEND_BROWSE_PAGE_SIZE,
    unsupportedToken: analysisUnsupportedMetricIntent,
    projection: browseProjection,
    generationToken: String(sessionResetToken),
  }), [
    analysisUnsupportedMetricIntent,
    browseProjection,
    current,
    normalizedQ,
    randomSeed,
    sessionResetToken,
    viewState.derivedMetric,
    viewState.filters,
    viewState.sort,
  ])
  const browseTargetIdentity = useMemo(() => (
    similarityState
      ? JSON.stringify(['similarity', similarityState.createdAt, viewState.filters])
      : JSON.stringify(browseQueryKey(browseQueryOptions))
  ), [browseQueryOptions, similarityState, viewState.filters])
  const browseQuery = useBrowseQuery({
    ...browseQueryOptions,
    enabled: !similarityActive && browseQueryUnavailableReason === null,
  })
  const { data: rootCount } = useFolderCount('/', { enabled: current !== '/' })
  const folderFields = useFolderFields(current, { enabled: !similarityActive })
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
  const browsePaths = useMemo((): string[] => (
    browseQuery.data?.pages.flatMap((page) => page.item_paths) ?? []
  ), [browseQuery.data])
  const browseItems = useBrowseEntities(browsePaths, viewState.filters)

  useEffect(() => {
    setBrowseCapabilityKeys((previous) => {
      const next = resolveBrowseCapabilityKeys(currentScopePath, folderFields.data, previous)
      return sameBrowseCapabilityKeys(previous, next) ? previous : next
    })
  }, [currentScopePath, folderFields.data])

  const effectiveBrowseCapabilityKeys = useMemo(() => (
    browseCapabilityKeys.path === currentScopePath
      ? browseCapabilityKeys
      : emptyBrowseCapabilityKeys(currentScopePath)
  ), [browseCapabilityKeys, currentScopePath])

  const rawPoolItems = browseItems

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
    browseTargetIdentity,
    browseTargetSettled: similarityActive || firstBrowsePage !== undefined,
  }
}
