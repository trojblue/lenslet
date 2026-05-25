import {
  Component,
  Suspense,
  lazy,
  useCallback,
  useEffect,
  useMemo,
  useRef,
  useState,
  type ReactNode,
} from 'react'
import Toolbar from '../shared/ui/Toolbar'
import VirtualGrid from '../features/browse/components/VirtualGrid'
import MetricScrollbar from '../features/browse/components/MetricScrollbar'
import SimilarityModal from '../features/embeddings/SimilarityModal'
import { api } from '../api/client'
import type { FullFilePrefetchContext } from '../api/client'
import { useOldestInflightAgeMs, useSyncStatus } from '../api/items'
import { usePollingEnabled } from '../api/polling'
import { readHash, resolveHashTargets, writeHash, sanitizePath, getParentPath } from './routing/hash'
import {
  countActiveFilters,
  getStarFilter,
  normalizeFilterAst,
  setNotesContainsFilter,
  setNotesNotContainsFilter,
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
import {
  resolveLeftToolToggle,
  resolveSidebarHotkeyToggle,
  toggleLeftPanelContent,
} from './layout/sidebarLayout'
import {
  buildResponsiveLayoutModel,
  type OverlayMode,
} from './layout/responsiveLayoutPolicy'
import { useQueryClient } from '@tanstack/react-query'
import type {
  CompareOrderMode,
  FilterAST,
  HealthMode,
  BrowseItemPayload,
  SavedView,
  SortSpec,
  StarRating,
  ViewMode,
  ViewsPayload,
  ViewState,
  EmbeddingSearchRequest,
} from '../lib/types'
import { isInputElement } from '../lib/keyboard'
import { safeJsonParse } from '../lib/util'
import { fileCache, thumbCache } from '../lib/blobCache'
import { FetchError } from '../lib/fetcher'
import LeftSidebar from './components/LeftSidebar'
import GridTopStack from './components/GridTopStack'
import { deriveIndicatorState } from './presenceUi'
import { LONG_SYNC_THRESHOLD_MS } from '../lib/constants'
import { getCompareFilePrefetchPaths, getViewerFilePrefetchPaths } from '../features/browse/model/prefetchPolicy'
import { LAYOUT_BREAKPOINTS } from '../lib/breakpoints'
import MoveToDialog from './components/MoveToDialog'
import AppContextMenuItems from './menu/AppContextMenuItems'
import { resolveFindSimilarAvailability } from '../features/inspector/model/findSimilarAvailability'
import { useLatestRef } from '../shared/hooks/useLatestRef'
import {
  buildStarCounts,
  getDisplayItemCount,
  getDisplayTotalCount,
  getSimilarityCountLabel,
  getSimilarityQueryLabel,
  hasMetricSortValues,
} from './model/appShellSelectors'
import { shouldShowGridLoading } from './model/loadingState'
import {
  downloadBlob,
  formatScopeLabel,
  getBrowserZoomWarningBucket,
  makeUniqueViewId,
  resolveScopeFromHashTarget,
  resolveVisibleBrowserZoomPercent,
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
import {
  createDeferredWriteScheduler,
  ItemQueryPathIndex,
  patchIndexedItemQueries,
  syncItemQueryIndexFromEvent,
  type ItemCacheUpdatePayload,
  type PersistedAppShellSettings,
} from './model/appShellStateSync'
import { applyThemePreset, type ThemePresetId } from '../theme/runtime'
import { loadWorkspaceThemePreset, writeStoredThemePreset } from '../theme/storage'

const Viewer = lazy(() => import('../features/viewer/Viewer'))
const CompareViewer = lazy(() => import('../features/compare/CompareViewer'))
const Inspector = lazy(() => import('../features/inspector/Inspector'))

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
  autoloadImageMetadata: 'autoloadImageMetadata',
  compareOrderMode: 'compareOrderMode',
} as const

const INDEXING_MODE_STORAGE_KEYS = {
  scanGeneration: 'indexingScanGeneration',
  recentGeneration: 'indexingMostRecentGeneration',
} as const

function writePersistedSettings(settings: PersistedAppShellSettings): void {
  if (typeof window === 'undefined') return
  try {
    const storage = window.localStorage
    storage.setItem(
      STORAGE_KEYS.sortKey,
      settings.sortSpec.kind === 'builtin' ? settings.sortSpec.key : 'added',
    )
    storage.setItem(STORAGE_KEYS.sortDir, settings.sortSpec.dir)
    storage.setItem(STORAGE_KEYS.sortSpec, JSON.stringify(settings.sortSpec))
    storage.setItem(STORAGE_KEYS.starFilters, JSON.stringify(settings.starFilters))
    storage.setItem(STORAGE_KEYS.filterAst, JSON.stringify(settings.filterAst))
    if (settings.selectedMetric) {
      storage.setItem(STORAGE_KEYS.selectedMetric, settings.selectedMetric)
    } else {
      storage.removeItem(STORAGE_KEYS.selectedMetric)
    }
    storage.setItem(STORAGE_KEYS.viewMode, settings.viewMode)
    storage.setItem(STORAGE_KEYS.gridItemSize, String(settings.gridItemSize))
    storage.setItem(STORAGE_KEYS.leftOpen, settings.leftOpen ? '1' : '0')
    storage.setItem(STORAGE_KEYS.rightOpen, settings.rightOpen ? '1' : '0')
    storage.setItem(
      STORAGE_KEYS.autoloadImageMetadata,
      settings.autoloadImageMetadata ? '1' : '0',
    )
    storage.setItem(STORAGE_KEYS.compareOrderMode, settings.compareOrderMode)
  } catch {
    // Ignore localStorage errors.
  }
}

type AppShellProps = {
  themeHealthMode: HealthMode | null
  themeWorkspaceId: string | null
}

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

type LazySurfaceBoundaryProps = {
  resetKey: string
  fallback: ReactNode
  children: ReactNode
}

type LazySurfaceBoundaryState = {
  hasError: boolean
}

class LazySurfaceBoundary extends Component<LazySurfaceBoundaryProps, LazySurfaceBoundaryState> {
  state: LazySurfaceBoundaryState = { hasError: false }

  static getDerivedStateFromError(): LazySurfaceBoundaryState {
    return { hasError: true }
  }

  componentDidUpdate(prevProps: LazySurfaceBoundaryProps): void {
    if (prevProps.resetKey !== this.props.resetKey && this.state.hasError) {
      this.setState({ hasError: false })
    }
  }

  render(): ReactNode {
    if (this.state.hasError) return this.props.fallback
    return this.props.children
  }
}

type InspectorFallbackProps = {
  message: string
  onClose: () => void
  busy?: boolean
}

function InspectorFallback({ message, onClose, busy = false }: InspectorFallbackProps): JSX.Element {
  return (
    <div
      className="app-right-panel inspector-panel col-start-3 row-start-2 border-l border-border bg-panel overflow-auto scrollbar-thin relative"
      data-inspector-panel
      aria-busy={busy ? 'true' : undefined}
    >
      <div className="p-3 flex items-center justify-between gap-3 text-sm text-muted">
        <span>{message}</span>
        <button className="btn btn-sm" onClick={onClose}>
          Close
        </button>
      </div>
    </div>
  )
}

type OverlayFallbackProps = {
  label: string
  message: string
  onClose: () => void
  busy?: boolean
}

function OverlayFallback({ label, message, onClose, busy = false }: OverlayFallbackProps): JSX.Element {
  return (
    <div
      role="dialog"
      aria-modal="true"
      aria-label={label}
      aria-busy={busy ? 'true' : undefined}
      tabIndex={-1}
      className="toolbar-offset absolute inset-0 left-[var(--overlay-left)] right-[var(--overlay-right)] bg-panel z-viewer flex items-center justify-center"
      onKeyDown={(event) => {
        if (event.key === 'Escape') {
          event.preventDefault()
          onClose()
        }
      }}
    >
      <div className="flex flex-col items-center gap-3 text-sm text-muted">
        <span>{message}</span>
        <button className="btn btn-sm" onClick={onClose} autoFocus>
          Close
        </button>
      </div>
    </div>
  )
}

export default function AppShell({
  themeHealthMode,
  themeWorkspaceId,
}: AppShellProps) {
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
  const [dismissedBrowserZoomBucket, setDismissedBrowserZoomBucket] = useState<number | null>(null)
  
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
  const [mobileSearchOpen, setMobileSearchOpen] = useState(false)
  const [mobileDrawerOpen, setMobileDrawerOpen] = useState(true)
  const [leftOpen, setLeftOpen] = useState(true)
  const [rightOpen, setRightOpen] = useState(true)
  const [viewportWidth, setViewportWidth] = useState(() => (
    typeof window === 'undefined' ? 1440 : window.innerWidth
  ))
  const [viewportHeight, setViewportHeight] = useState(() => (
    typeof window === 'undefined' ? 900 : window.innerHeight
  ))
  const [leftTool, setLeftTool] = useState<'folders' | 'metrics'>('folders')
  const [views, setViews] = useState<SavedView[]>([])
  const [activeViewId, setActiveViewId] = useState<string | null>(null)
  const [folderCountsVersion, setFolderCountsVersion] = useState(0)
  const [headerRefreshBusy, setHeaderRefreshBusy] = useState(false)
  const [scanGeneration, setScanGeneration] = useState<string | null>(() => (
    readStoredGeneration(INDEXING_MODE_STORAGE_KEYS.scanGeneration)
  ))
  const [recentGeneration, setRecentGeneration] = useState<string | null>(() => (
    readStoredGeneration(INDEXING_MODE_STORAGE_KEYS.recentGeneration)
  ))
  const [themePreset, setThemePreset] = useState<ThemePresetId>(() => (
    loadWorkspaceThemePreset(themeWorkspaceId, themeHealthMode)
  ))
  const [autoloadImageMetadata, setAutoloadImageMetadata] = useState(true)
  const [compareOrderMode, setCompareOrderMode] = useState<CompareOrderMode>('gallery')
  const [scanStableMode, setScanStableMode] = useState(false)
  const [persistedSettingsReady, setPersistedSettingsReady] = useState(false)
  
  // Local optimistic updates for star ratings
  const [localStarOverrides, setLocalStarOverrides] = useState<Record<string, StarRating>>({})
  
  // Refs
  const appRef = useRef<HTMLDivElement>(null)
  const browseShellRef = useRef<HTMLDivElement>(null)
  const gridShellRef = useRef<HTMLDivElement>(null)
  const gridScrollRef = useRef<HTMLDivElement>(null)
  const toolbarRef = useRef<HTMLDivElement>(null)
  const uploadInputRef = useRef<HTMLInputElement>(null)
  const similarityPrevSelectionRef = useRef<string[] | null>(null)
  const initialHashSyncRef = useRef(false)
  const itemQueryIndexRef = useRef(new ItemQueryPathIndex())
  const persistedSettingsWriterRef = useRef(
    createDeferredWriteScheduler<PersistedAppShellSettings>(writePersistedSettings),
  )

  const { leftW, rightW, onResizeLeft, onResizeRight } = useSidebars(appRef, leftTool, {
    userLeftOpen: leftOpen,
    userRightOpen: rightOpen,
  })
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

  useEffect(() => {
    const itemQueryIndex = itemQueryIndexRef.current
    const queryCache = queryClient.getQueryCache()
    itemQueryIndex.seed(queryCache.getAll())
    return queryCache.subscribe((event) => {
      syncItemQueryIndexFromEvent(
        itemQueryIndex,
        event as {
          type?: string
          query?: {
            queryHash?: string
            queryKey: readonly unknown[]
            state?: { data?: unknown }
          }
        },
      )
    })
  }, [queryClient])

  useEffect(() => {
    const writer = persistedSettingsWriterRef.current
    const flush = () => {
      writer.flush()
    }
    window.addEventListener('pagehide', flush)
    window.addEventListener('beforeunload', flush)
    return () => {
      window.removeEventListener('pagehide', flush)
      window.removeEventListener('beforeunload', flush)
      writer.flush()
    }
  }, [])

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
    metricKeys,
    items,
    totalCount,
    filteredCount,
    scopeTotal,
    rootTotal,
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
  const itemPathSet = useMemo(() => new Set(itemPaths), [itemPaths])
  const focusGridCell = useCallback((path: string | null | undefined) => {
    if (!path) return
    const focus = () => {
      const el = document.getElementById(`cell-${encodeURIComponent(path)}`)
      el?.focus()
    }
    requestAnimationFrame(() => requestAnimationFrame(focus))
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
    compareOrderMode,
    focusGridCell,
  })

  useEffect(() => {
    const shell = browseShellRef.current
    if (!shell) return
    if (overlayActive) {
      shell.setAttribute('inert', '')
      shell.setAttribute('aria-hidden', 'true')
      return
    }
    shell.removeAttribute('inert')
    shell.removeAttribute('aria-hidden')
  }, [overlayActive])

  useEffect(() => {
    const toolbar = toolbarRef.current
    if (!toolbar) return
    if (compareOpen) {
      toolbar.setAttribute('inert', '')
      toolbar.setAttribute('aria-hidden', 'true')
      return
    }
    toolbar.removeAttribute('inert')
    toolbar.removeAttribute('aria-hidden')
  }, [compareOpen])

  const syncHashImageSelectionRef = useLatestRef(syncHashImageSelection)
  const itemPathSetRef = useLatestRef(itemPathSet)
  const bumpRestoreGridToSelectionTokenRef = useLatestRef(bumpRestoreGridToSelectionToken)
  const leftOpenRef = useLatestRef(leftOpen)
  const rightOpenRef = useLatestRef(rightOpen)
  const leftToolRef = useLatestRef(leftTool)
  // Initialize current folder from URL hash and keep in sync.
  useEffect(() => {
    const applyHash = (raw: string) => {
      const { folderTarget, imageTarget } = resolveHashTargets(raw, itemPathSetRef.current)
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
  }, [bumpRestoreGridToSelectionTokenRef, itemPathSetRef, syncHashImageSelectionRef])
  const metricsBaseItems = selectionPool
  const metricSortKey = similarityState ? null : (viewState.sort.kind === 'metric' ? viewState.sort.key : null)
  const hasMetricScrollbar = useMemo(
    () => hasMetricSortValues(items, metricSortKey),
    [items, metricSortKey],
  )
  const findSimilarAvailability = useMemo(
    () => resolveFindSimilarAvailability({
      enabled: true,
      embeddingsAvailable,
      embeddingsLoading,
      selectedCount: selectedPaths.length,
    }),
    [embeddingsAvailable, embeddingsLoading, selectedPaths.length],
  )

  const updateItemCaches = useCallback((payload: ItemCacheUpdatePayload) => {
    patchIndexedItemQueries(queryClient, itemQueryIndexRef.current, payload)
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
    refreshEnabled,
    refreshDisabledReason,
    indexing,
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

  useEffect(() => {
    setThemePreset(loadWorkspaceThemePreset(themeWorkspaceId, themeHealthMode))
  }, [themeHealthMode, themeWorkspaceId])

  const handleThemePresetChange = useCallback((nextThemePreset: ThemePresetId) => {
    const appliedTheme = applyThemePreset(nextThemePreset)
    writeStoredThemePreset(themeWorkspaceId, themeHealthMode, appliedTheme)
    setThemePreset(appliedTheme)
  }, [themeHealthMode, themeWorkspaceId])

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
    if (!refreshEnabled) return
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
    refreshEnabled,
  ])

  const handlePullRefreshFolders = useCallback(async () => {
    if (!refreshEnabled) return
    try {
      await refreshFolderPath(current)
    } catch (err) {
      console.error('Failed to refresh folder:', err)
    }
  }, [current, refreshEnabled, refreshFolderPath])

  const handleHeaderRefresh = useCallback(async () => {
    if (!refreshEnabled || headerRefreshBusy) return
    setHeaderRefreshBusy(true)
    try {
      await refreshFolderPath('/')
    } catch (err) {
      console.error('Failed to refresh root folder:', err)
    } finally {
      setHeaderRefreshBusy(false)
    }
  }, [headerRefreshBusy, refreshEnabled, refreshFolderPath])

  // Compute star counts for the filter UI
  const starCounts = useMemo(() => {
    const baseItems = similarityState ? similarityItems : poolItems
    return buildStarCounts(baseItems, localStarOverrides)
  }, [similarityState, similarityItems, poolItems, localStarOverrides])

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
  const showGridLoading = shouldShowGridLoading({
    similarityActive,
    searching,
    itemCount: items.length,
    isLoading,
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
    clearNotesContains: () => updateFilters((filters) => setNotesContainsFilter(filters, '')),
    clearNotesNotContains: () => updateFilters((filters) => setNotesNotContainsFilter(filters, '')),
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
  const closeRightPanel = useCallback(() => {
    setRightOpen(false)
  }, [])

  const handleLeftToolChange = useCallback((nextTool: 'folders' | 'metrics') => {
    const nextState = resolveLeftToolToggle({
      activeTool: leftToolRef.current,
      contentOpen: leftOpenRef.current,
      clickedTool: nextTool,
    })
    setLeftTool(nextState.nextTool)
    setLeftOpen(nextState.contentOpen)
  }, [leftOpenRef, leftToolRef])

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
      const storedAutoloadImageMetadata = localStorage.getItem(STORAGE_KEYS.autoloadImageMetadata)
      const storedCompareOrderMode = localStorage.getItem(STORAGE_KEYS.compareOrderMode)

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
      if (storedAutoloadImageMetadata === '0' || storedAutoloadImageMetadata === 'false') {
        setAutoloadImageMetadata(false)
      } else if (storedAutoloadImageMetadata === '1' || storedAutoloadImageMetadata === 'true') {
        setAutoloadImageMetadata(true)
      }
      if (storedCompareOrderMode === 'gallery' || storedCompareOrderMode === 'selection') {
        setCompareOrderMode(storedCompareOrderMode)
      }
    } catch {
      // Ignore localStorage errors (private browsing, etc.)
    }
    setPersistedSettingsReady(true)
  }, [])

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

  useEffect(() => {
    if (getBrowserZoomWarningBucket(browserZoomPercent) === null) {
      setDismissedBrowserZoomBucket(null)
    }
  }, [browserZoomPercent])

  const visibleBrowserZoomPercent = useMemo(() => (
    resolveVisibleBrowserZoomPercent(browserZoomPercent, dismissedBrowserZoomBucket)
  ), [browserZoomPercent, dismissedBrowserZoomBucket])

  const dismissBrowserZoomWarning = useCallback(() => {
    setDismissedBrowserZoomBucket(getBrowserZoomWarningBucket(browserZoomPercent))
  }, [browserZoomPercent])

  const persistedSettings = useMemo<PersistedAppShellSettings>(() => ({
    sortSpec: viewState.sort,
    starFilters: getStarFilter(viewState.filters),
    filterAst: viewState.filters,
    selectedMetric: viewState.selectedMetric,
    viewMode,
    gridItemSize,
    leftOpen,
    rightOpen,
    autoloadImageMetadata,
    compareOrderMode,
  }), [
    autoloadImageMetadata,
    compareOrderMode,
    gridItemSize,
    leftOpen,
    rightOpen,
    viewMode,
    viewState.filters,
    viewState.selectedMetric,
    viewState.sort,
  ])

  useEffect(() => {
    if (!persistedSettingsReady) return
    persistedSettingsWriterRef.current.schedule(persistedSettings)
  }, [persistedSettings, persistedSettingsReady])

  useEffect(() => {
    if (typeof window === 'undefined') return
    const update = () => {
      setViewportWidth(window.innerWidth)
      setViewportHeight(window.innerHeight)
    }
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
    currentDirCount: data?.folders?.length ?? 0,
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

      // Ignore if viewer or compare is open (they have their own handlers)
      if (state.viewer || state.compareOpen) return

      // Toggle sidebars
      if ((e.ctrlKey || e.metaKey) && e.key.toLowerCase() === 'b') {
        e.preventDefault()
        const next = resolveSidebarHotkeyToggle({
          leftContentOpen: leftOpenRef.current,
          rightOpen: rightOpenRef.current,
          altKey: e.altKey,
        })
        setLeftOpen(next.leftContentOpen)
        setRightOpen(next.rightOpen)
        return
      }

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
        if (viewportWidth <= LAYOUT_BREAKPOINTS.narrowMax) {
          setMobileSearchOpen(true)
          return
        }
        const searchInput = document.querySelector('.toolbar-right .input') as HTMLInputElement | null
        searchInput?.focus()
      }
    }
    
    window.addEventListener('keydown', onKey)
    return () => window.removeEventListener('keydown', onKey)
  }, [keyboardStateRef, leftOpenRef, rightOpenRef, setSelectedPaths, viewportWidth])

  const overlayMode = useMemo<OverlayMode>(() => {
    if (compareOpen) return 'compare'
    if (viewer) return 'viewer'
    return 'none'
  }, [compareOpen, viewer])

  const layoutModel = useMemo(() => buildResponsiveLayoutModel({
    viewportWidth,
    viewportHeight,
    userLeftOpen: leftOpen,
    userRightOpen: rightOpen,
    leftPreferredWidth: leftW,
    rightPreferredWidth: rightW,
    overlay: overlayMode,
    mobileSearchOpen,
    mobileDrawerOpen,
  }), [
    viewportWidth,
    viewportHeight,
    leftOpen,
    rightOpen,
    leftW,
    rightW,
    overlayMode,
    mobileSearchOpen,
    mobileDrawerOpen,
  ])

  const leftCol = `${layoutModel.gridInsets.left}px`
  const rightCol = `${layoutModel.gridInsets.right}px`
  const overlayLeft = `${layoutModel.overlayInsets.left}px`
  const overlayRight = `${layoutModel.overlayInsets.right}px`
  const toolbarHeight = `${layoutModel.shellReserves.toolbarHeightPx}px`
  const mobileDrawerHeight = layoutModel.shellReserves.mobileDrawerHeightPx > 0
    ? `calc(${layoutModel.shellReserves.mobileDrawerHeightPx}px + env(safe-area-inset-bottom, 0px))`
    : '0px'
  const metricRailActive = hasMetricScrollbar && metricSortKey !== null

  return (
    <div
      className="app-shell grid h-full grid-cols-[var(--grid-left)_1fr_var(--grid-right)]"
      ref={appRef}
      data-layout-mode={layoutModel.mode}
      data-short-height={layoutModel.shortHeight ? 'true' : 'false'}
      data-left-suppression-reason={layoutModel.leftSuppressionReason}
      data-right-suppression-reason={layoutModel.rightSuppressionReason}
      data-inspector-suppression-reason={layoutModel.inspector.suppressionReason}
      data-overlay-mode={overlayMode}
      data-mobile-search-open={mobileSearchOpen ? 'true' : 'false'}
      data-mobile-drawer-open={mobileDrawerOpen ? 'true' : 'false'}
      data-effective-left-width={layoutModel.leftWidth}
      data-effective-right-width={layoutModel.rightWidth}
      style={{
        ['--grid-left' as any]: leftCol,
        ['--grid-right' as any]: rightCol,
        ['--overlay-left' as any]: overlayLeft,
        ['--overlay-right' as any]: overlayRight,
        ['--toolbar-h' as any]: toolbarHeight,
        ['--mobile-drawer-h' as any]: mobileDrawerHeight,
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
        onToggleLeft={() => setLeftOpen((v) => toggleLeftPanelContent(v))}
        onToggleRight={()=> setRightOpen(v=>!v)}
        onRefreshRoot={handleHeaderRefresh}
        refreshEnabled={refreshEnabled}
        refreshDisabledReason={refreshDisabledReason}
        refreshBusy={headerRefreshBusy}
        onPrevImage={() => handleNavigate(-1)}
        onNextImage={() => handleNavigate(1)}
        canPrevImage={canPrevImage}
        canNextImage={canNextImage}
        searchDisabled={similarityActive}
        searchPlaceholder={similarityActive ? 'Exit similarity to search' : undefined}
        mobileSearchOpen={mobileSearchOpen}
        onMobileSearchOpenChange={setMobileSearchOpen}
        mobileDrawerOpen={mobileDrawerOpen}
        onMobileDrawerOpenChange={setMobileDrawerOpen}
        onUploadClick={openUploadPicker}
        uploadBusy={uploading}
        uploadDisabled={compareOpen}
        themePreset={themePreset}
        onThemePresetChange={handleThemePresetChange}
        autoloadImageMetadata={autoloadImageMetadata}
        onAutoloadImageMetadataChange={setAutoloadImageMetadata}
        compareOrderMode={compareOrderMode}
        onCompareOrderModeChange={setCompareOrderMode}
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
      <div
        ref={browseShellRef}
        className="browse-shell"
        data-browse-shell
        data-overlay-inert={overlayActive ? 'true' : 'false'}
      >
        <input
          ref={uploadInputRef}
          type="file"
          multiple
          accept="image/*"
          className="sr-only"
          onChange={handleUploadInputChange}
        />
        {layoutModel.leftRailVisible && (
          <LeftSidebar
            leftTool={leftTool}
            contentOpen={layoutModel.effectiveLeftOpen}
            onToolChange={handleLeftToolChange}
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
            onPullRefreshFolders={refreshEnabled ? handlePullRefreshFolders : undefined}
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
            themePreset={themePreset}
            onThemePresetChange={handleThemePresetChange}
            autoloadImageMetadata={autoloadImageMetadata}
            onAutoloadImageMetadataChange={setAutoloadImageMetadata}
            compareOrderMode={compareOrderMode}
            onCompareOrderModeChange={setCompareOrderMode}
          />
        )}
        <div className="grid-shell col-start-2 row-start-2 relative overflow-hidden flex flex-col" ref={gridShellRef}>
          <div aria-live="polite" className="sr-only">
            {selectedPaths.length ? `${selectedPaths.length} selected` : ''}
          </div>
          <GridTopStack
            statusBarProps={{
              persistenceEnabled,
              indexing,
              showSwitchToMostRecentBanner: indexingBrowseMode.showSwitchToMostRecentBanner,
              onSwitchToMostRecent: handleSwitchToMostRecent,
              offViewSummary,
              canRevealOffView: showFilteredCounts,
              onRevealOffView: handleRevealOffView,
              onClearOffView: clearOffViewActivity,
              browserZoomPercent: visibleBrowserZoomPercent,
              onDismissBrowserZoomWarning: dismissBrowserZoomWarning,
            }}
            actionError={actionError}
            similarity={similarityState ? {
              embedding: similarityState.embedding,
              topK: similarityState.topK,
              minScore: similarityState.minScore,
              queryLabel: similarityQueryLabel,
              countLabel: similarityCountLabel,
            } : null}
            onExitSimilarity={clearSimilarity}
            filterChips={filterChips}
            onClearFilters={handleClearFilters}
          />
          <div className="grid-body flex-1 min-h-0" data-grid-body>
            <div className="grid-body-main relative min-h-0 min-w-0" data-grid-body-main>
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
                isLoading={showGridLoading}
              />
            </div>
            <div
              className={`metric-rail-slot${metricRailActive ? '' : ' is-inactive'}`}
              data-metric-rail-slot
              data-metric-rail-active={metricRailActive ? 'true' : 'false'}
              aria-hidden={!metricRailActive}
            >
              {metricRailActive
                ? (
                  <MetricScrollbar
                    items={items}
                    metricKey={metricSortKey!}
                    scrollRef={gridScrollRef}
                    sortDir={viewState.sort.dir}
                  />
                )
                : <div className="metric-rail-placeholder" aria-hidden="true" />}
            </div>
          </div>
          {/* Bottom selection bar removed intentionally */}
        </div>
        {layoutModel.effectiveRightOpen && (
          <LazySurfaceBoundary
            resetKey={`inspector:${layoutModel.effectiveRightOpen}`}
            fallback={<InspectorFallback message="Inspector could not load." onClose={closeRightPanel} />}
          >
            <Suspense
              fallback={<InspectorFallback message="Loading inspector..." onClose={closeRightPanel} busy />}
            >
              <Inspector
                path={selectedPaths[0] ?? null}
                selectedPaths={selectedPaths}
                comparePaths={comparePaths}
                items={items}
                viewerCompareActive={compareOpen}
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
                autoloadImageMetadata={autoloadImageMetadata}
                onLocalTypingChange={setLocalTypingActive}
              />
            </Suspense>
          </LazySurfaceBoundary>
        )}
      </div>
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
        <LazySurfaceBoundary
          resetKey={`viewer:${viewer}`}
          fallback={<OverlayFallback label="Image viewer" message="Viewer could not load." onClose={closeViewer} />}
        >
          <Suspense
            fallback={<OverlayFallback label="Image viewer" message="Loading viewer..." onClose={closeViewer} busy />}
          >
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
          </Suspense>
        </LazySurfaceBoundary>
      )}
      {compareOpen && (
        <LazySurfaceBoundary
          resetKey={`compare:${compareOpen}`}
          fallback={<OverlayFallback label="Compare images" message="Compare could not load." onClose={closeCompare} />}
        >
          <Suspense
            fallback={<OverlayFallback label="Compare images" message="Loading compare..." onClose={closeCompare} busy />}
          >
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
          </Suspense>
        </LazySurfaceBoundary>
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
          className="toolbar-offset fixed inset-0 left-[var(--overlay-left)] right-[var(--overlay-right)] bg-accent/10 border-2 border-dashed border-accent text-text flex items-center justify-center text-lg z-overlay pointer-events-none"
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
          refreshEnabled={refreshEnabled}
          refreshDisabledReason={refreshDisabledReason}
          onRefetch={refetch}
          onOpenMoveDialog={openMoveDialogForPaths}
          onRefreshFolder={refreshFolderPath}
          canFindSimilar={findSimilarAvailability.canFindSimilar}
          findSimilarDisabledReason={findSimilarAvailability.disabledReason}
          onFindSimilar={(path) => {
            setSelectedPaths([path])
            setSimilarityOpen(true)
          }}
        />
      )}
    </div>
  )
}
