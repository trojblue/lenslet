import React, { useCallback, useEffect, useMemo, useRef, useState } from 'react'
import Toolbar from '../shared/ui/Toolbar'
import VirtualGrid from '../features/browse/components/VirtualGrid'
import MetricScrollbar from '../features/browse/components/MetricScrollbar'
import Viewer from '../features/viewer/Viewer'
import CompareViewer from '../features/compare/CompareViewer'
import Inspector from '../features/inspector/Inspector'
import SimilarityModal from '../features/embeddings/SimilarityModal'
import { api } from '../shared/api/client'
import type { FullFilePrefetchContext } from '../shared/api/client'
import { useOldestInflightAgeMs, useSyncStatus } from '../shared/api/items'
import { usePollingEnabled } from '../shared/api/polling'
import { readHash, writeHash, sanitizePath, getParentPath, isLikelyImagePath } from './routing/hash'
import {
  countActiveFilters,
  getStarFilter,
  normalizeFilterAst,
  setCommentsContainsFilter,
  setCommentsNotContainsFilter,
  setDateRangeFilter,
  setHeightCompareFilter,
  setMetricRangeFilter,
  setNameContainsFilter,
  setNameNotContainsFilter,
  setStarFilter,
  setStarsNotInFilter,
  setUrlContainsFilter,
  setUrlNotContainsFilter,
  setWidthCompareFilter,
} from '../features/browse/model/filters'
import { useSidebars } from './layout/useSidebars'
import { useQueryClient } from '@tanstack/react-query'
import type { FilterAST, Item, SavedView, SortSpec, StarRating, ViewMode, ViewsPayload, ViewState, FolderIndex, SearchResult, EmbeddingSearchRequest } from '../lib/types'
import { isInputElement } from '../lib/keyboard'
import { safeJsonParse } from '../lib/util'
import { fileCache, thumbCache } from '../lib/blobCache'
import { FetchError } from '../lib/fetcher'
import LeftSidebar from './components/LeftSidebar'
import StatusBar from './components/StatusBar'
import { deriveIndicatorState } from './presenceUi'
import { LONG_SYNC_THRESHOLD_MS } from '../lib/constants'
import { getCompareFilePrefetchPaths, getViewerFilePrefetchPaths } from '../features/browse/model/prefetchPolicy'
import { constrainSidebarWidths, LAYOUT_BREAKPOINTS, LAYOUT_MEDIA_QUERIES } from '../lib/breakpoints'
import { useMediaQuery } from '../shared/hooks/useMediaQuery'
import MoveToDialog from './components/MoveToDialog'
import AppContextMenuItems from './menu/AppContextMenuItems'
import { useLatestRef } from '../shared/hooks/useLatestRef'
import {
  buildStarCounts,
  collectMetricKeys,
  getDisplayItemCount,
  getDisplayTotalCount,
  getSimilarityCountLabel,
  getSimilarityQueryLabel,
  hasMetricSortValues,
} from './model/appShellSelectors'
import { shouldShowGridHydrationLoading } from './model/loadingState'
import {
  downloadBlob,
  formatScopeLabel,
  makeUniqueViewId,
  resolveScopeFromHashTarget,
} from './utils/appShellHelpers'
import { useAppDataScope, type SimilarityState } from './hooks/useAppDataScope'
import { useAppSelectionViewerCompare } from './hooks/useAppSelectionViewerCompare'
import { useAppPresenceSync } from './hooks/useAppPresenceSync'
import { useAppActions } from './hooks/useAppActions'
import { useFolderSessionState } from './hooks/useFolderSessionState'
import { buildFilterChips } from './model/filterChips'
import {
  captureScanGeneration,
  deriveIndexingBrowseMode,
  normalizeIndexingGeneration,
} from './model/indexingBrowseMode'

// S0/T1 seam anchors (see docs/dev_notes/20260211_s0_t1_seam_map.md):
// - T13a data scope: folder/search/similarity loading + derived pools.
// - T13b selection/viewer/compare: selection state, openViewer/closeViewer, openCompare/closeCompare.
// - T13c presence/sync: useAppPresenceSync lifecycle, subscriptions, and activity derivations.
// - T13d mutations/actions: uploadFiles/moveSelectedToFolder/view persistence actions.
// - T14/T15 selectors + render/effect optimization: filter/select helpers and memo/effect boundaries.

/** Local storage keys for persisted settings */
const STORAGE_KEYS = {
  sortKey: 'sortKey',
  sortDir: 'sortDir',
  sortSpec: 'sortSpec',
  starFilters: 'starFilters',
  filterAst: 'filterAst',
  selectedMetric: 'selectedMetric',
  viewMode: 'viewMode',
  gridItemSize: 'gridItemSize',
  leftOpen: 'leftOpen',
  rightOpen: 'rightOpen',
} as const

const INDEXING_MODE_STORAGE_KEYS = {
  scanGeneration: 'indexingScanGeneration',
  recentGeneration: 'indexingMostRecentGeneration',
} as const

function readStoredGeneration(key: string): string | null {
  if (typeof window === 'undefined') return null
  try {
    const raw = window.localStorage.getItem(key)
    return normalizeIndexingGeneration(raw)
  } catch {
    return null
  }
}

function writeStoredGeneration(key: string, generation: string): void {
  if (typeof window === 'undefined') return
  try {
    window.localStorage.setItem(key, generation)
  } catch {
    // Ignore storage failures.
  }
}

function prefetchFilesAndThumbs(paths: readonly string[], context: FullFilePrefetchContext): void {
  for (const path of paths) {
    api.prefetchFile(path, context)
    api.prefetchThumb(path)
  }
}

export default function AppShell() {
  // Navigation state
  const [current, setCurrent] = useState<string>('/')
  const [query, setQuery] = useState('')
  const [similarityOpen, setSimilarityOpen] = useState(false)
  const [similarityState, setSimilarityState] = useState<SimilarityState | null>(null)
  
  // Viewer zoom state
  const [requestedZoom, setRequestedZoom] = useState<number | null>(null)
  const [currentZoom, setCurrentZoom] = useState(100)

  // Browser zoom (best-effort) for UI proportion warning
  const [browserZoomPercent, setBrowserZoomPercent] = useState<number | null>(null)
  
  // View state (filters + sort)
  const [viewState, setViewState] = useState<ViewState>(() => ({
    filters: { and: [] },
    sort: { kind: 'builtin', key: 'added', dir: 'desc' },
    selectedMetric: undefined,
  }))
  const [randomSeed, setRandomSeed] = useState<number>(() => Date.now())
  const [viewMode, setViewMode] = useState<ViewMode>('adaptive')
  const [gridItemSize, setGridItemSize] = useState<number>(220)
  const [mobileSelectMode, setMobileSelectMode] = useState(false)
  const [leftOpen, setLeftOpen] = useState(true)
  const [rightOpen, setRightOpen] = useState(true)
  const [viewportWidth, setViewportWidth] = useState(() => (
    typeof window === 'undefined' ? 1440 : window.innerWidth
  ))
  const isNarrowViewport = useMediaQuery(LAYOUT_MEDIA_QUERIES.narrow)
  const [leftTool, setLeftTool] = useState<'folders' | 'metrics'>('folders')
  const [views, setViews] = useState<SavedView[]>([])
  const [activeViewId, setActiveViewId] = useState<string | null>(null)
  const [folderCountsVersion, setFolderCountsVersion] = useState(0)
  const [scanGeneration, setScanGeneration] = useState<string | null>(() => (
    readStoredGeneration(INDEXING_MODE_STORAGE_KEYS.scanGeneration)
  ))
  const [recentGeneration, setRecentGeneration] = useState<string | null>(() => (
    readStoredGeneration(INDEXING_MODE_STORAGE_KEYS.recentGeneration)
  ))
  const [scanStableMode, setScanStableMode] = useState(false)
  
  // Local optimistic updates for star ratings
  const [localStarOverrides, setLocalStarOverrides] = useState<Record<string, StarRating>>({})
  
  // Refs
  const appRef = useRef<HTMLDivElement>(null)
  const gridShellRef = useRef<HTMLDivElement>(null)
  const gridScrollRef = useRef<HTMLDivElement>(null)
  const toolbarRef = useRef<HTMLDivElement>(null)
  const uploadInputRef = useRef<HTMLInputElement>(null)
  const similarityPrevSelectionRef = useRef<string[] | null>(null)
  const initialHashSyncRef = useRef(false)

  const { leftW, rightW, onResizeLeft, onResizeRight } = useSidebars(appRef, leftTool)
  const {
    getHydratedSnapshot: getFolderHydratedSnapshot,
    getTopAnchorPath,
    saveHydratedSnapshot: saveFolderHydratedSnapshot,
    saveTopAnchorPath,
    invalidateSubtree: invalidateFolderSessionSubtree,
  } = useFolderSessionState()
  const [restoreGridToTopAnchorToken, setRestoreGridToTopAnchorToken] = useState(0)
  const [scopeSessionResetToken, setScopeSessionResetToken] = useState(0)

  const queryClient = useQueryClient()
  const syncStatus = useSyncStatus()
  const pollingEnabled = usePollingEnabled()
  const oldestInflightAgeMs = useOldestInflightAgeMs()
  const [localTypingActive, setLocalTypingActive] = useState(false)

  const {
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
    embeddingsLoading,
    embeddingsError,
    poolItems,
    similarityItems,
    items,
    totalCount,
    filteredCount,
    scopeTotal,
    rootTotal,
    browseHydrationPending,
    browseHydrationProgress,
  } = useAppDataScope({
    current,
    query,
    similarityState,
    scanStableMode,
    viewState,
    randomSeed,
    localStarOverrides,
    onFolderHydratedSnapshot: saveFolderHydratedSnapshot,
    getCachedHydratedSnapshot: getFolderHydratedSnapshot,
    sessionResetToken: scopeSessionResetToken,
  })
  const currentGalleryId = useMemo(() => sanitizePath(current || '/'), [current])
  const starFilters = useMemo(() => getStarFilter(viewState.filters), [viewState.filters])

  const itemPaths = useMemo(() => items.map((i) => i.path), [items])
  const focusGridCell = useCallback((path: string | null | undefined) => {
    if (!path) return
    const el = document.getElementById(`cell-${encodeURIComponent(path)}`)
    el?.focus()
  }, [])
  const selectionPool = similarityState ? similarityItems : poolItems
  const {
    selectedPaths,
    setSelectedPaths,
    viewer,
    compareOpen,
    restoreGridToSelectionToken,
    bumpRestoreGridToSelectionToken,
    selectedItems,
    compareItems,
    comparePaths,
    compareIndexClamped,
    compareA,
    compareB,
    canComparePrev,
    canCompareNext,
    compareEnabled,
    canPrevImage,
    canNextImage,
    overlayActive,
    rememberFocusedPath,
    openViewer,
    closeViewer,
    openCompare,
    closeCompare,
    handleCompareNavigate,
    handleNavigate,
    resetViewerState,
    clearViewerForSearch,
    syncHashImageSelection,
  } = useAppSelectionViewerCompare({
    current,
    itemPaths,
    items,
    selectionPool,
    focusGridCell,
  })
  const syncHashImageSelectionRef = useLatestRef(syncHashImageSelection)
  const bumpRestoreGridToSelectionTokenRef = useLatestRef(bumpRestoreGridToSelectionToken)
  // Initialize current folder from URL hash and keep in sync.
  useEffect(() => {
    const applyHash = (raw: string) => {
      const norm = sanitizePath(raw)
      const imageTarget = isLikelyImagePath(norm) ? norm : null
      const folderTarget = imageTarget ? getParentPath(norm) : norm
      const isInitialHashSync = !initialHashSyncRef.current
      initialHashSyncRef.current = true
      syncHashImageSelectionRef.current(imageTarget)
      // Only trigger "restore selection into view" when the folder/tab actually changes.
      setCurrent((prev) => {
        const nextScope = resolveScopeFromHashTarget(
          prev,
          folderTarget,
          imageTarget,
          isInitialHashSync,
        )
        if (prev === nextScope) return prev
        bumpRestoreGridToSelectionTokenRef.current()
        return nextScope
      })
    }

    applyHash(readHash())
    const onHash = () => applyHash(readHash())
    window.addEventListener('hashchange', onHash)
    return () => window.removeEventListener('hashchange', onHash)
  }, [bumpRestoreGridToSelectionTokenRef, syncHashImageSelectionRef])
  const metricsBaseItems = selectionPool
  const metricSortKey = similarityState ? null : (viewState.sort.kind === 'metric' ? viewState.sort.key : null)
  const hasMetricScrollbar = useMemo(
    () => hasMetricSortValues(items, metricSortKey),
    [items, metricSortKey],
  )

  const updateItemCaches = useCallback((payload: { path: string; star?: StarRating | null; metrics?: Record<string, number | null> | null; comments?: string | null }) => {
    const hasStar = Object.prototype.hasOwnProperty.call(payload, 'star')
    const hasMetrics = payload.metrics !== undefined
    const hasComments = payload.comments !== undefined
    if (!hasStar && !hasMetrics && !hasComments) return

    const updateItem = (item: Item): Item => {
      if (item.path !== payload.path) return item
      let next = item
      if (hasStar && item.star !== payload.star) {
        next = { ...next, star: payload.star ?? null }
      }
      if (hasMetrics) {
        next = { ...next, metrics: payload.metrics ?? undefined }
      }
      if (hasComments && item.comments !== payload.comments) {
        next = { ...next, comments: payload.comments ?? '' }
      }
      return next
    }

    const updateList = <T extends { items: Item[] }>(old: T | undefined): T | undefined => {
      if (!old) return old
      let changed = false
      const items = old.items.map((it) => {
        const next = updateItem(it)
        if (next !== it) changed = true
        return next
      })
      return changed ? { ...old, items } : old
    }

    queryClient.setQueriesData<FolderIndex>({
      predicate: ({ queryKey }) => Array.isArray(queryKey) && queryKey[0] === 'folder',
    }, updateList)

    queryClient.setQueriesData<SearchResult>({
      predicate: ({ queryKey }) => Array.isArray(queryKey) && queryKey[0] === 'search',
    }, updateList)
  }, [queryClient])

  const {
    connectionStatus,
    connectionLabel,
    presence,
    editingCount,
    recentEditActive,
    hasEdits,
    lastEditedLabel,
    persistenceEnabled,
    indexing,
    compareExportCapability,
    highlightedPaths,
    onVisiblePathsChange: handleVisiblePathsChange,
    offViewSummary,
    recentTouchesDisplay,
    clearOffViewActivity,
  } = useAppPresenceSync({
    current,
    currentGalleryId,
    itemPaths,
    items,
    queryClient,
    updateItemCaches,
    setLocalStarOverrides,
  })

  useEffect(() => {
    const nextScanGeneration = captureScanGeneration(scanGeneration, indexing)
    if (!nextScanGeneration || nextScanGeneration === scanGeneration) return
    setScanGeneration(nextScanGeneration)
    writeStoredGeneration(INDEXING_MODE_STORAGE_KEYS.scanGeneration, nextScanGeneration)
  }, [indexing, scanGeneration])

  const indexingBrowseMode = useMemo(() => {
    return deriveIndexingBrowseMode(indexing, {
      scanGeneration,
      recentGeneration,
    })
  }, [indexing, recentGeneration, scanGeneration])

  useEffect(() => {
    setScanStableMode((prev) => (
      prev === indexingBrowseMode.scanStableActive
        ? prev
        : indexingBrowseMode.scanStableActive
    ))
  }, [indexingBrowseMode.scanStableActive])

  const handleSwitchToMostRecent = useCallback(() => {
    const generation = normalizeIndexingGeneration(indexing?.generation) ?? scanGeneration
    if (!generation) return
    if (recentGeneration !== generation) {
      setRecentGeneration(generation)
      writeStoredGeneration(INDEXING_MODE_STORAGE_KEYS.recentGeneration, generation)
    }
    setViewState((prev) => {
      if (prev.sort.kind === 'builtin' && prev.sort.key === 'added' && prev.sort.dir === 'desc') {
        return prev
      }
      return {
        ...prev,
        sort: { kind: 'builtin', key: 'added', dir: 'desc' },
      }
    })
  }, [indexing?.generation, recentGeneration, scanGeneration])

  const handleGridTopAnchorPathChange = useCallback((topAnchorPath: string | null) => {
    if (!topAnchorPath) return
    saveTopAnchorPath(current, topAnchorPath)
  }, [current, saveTopAnchorPath])
  const restoreGridTopAnchorPath = useMemo(
    () => getTopAnchorPath(current),
    [current, getTopAnchorPath],
  )

  useEffect(() => {
    setRestoreGridToTopAnchorToken((token) => token + 1)
  }, [current])

  const invalidateDerivedCounts = useCallback(() => {
    setFolderCountsVersion((prev) => prev + 1)
  }, [])

  const normalizeRefreshPath = useCallback((path: string): string => {
    const safe = sanitizePath(path || '/')
    return safe === '' ? '/' : safe
  }, [])

  const invalidateFolderSubtree = useCallback((target: string) => {
    const matches = (candidate: string) => {
      if (target === '/') return true
      return candidate === target || candidate.startsWith(`${target}/`)
    }

    queryClient.invalidateQueries({
      predicate: ({ queryKey }) => {
        if (!Array.isArray(queryKey)) return false
        if (queryKey[0] !== 'folder') return false
        const keyPath = typeof queryKey[1] === 'string' ? queryKey[1] : ''
        return matches(keyPath)
      },
    })
  }, [queryClient])

  const refreshFolderPath = useCallback(async (path: string) => {
    const target = normalizeRefreshPath(path)
    await api.refreshFolder(target)
    invalidateFolderSubtree(target)
    invalidateDerivedCounts()
    invalidateFolderSessionSubtree(target)

    if (current === target || current.startsWith(target === '/' ? '/' : `${target}/`)) {
      setScopeSessionResetToken((token) => token + 1)
      await refetch()
    }

    thumbCache.evictPrefix(target)
    fileCache.evictPrefix(target)
  }, [
    current,
    invalidateDerivedCounts,
    invalidateFolderSessionSubtree,
    invalidateFolderSubtree,
    normalizeRefreshPath,
    refetch,
  ])

  const handlePullRefreshFolders = useCallback(async () => {
    try {
      await refreshFolderPath(current)
    } catch (err) {
      console.error('Failed to refresh folder:', err)
    }
  }, [current, refreshFolderPath])

  // Compute star counts for the filter UI
  const starCounts = useMemo(() => {
    const baseItems = similarityState ? similarityItems : poolItems
    return buildStarCounts(baseItems, localStarOverrides)
  }, [similarityState, similarityItems, poolItems, localStarOverrides])

  const metricKeys = useMemo(() => {
    const baseItems = similarityState ? similarityItems : poolItems
    return collectMetricKeys(baseItems)
  }, [similarityState, similarityItems, poolItems])

  useEffect(() => {
    if (similarityActive) return
    if (!metricKeys.length) return
    setViewState((prev) => {
      const nextKey = prev.selectedMetric && metricKeys.includes(prev.selectedMetric)
        ? prev.selectedMetric
        : metricKeys[0]
      if (nextKey === prev.selectedMetric) return prev
      return { ...prev, selectedMetric: nextKey }
    })
  }, [metricKeys, similarityActive])

  useEffect(() => {
    if (similarityActive) return
    if (viewState.sort.kind !== 'metric') return
    if (metricKeys.includes(viewState.sort.key)) return
    setViewState((prev) => ({
      ...prev,
      sort: { kind: 'builtin', key: 'added', dir: prev.sort.dir },
    }))
  }, [metricKeys, viewState.sort, similarityActive])

  const activeFilterCount = useMemo(() => countActiveFilters(viewState.filters), [viewState.filters])
  const showFilteredCounts = similarityActive || searching || activeFilterCount > 0

  const syncLabel = (() => {
    if (syncStatus.state === 'syncing') return 'Syncing…'
    if (syncStatus.state === 'error') {
      return syncStatus.message ? `Not saved — ${syncStatus.message}` : 'Not saved — retry'
    }
    return 'All changes saved'
  })()
  const longSync = oldestInflightAgeMs != null && oldestInflightAgeMs > LONG_SYNC_THRESHOLD_MS
  const isOffline = connectionStatus === 'offline' || connectionStatus === 'connecting' || connectionStatus === 'idle'
  const isUnstable = connectionStatus === 'reconnecting' || pollingEnabled || syncStatus.state === 'error' || longSync
  const indicatorState = deriveIndicatorState({
    isOffline,
    isUnstable,
    recentEditActive,
    editingCount,
  })
  const displayItemCount = getDisplayItemCount(
    similarityActive,
    showFilteredCounts,
    filteredCount,
    scopeTotal
  )
  const displayTotalCount = getDisplayTotalCount(
    similarityActive,
    showFilteredCounts,
    totalCount,
    scopeTotal,
    rootTotal,
    current
  )

  const similarityQueryLabel = useMemo(() => getSimilarityQueryLabel(similarityState), [similarityState])
  const similarityCountLabel = useMemo(
    () => getSimilarityCountLabel(similarityState !== null, activeFilterCount, filteredCount, totalCount),
    [similarityState, activeFilterCount, filteredCount, totalCount],
  )
  const showGridHydrationLoading = shouldShowGridHydrationLoading({
    similarityActive,
    searching,
    itemCount: items.length,
    isLoading,
    browseHydrationPending,
  })

  const updateFilters = useCallback((updater: (filters: FilterAST) => FilterAST) => {
    setViewState((prev) => ({
      ...prev,
      filters: updater(prev.filters),
    }))
  }, [])

  const handleFiltersChange = useCallback((filters: FilterAST) => {
    setViewState((prev) => ({
      ...prev,
      filters,
    }))
  }, [])

  const handleClearStars = useCallback(() => {
    updateFilters((filters) => setStarFilter(filters, []))
  }, [updateFilters])

  const handleClearFilters = useCallback(() => {
    setViewState((prev) => ({
      ...prev,
      filters: { and: [] },
    }))
  }, [])

  const clearSimilarity = useCallback(() => {
    setSimilarityState(null)
    const prevSelection = similarityPrevSelectionRef.current
    similarityPrevSelectionRef.current = null
    if (prevSelection && prevSelection.length) {
      setSelectedPaths(prevSelection)
      bumpRestoreGridToSelectionToken()
    } else {
      setSelectedPaths([])
    }
  }, [bumpRestoreGridToSelectionToken, setSelectedPaths])

  const handleRevealOffView = useCallback(() => {
    if (similarityState) {
      clearSimilarity()
    }
    setQuery('')
    setViewState((prev) => ({ ...prev, filters: { and: [] } }))
  }, [clearSimilarity, similarityState])

  const handleSimilaritySearch = useCallback(async (payload: EmbeddingSearchRequest) => {
    if (!similarityState && similarityPrevSelectionRef.current === null) {
      similarityPrevSelectionRef.current = selectedPaths
    }
    const res = await api.searchEmbeddings(payload)
    setSimilarityState({
      embedding: res.embedding,
      queryPath: payload.query_path ?? null,
      queryVector: payload.query_vector_b64 ?? null,
      topK: payload.top_k ?? 50,
      minScore: payload.min_score ?? null,
      items: res.items,
      createdAt: Date.now(),
    })
    if (res.items.length) {
      const preferred = payload.query_path && res.items.some((item) => item.path === payload.query_path)
        ? payload.query_path
        : res.items[0].path
      setSelectedPaths([preferred])
      bumpRestoreGridToSelectionToken()
    } else {
      setSelectedPaths([])
    }
  }, [bumpRestoreGridToSelectionToken, selectedPaths, setSelectedPaths, similarityState])

  const handleMetricRange = useCallback((key: string, range: { min: number; max: number } | null) => {
    updateFilters((filters) => setMetricRangeFilter(filters, key, range))
  }, [updateFilters])

  const filterChips = useMemo(() => buildFilterChips(viewState.filters, {
    clearStars: handleClearStars,
    clearStarsNotIn: () => updateFilters((filters) => setStarsNotInFilter(filters, [])),
    clearNameContains: () => updateFilters((filters) => setNameContainsFilter(filters, '')),
    clearNameNotContains: () => updateFilters((filters) => setNameNotContainsFilter(filters, '')),
    clearCommentsContains: () => updateFilters((filters) => setCommentsContainsFilter(filters, '')),
    clearCommentsNotContains: () => updateFilters((filters) => setCommentsNotContainsFilter(filters, '')),
    clearUrlContains: () => updateFilters((filters) => setUrlContainsFilter(filters, '')),
    clearUrlNotContains: () => updateFilters((filters) => setUrlNotContainsFilter(filters, '')),
    clearDateRange: () => updateFilters((filters) => setDateRangeFilter(filters, null)),
    clearWidthCompare: () => updateFilters((filters) => setWidthCompareFilter(filters, null)),
    clearHeightCompare: () => updateFilters((filters) => setHeightCompareFilter(filters, null)),
    clearMetricRange: (key: string) => handleMetricRange(key, null),
  }), [viewState.filters, handleClearStars, handleMetricRange, updateFilters])

  const handleToggleStar = useCallback((v: number) => {
    const next = new Set(starFilters)
    if (next.has(v)) {
      next.delete(v)
    } else {
      next.add(v)
    }
    setViewState((prev) => ({
      ...prev,
      filters: setStarFilter(prev.filters, Array.from(next)),
    }))
  }, [starFilters])

  const openMetricsPanel = useCallback(() => {
    setLeftOpen(true)
    setLeftTool('metrics')
  }, [])

  const handleSortChange = useCallback((next: SortSpec) => {
    setViewState((prev) => ({ ...prev, sort: next }))
    if (next.kind === 'builtin' && next.key === 'random') {
      setRandomSeed(Date.now())
    }
  }, [])

  const formatTitle = useCallback((path: string) => {
    if (path === '/' || path === '') return 'Lenslet | Root'
    const segments = path.split('/').filter(Boolean)
    if (!segments.length) return 'Lenslet'
    const tail = segments.slice(-2).join('/')
    const display = segments.length > 2 ? `.../${tail}` : `/${tail}`
    return `Lenslet | ${display}`
  }, [])

  const scopeLabel = useMemo(() => formatScopeLabel(current), [current])

  useEffect(() => {
    document.title = formatTitle(current)
  }, [current, formatTitle])

  useEffect(() => {
    let alive = true
    api.getViews()
      .then((payload: ViewsPayload) => {
        if (!alive) return
        setViews(payload.views || [])
      })
      .catch(() => {
        if (!alive) return
        setViews([])
      })
    return () => { alive = false }
  }, [])

  // Clear selection when entering search mode
  useEffect(() => {
    if (searching) {
      setSelectedPaths([])
      clearViewerForSearch(current)
    }
  }, [clearViewerForSearch, current, searching, setSelectedPaths])

  // Track toolbar height so overlays align on small screens
  useEffect(() => {
    const appEl = appRef.current
    const toolbarEl = toolbarRef.current
    if (!appEl || !toolbarEl) return
    const update = () => {
      const h = Math.max(48, Math.round(toolbarEl.getBoundingClientRect().height))
      appEl.style.setProperty('--toolbar-h', `${h}px`)
    }
    update()
    const resizeObserverCtor = (window as Window & { ResizeObserver?: typeof ResizeObserver }).ResizeObserver
    if (resizeObserverCtor) {
      const ro = new resizeObserverCtor(update)
      ro.observe(toolbarEl)
      return () => ro.disconnect()
    }
    window.addEventListener('resize', update)
    return () => window.removeEventListener('resize', update)
  }, [])

  // Load persisted settings on mount
  useEffect(() => {
    try {
      const storedSortKey = localStorage.getItem(STORAGE_KEYS.sortKey)
      const storedSortDir = localStorage.getItem(STORAGE_KEYS.sortDir)
      const storedSortSpec = localStorage.getItem(STORAGE_KEYS.sortSpec)
      const storedStarFilters = localStorage.getItem(STORAGE_KEYS.starFilters)
      const storedFilterAst = localStorage.getItem(STORAGE_KEYS.filterAst)
      const storedSelectedMetric = localStorage.getItem(STORAGE_KEYS.selectedMetric)
      const storedViewMode = localStorage.getItem(STORAGE_KEYS.viewMode) as ViewMode | null
      const storedGridSize = localStorage.getItem(STORAGE_KEYS.gridItemSize)
      const storedLeftOpen = localStorage.getItem(STORAGE_KEYS.leftOpen)
      const storedRightOpen = localStorage.getItem(STORAGE_KEYS.rightOpen)

      const parseSortSpec = (raw: string | null): SortSpec | null => {
        if (!raw) return null
        const parsed = safeJsonParse<SortSpec>(raw)
        if (!parsed || typeof parsed !== 'object') return null
        if (parsed.kind === 'builtin') {
          if ((parsed.key === 'name' || parsed.key === 'added' || parsed.key === 'random') &&
            (parsed.dir === 'asc' || parsed.dir === 'desc')) {
            return parsed
          }
        }
        if (parsed.kind === 'metric') {
          if (typeof parsed.key === 'string' && parsed.key.length > 0 &&
            (parsed.dir === 'asc' || parsed.dir === 'desc')) {
            return parsed
          }
        }
        return null
      }

      const sort: SortSpec = parseSortSpec(storedSortSpec) ?? {
        kind: 'builtin',
        key: storedSortKey === 'name' || storedSortKey === 'added' || storedSortKey === 'random' ? storedSortKey : 'added',
        dir: storedSortDir === 'asc' || storedSortDir === 'desc' ? storedSortDir : 'desc',
      }
      if (sort.key === 'random') {
        setRandomSeed(Date.now())
      }

      const parseFilterAst = (raw: string | null): FilterAST | null => {
        if (!raw) return null
        const parsed = safeJsonParse<unknown>(raw)
        return normalizeFilterAst(parsed)
      }

      let filters = parseFilterAst(storedFilterAst) ?? { and: [] }
      if (storedStarFilters) {
        const parsed = safeJsonParse<number[]>(storedStarFilters)
        if (Array.isArray(parsed)) {
          const stars = parsed.filter((n) => [0, 1, 2, 3, 4, 5].includes(n))
          filters = setStarFilter(filters, stars)
        }
      }

      setViewState((prev) => ({
        ...prev,
        sort,
        filters,
        selectedMetric: storedSelectedMetric || prev.selectedMetric,
      }))

      if (storedViewMode === 'grid' || storedViewMode === 'adaptive') {
        setViewMode(storedViewMode)
      }
      if (storedGridSize) {
        const size = Number(storedGridSize)
        if (!isNaN(size) && size >= 80 && size <= 500) {
          setGridItemSize(size)
        }
      }
      if (storedLeftOpen === '0' || storedLeftOpen === 'false') setLeftOpen(false)
      if (storedRightOpen === '0' || storedRightOpen === 'false') setRightOpen(false)
    } catch {
      // Ignore localStorage errors (private browsing, etc.)
    }
  }, [])

  // Auto-collapse side panels on narrow screens
  useEffect(() => {
    if (!isNarrowViewport) return
    setLeftOpen(false)
    setRightOpen(false)
  }, [isNarrowViewport])

  // Track browser zoom changes (best-effort heuristic)
  useEffect(() => {
    if (typeof window === 'undefined') return
    const baseCandidates = [1, 1.25, 1.5, 1.75, 2, 3, 4]
    const nearestBase = (dpr: number) => baseCandidates.reduce((closest, candidate) => (
      Math.abs(candidate - dpr) < Math.abs(closest - dpr) ? candidate : closest
    ), baseCandidates[0])
    const update = () => {
      const dpr = window.devicePixelRatio || 1
      const base = nearestBase(dpr)
      const pinchScale = window.visualViewport?.scale ?? 1
      const zoom = (dpr * pinchScale) / base
      if (!Number.isFinite(zoom)) {
        setBrowserZoomPercent(null)
        return
      }
      const percent = Math.round(zoom * 100)
      const clamped = Math.min(500, Math.max(25, percent))
      setBrowserZoomPercent(clamped)
    }
    update()
    window.addEventListener('resize', update)
    window.addEventListener('orientationchange', update)
    const viewport = window.visualViewport
    if (viewport) viewport.addEventListener('resize', update)
    return () => {
      window.removeEventListener('resize', update)
      window.removeEventListener('orientationchange', update)
      if (viewport) viewport.removeEventListener('resize', update)
    }
  }, [])

  // Persist settings when they change
  useEffect(() => {
    try {
      localStorage.setItem(STORAGE_KEYS.sortKey, viewState.sort.kind === 'builtin' ? viewState.sort.key : 'added')
      localStorage.setItem(STORAGE_KEYS.sortDir, viewState.sort.dir)
      localStorage.setItem(STORAGE_KEYS.sortSpec, JSON.stringify(viewState.sort))
      const starFilters = getStarFilter(viewState.filters)
      localStorage.setItem(STORAGE_KEYS.starFilters, JSON.stringify(starFilters))
      localStorage.setItem(STORAGE_KEYS.filterAst, JSON.stringify(viewState.filters))
      if (viewState.selectedMetric) {
        localStorage.setItem(STORAGE_KEYS.selectedMetric, viewState.selectedMetric)
      } else {
        localStorage.removeItem(STORAGE_KEYS.selectedMetric)
      }
      localStorage.setItem(STORAGE_KEYS.viewMode, viewMode)
      localStorage.setItem(STORAGE_KEYS.gridItemSize, String(gridItemSize))
      localStorage.setItem(STORAGE_KEYS.leftOpen, leftOpen ? '1' : '0')
      localStorage.setItem(STORAGE_KEYS.rightOpen, rightOpen ? '1' : '0')
    } catch {
      // Ignore localStorage errors
    }
  }, [viewState, viewMode, gridItemSize, leftOpen, rightOpen])

  useEffect(() => {
    if (typeof window === 'undefined') return
    const update = () => setViewportWidth(window.innerWidth)
    update()
    window.addEventListener('resize', update)
    window.addEventListener('orientationchange', update)
    return () => {
      window.removeEventListener('resize', update)
      window.removeEventListener('orientationchange', update)
    }
  }, [])

  const mobileSelectEnabled = viewportWidth <= LAYOUT_BREAKPOINTS.mobileMax
  const gridItemSizeRef = useLatestRef(gridItemSize)

  useEffect(() => {
    if (mobileSelectEnabled) return
    if (!mobileSelectMode) return
    setMobileSelectMode(false)
  }, [mobileSelectEnabled, mobileSelectMode])

  // Ctrl + scroll adjusts thumbnail size (override browser zoom)
  useEffect(() => {
    const shell = gridShellRef.current
    if (!shell) return
    const clamp = (v: number) => Math.min(500, Math.max(80, v))
    const onWheel = (e: WheelEvent) => {
      if (!e.ctrlKey) return
      if (viewer || compareOpen) return
      e.preventDefault()
      setGridItemSize((prev) => clamp(prev + (e.deltaY < 0 ? 20 : -20)))
    }
    shell.addEventListener('wheel', onWheel, { passive: false })
    return () => shell.removeEventListener('wheel', onWheel)
  }, [viewer, compareOpen])

  // Pinch to resize thumbnails on touch devices
  useEffect(() => {
    if (viewer || compareOpen) return
    const shell = gridShellRef.current
    if (!shell) return
    const clamp = (v: number) => Math.min(500, Math.max(80, v))
    let pinchStart: { dist: number; size: number } | null = null

    const getDistance = (touches: TouchList) => {
      if (touches.length < 2) return 0
      const [a, b] = [touches[0], touches[1]]
      return Math.hypot(a.clientX - b.clientX, a.clientY - b.clientY)
    }

    const onTouchStart = (e: TouchEvent) => {
      if (e.touches.length !== 2) return
      const dist = getDistance(e.touches)
      if (!dist) return
      pinchStart = { dist, size: gridItemSizeRef.current }
    }

    const onTouchMove = (e: TouchEvent) => {
      if (!pinchStart || e.touches.length !== 2) return
      const dist = getDistance(e.touches)
      if (!dist) return
      e.preventDefault()
      const next = clamp(pinchStart.size * (dist / pinchStart.dist))
      setGridItemSize(next)
    }

    const onTouchEnd = () => { pinchStart = null }

    shell.addEventListener('touchstart', onTouchStart, { passive: true })
    shell.addEventListener('touchmove', onTouchMove, { passive: false })
    shell.addEventListener('touchend', onTouchEnd)
    shell.addEventListener('touchcancel', onTouchEnd)

    return () => {
      shell.removeEventListener('touchstart', onTouchStart)
      shell.removeEventListener('touchmove', onTouchMove)
      shell.removeEventListener('touchend', onTouchEnd)
      shell.removeEventListener('touchcancel', onTouchEnd)
    }
  }, [viewer, compareOpen, gridItemSizeRef])

  // Prefetch neighbors for the open viewer (previous and next)
  useEffect(() => {
    prefetchFilesAndThumbs(getViewerFilePrefetchPaths(itemPaths, viewer), 'viewer')
  }, [viewer, itemPaths])

  useEffect(() => {
    if (!compareOpen) return
    prefetchFilesAndThumbs(getCompareFilePrefetchPaths(comparePaths, compareIndexClamped), 'compare')
  }, [compareOpen, comparePaths, compareIndexClamped])

  // Navigation callbacks
  const openFolder = useCallback((p: string) => {
    resetViewerState()
    const safe = sanitizePath(p)
    setCurrent(safe)
    writeHash(safe)
  }, [resetViewerState])

  const {
    uploading,
    actionError,
    isDraggingOver,
    moveDialog,
    moveFolders,
    moveFoldersLoading,
    ctx,
    setCtx,
    closeMoveDialog,
    openUploadPicker,
    handleUploadInputChange,
    openGridActions,
    openFolderActions,
    openMoveDialogForPaths,
    moveSelectedToFolder,
  } = useAppActions({
    appRef,
    uploadInputRef,
    current,
    currentDirCount: data?.dirs?.length ?? 0,
    selectedPaths,
    setSelectedPaths,
    refetch,
    invalidateDerivedCounts,
  })

  const handleSaveView = useCallback(async () => {
    const name = window.prompt('Save Smart Folder as:', 'New Smart Folder')
    if (!name) return
    const id = makeUniqueViewId(name, views)
    const payload: SavedView = {
      id,
      name,
      pool: { kind: 'folder', path: current },
      view: JSON.parse(JSON.stringify(viewState)),
    }
    const nextViews = [...views.filter((v) => v.id !== id), payload]
    setViews(nextViews)
    setActiveViewId(id)
    try {
      await api.saveViews({ version: 1, views: nextViews })
    } catch (err) {
      if (err instanceof FetchError && err.status === 403) {
        const blob = new Blob([JSON.stringify({ version: 1, views: nextViews }, null, 2)], { type: 'application/json' })
        downloadBlob(blob, `lenslet-smart-folder-${id}.json`)
        alert('No-write mode: exported Smart Folder JSON instead of saving.')
        return
      }
      console.error('Failed to save Smart Folder:', err)
    }
  }, [current, viewState, views])

  useEffect(() => {
    if (!activeViewId) return
    const view = views.find((v) => v.id === activeViewId)
    if (!view) {
      setActiveViewId(null)
      return
    }
    const samePool = view.pool.path === current
    const sameView = JSON.stringify(view.view) === JSON.stringify(viewState)
    if (!samePool || !sameView) {
      setActiveViewId(null)
    }
  }, [activeViewId, views, current, viewState])

  const keyboardStateRef = useLatestRef({
    current,
    items,
    selectedPaths,
    viewer,
    compareOpen,
    mobileSelectMode,
    openFolder,
  })

  // Global keyboard shortcuts
  useEffect(() => {
    const onKey = (e: KeyboardEvent) => {
      const state = keyboardStateRef.current
      // Ignore if in input field
      if (isInputElement(e.target)) return

      // Toggle sidebars
      if ((e.ctrlKey || e.metaKey) && e.key.toLowerCase() === 'b') {
        e.preventDefault()
        if (e.altKey) setRightOpen((v) => !v)
        else setLeftOpen((v) => !v)
        return
      }

      // Ignore if viewer or compare is open (they have their own handlers)
      if (state.viewer || state.compareOpen) return
      
      if (e.key === 'Backspace' || e.key === 'Delete') {
        e.preventDefault()
        state.openFolder(getParentPath(state.current))
      } else if ((e.ctrlKey || e.metaKey) && e.key.toLowerCase() === 'a') {
        e.preventDefault()
        setSelectedPaths(state.items.map((i) => i.path))
      } else if (e.key === 'Escape') {
        if (state.selectedPaths.length) {
          e.preventDefault()
          setSelectedPaths([])
          return
        }
        if (state.mobileSelectMode) {
          e.preventDefault()
          setMobileSelectMode(false)
        }
      } else if (e.key === '/') {
        e.preventDefault()
        const searchInput = document.querySelector('.toolbar-right .input') as HTMLInputElement | null
        searchInput?.focus()
      }
    }
    
    window.addEventListener('keydown', onKey)
    return () => window.removeEventListener('keydown', onKey)
  }, [keyboardStateRef, setSelectedPaths])

  const constrainedSidebars = useMemo(() => constrainSidebarWidths({
    viewportWidth,
    leftOpen,
    rightOpen,
    leftWidth: leftW,
    rightWidth: rightW,
  }), [viewportWidth, leftOpen, rightOpen, leftW, rightW])

  const leftCol = leftOpen ? `${constrainedSidebars.leftWidth}px` : '0px'
  const rightCol = rightOpen ? `${constrainedSidebars.rightWidth}px` : '0px'

  return (
    <div
      className="app-shell grid h-full grid-cols-[var(--left)_1fr_var(--right)]"
      ref={appRef}
      style={{
        ['--left' as any]: leftCol,
        ['--right' as any]: rightCol,
      }}
    >
      <Toolbar
        rootRef={toolbarRef}
        onSearch={setQuery}
        viewerActive={!!viewer}
        onBack={closeViewer}
        zoomPercent={viewer ? currentZoom : undefined}
        onZoomPercentChange={(p)=> setRequestedZoom(p)}
        currentLabel={scopeLabel}
        itemCount={displayItemCount}
        totalCount={displayTotalCount}
        sortSpec={viewState.sort}
        metricKeys={metricKeys}
        onSortChange={handleSortChange}
        sortDisabled={similarityActive || indexingBrowseMode.sortLocked}
        filterCount={activeFilterCount}
        onOpenFilters={openMetricsPanel}
        starFilters={starFilters}
        onToggleStar={handleToggleStar}
        onClearStars={handleClearStars}
        onClearFilters={handleClearFilters}
        starCounts={starCounts}
        viewMode={viewMode}
        onViewMode={setViewMode}
        gridItemSize={gridItemSize}
        onGridItemSize={setGridItemSize}
        leftOpen={leftOpen}
        rightOpen={rightOpen}
        onToggleLeft={()=> setLeftOpen(v=>!v)}
        onToggleRight={()=> setRightOpen(v=>!v)}
        onPrevImage={() => handleNavigate(-1)}
        onNextImage={() => handleNavigate(1)}
        canPrevImage={canPrevImage}
        canNextImage={canNextImage}
        searchDisabled={similarityActive}
        searchPlaceholder={similarityActive ? 'Exit similarity to search' : undefined}
        onUploadClick={openUploadPicker}
        uploadBusy={uploading}
        uploadDisabled={compareOpen}
        multiSelectMode={mobileSelectMode}
        selectedCount={selectedPaths.length}
        onToggleMultiSelectMode={mobileSelectEnabled ? (() => setMobileSelectMode((prev) => !prev)) : undefined}
        syncIndicator={{
          state: indicatorState,
          presence,
          syncLabel,
          connectionLabel,
          lastEditedLabel,
          hasEdits,
          localTypingActive,
          recentTouches: recentTouchesDisplay,
        }}
      />
      <input
        ref={uploadInputRef}
        type="file"
        multiple
        accept="image/*"
        className="sr-only"
        onChange={handleUploadInputChange}
      />
      {leftOpen && (
        <LeftSidebar
          leftTool={leftTool}
          onToolChange={setLeftTool}
          compareEnabled={compareEnabled}
          compareActive={compareOpen}
          onOpenCompare={openCompare}
          views={views}
          activeViewId={activeViewId}
          onActivateView={(view) => {
            setActiveViewId(view.id)
            const safeFilters = normalizeFilterAst(view.view?.filters) ?? { and: [] }
            setViewState({ ...view.view, filters: safeFilters })
            openFolder(view.pool.path)
          }}
          onSaveView={handleSaveView}
          current={current}
          data={data}
          onOpenFolder={(p) => { setActiveViewId(null); openFolder(p) }}
          onOpenFolderActions={openFolderActions}
          onPullRefreshFolders={handlePullRefreshFolders}
          onContextMenu={(e, p) => {
            e.preventDefault()
            openFolderActions(p, { x: e.clientX, y: e.clientY })
          }}
          countVersion={folderCountsVersion}
          items={metricsBaseItems}
          filteredItems={items}
          metricKeys={metricKeys}
          selectedItems={selectedItems}
          selectedMetric={viewState.selectedMetric}
          onSelectMetric={(key) => setViewState((prev) => ({ ...prev, selectedMetric: key }))}
          filters={viewState.filters}
          onChangeRange={handleMetricRange}
          onChangeFilters={handleFiltersChange}
          onResize={onResizeLeft}
        />
      )}
      <div className="grid-shell col-start-2 row-start-2 relative overflow-hidden flex flex-col" ref={gridShellRef}>
        <div aria-live="polite" className="sr-only">
          {selectedPaths.length ? `${selectedPaths.length} selected` : ''}
        </div>
        <StatusBar
          persistenceEnabled={persistenceEnabled}
          indexing={indexing}
          showSwitchToMostRecentBanner={indexingBrowseMode.showSwitchToMostRecentBanner}
          onSwitchToMostRecent={handleSwitchToMostRecent}
          offViewSummary={offViewSummary}
          canRevealOffView={showFilteredCounts}
          onRevealOffView={handleRevealOffView}
          onClearOffView={clearOffViewActivity}
          browserZoomPercent={browserZoomPercent}
        />
        {actionError && (
          <div className="border-b border-border bg-panel px-3 py-2">
            <div className="ui-banner ui-banner-danger text-xs">{actionError}</div>
          </div>
        )}
        {similarityState && (
          <div className="border-b border-border bg-panel">
            <div className="px-3 py-2 flex flex-wrap items-center gap-2">
              <div className="ui-banner ui-banner-accent text-xs flex flex-wrap items-center gap-2">
                <span className="font-semibold">Similarity mode</span>
                <span className="text-muted">Embedding: {similarityState.embedding}</span>
                {similarityQueryLabel && (
                  <span className="text-muted">Query: {similarityQueryLabel}</span>
                )}
                {similarityCountLabel && (
                  <span className="text-muted">Results: {similarityCountLabel}</span>
                )}
                <span className="text-muted">Top K: {similarityState.topK}</span>
                {similarityState.minScore != null && (
                  <span className="text-muted">Min score: {similarityState.minScore}</span>
                )}
              </div>
              <button className="btn btn-sm" onClick={clearSimilarity}>
                Exit similarity
              </button>
            </div>
          </div>
        )}
        {filterChips.length > 0 && (
          <div className="sticky top-0 z-10 px-3 py-2 bg-panel border-b border-border">
            <div className="flex flex-wrap items-center gap-2">
              <span className="text-[11px] uppercase tracking-wide text-muted">Filters</span>
              {filterChips.map((chip) => (
                <span key={chip.id} className="filter-chip">
                  <span className="truncate max-w-[240px]" title={chip.label}>{chip.label}</span>
                  <button
                    className="filter-chip-remove"
                    aria-label={`Clear filter ${chip.label}`}
                    onClick={chip.onRemove}
                  >
                    ×
                  </button>
                </span>
              ))}
              <button className="btn btn-sm btn-ghost text-xs" onClick={handleClearFilters}>
                Clear all
              </button>
            </div>
          </div>
        )}
        <div className="flex-1 min-h-0 relative">
          <VirtualGrid
            items={items}
            selected={selectedPaths}
            restoreToSelectionToken={restoreGridToSelectionToken}
            restoreToTopAnchorToken={restoreGridToTopAnchorToken}
            restoreToTopAnchorPath={restoreGridTopAnchorPath}
            multiSelectMode={mobileSelectEnabled && mobileSelectMode}
            onSelectionChange={setSelectedPaths}
            onOpenViewer={(p) => { rememberFocusedPath(p); openViewer(p); setSelectedPaths([p]) }}
            highlight={searching ? normalizedQ : ''}
            recentlyUpdated={highlightedPaths}
            onVisiblePathsChange={handleVisiblePathsChange}
            onTopAnchorPathChange={handleGridTopAnchorPathChange}
            suppressSelectionHighlight={overlayActive}
            viewMode={viewMode}
            targetCellSize={gridItemSize}
            onContextMenuItem={(e, path) => {
              e.preventDefault()
              openGridActions(path, { x: e.clientX, y: e.clientY })
            }}
            onOpenItemActions={openGridActions}
            scrollRef={gridScrollRef}
            hideScrollbar={hasMetricScrollbar}
            isHydrationLoading={showGridHydrationLoading}
            hydrationProgress={browseHydrationProgress}
          />
          {hasMetricScrollbar && metricSortKey && (
            <MetricScrollbar
              items={items}
              metricKey={metricSortKey}
              scrollRef={gridScrollRef}
              sortDir={viewState.sort.dir}
            />
          )}
        </div>
        {/* Bottom selection bar removed intentionally */}
      </div>
      {rightOpen && (
        <Inspector
          path={selectedPaths[0] ?? null}
          selectedPaths={selectedPaths}
          items={items}
          compareActive={compareOpen}
          compareA={compareA}
          compareB={compareB}
          onOpenCompare={openCompare}
          sortSpec={viewState.sort}
          onResize={onResizeRight}
          onStarChanged={(paths, val)=>{
            setLocalStarOverrides(prev => { const next = { ...prev }; for (const p of paths) next[p] = val; return next })
          }}
          onFindSimilar={() => setSimilarityOpen(true)}
          embeddingsAvailable={embeddingsAvailable}
          embeddingsLoading={embeddingsLoading}
          compareExportSupportsV2={compareExportCapability.supportsV2}
          compareExportMaxPathsV2={compareExportCapability.maxPathsV2}
          onLocalTypingChange={setLocalTypingActive}
        />
      )}
      <SimilarityModal
        open={similarityOpen}
        embeddings={embeddings}
        rejected={embeddingsRejected}
        selectedPath={selectedPaths[0] ?? null}
        embeddingsLoading={embeddingsLoading}
        embeddingsError={embeddingsError}
        onClose={() => setSimilarityOpen(false)}
        onSearch={handleSimilaritySearch}
      />
      {viewer && (
        <Viewer
          path={viewer}
          onClose={closeViewer}
          onZoomChange={(p)=> setCurrentZoom(Math.round(p))}
          requestedZoomPercent={requestedZoom}
          onZoomRequestConsumed={()=> setRequestedZoom(null)}
          canPrev={canPrevImage}
          canNext={canNextImage}
          onNavigate={handleNavigate}
        />
      )}
      {compareOpen && (
        <CompareViewer
          aItem={compareA}
          bItem={compareB}
          index={compareIndexClamped}
          total={compareItems.length}
          canPrev={canComparePrev}
          canNext={canCompareNext}
          onNavigate={handleCompareNavigate}
          onClose={closeCompare}
        />
      )}
      {moveDialog && (
        <MoveToDialog
          paths={moveDialog.paths}
          defaultDestination={current}
          destinations={moveFolders}
          loadingDestinations={moveFoldersLoading}
          onClose={closeMoveDialog}
          onSubmit={moveSelectedToFolder}
        />
      )}
      {isDraggingOver && (
        <div
          className="toolbar-offset fixed inset-0 left-[var(--left)] right-[var(--right)] bg-accent/10 border-2 border-dashed border-accent text-text flex items-center justify-center text-lg z-overlay pointer-events-none"
        >
          Drop images to upload
        </div>
      )}
      {ctx && (
        <AppContextMenuItems
          ctx={ctx}
          current={current}
          items={items}
          setCtx={setCtx}
          onRefetch={refetch}
          onOpenMoveDialog={openMoveDialogForPaths}
          onRefreshFolder={refreshFolderPath}
        />
      )}
    </div>
  )
}
