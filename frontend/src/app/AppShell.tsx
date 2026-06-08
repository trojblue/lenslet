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
import Viewer from '../features/viewer/Viewer'
import { api } from '../api/client'
import type { FullFilePrefetchContext } from '../api/client'
import { useOldestInflightAgeMs, useSyncStatus } from '../api/items'
import { usePollingEnabled } from '../api/polling'
import { writeHash } from './routing/hash'
import { sanitizePath } from '../lib/paths'
import {
  countActiveFilters,
  setCategoricalInFilter,
  getStarsInFilter,
  normalizeFilterAst,
  setNotesContainsFilter,
  setNotesNotContainsFilter,
  setDateRangeFilter,
  setHeightCompareFilter,
  setMetricRangeFilter,
  setNameContainsFilter,
  setNameNotContainsFilter,
  setStarsInFilter,
  setStarsNotInFilter,
  setUrlContainsFilter,
  setUrlNotContainsFilter,
  setWidthCompareFilter,
} from '../features/browse/model/filters'
import { useSidebars } from './layout/useSidebars'
import {
  resolveLeftToolToggle,
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
  SortSpec,
  StarRating,
  TableSourceColumnsPayload,
  ViewMode,
  ViewState,
} from '../lib/types'
import { cssVars } from '../lib/cssVars'
import { fileCache, thumbCache } from '../lib/blobCache'
import LeftSidebar from './components/LeftSidebar'
import GridTopStack from './components/GridTopStack'
import { deriveIndicatorState } from './presenceUi'
import { LONG_SYNC_THRESHOLD_MS } from '../lib/constants'
import { getCompareFilePrefetchPaths, getViewerFilePrefetchPaths } from '../features/browse/model/prefetchPolicy'
import { LAYOUT_BREAKPOINTS } from '../lib/breakpoints'
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
  resolveSelectedMetricKey,
  shouldResetUnavailableMetricSort,
} from './model/appShellSelectors'
import { shouldShowGridLoading } from './model/loadingState'
import {
  formatScopeLabel,
} from './utils/appShellHelpers'
import { useAppDataScope, type SimilarityState } from './hooks/useAppDataScope'
import { useAppSelectionViewerCompare } from './hooks/useAppSelectionViewerCompare'
import { useAppPresenceSync } from './hooks/useAppPresenceSync'
import { useAppActions } from './hooks/useAppActions'
import { useAppHashRouting } from './hooks/useAppHashRouting'
import { useAppKeyboardShortcuts } from './hooks/useAppKeyboardShortcuts'
import { useFolderSessionState } from './hooks/useFolderSessionState'
import { useFolderRefreshActions } from './hooks/useFolderRefreshActions'
import { useBrowserZoomWarning } from './hooks/useBrowserZoomWarning'
import { useGridPinchResize } from './hooks/useGridPinchResize'
import { useIndexingModePersistence } from './hooks/useIndexingModePersistence'
import { usePersistedAppShellSettings } from './hooks/usePersistedAppShellSettings'
import { useSimilaritySearchWorkflow } from './hooks/useSimilaritySearchWorkflow'
import { useSmartFolders } from './hooks/useSmartFolders'
import { useViewportSize } from './hooks/useViewportSize'
import { buildFilterChips } from './model/filterChips'
import {
  ItemQueryPathIndex,
  patchIndexedItemQueries,
  syncItemQueryIndexFromEvent,
  type ItemCacheUpdatePayload,
} from './model/appShellStateSync'
import { applyThemePreset, type ThemePresetId } from '../theme/runtime'
import { loadWorkspaceThemePreset, writeStoredThemePreset } from '../theme/storage'

const CompareViewer = lazy(() => import('../features/compare/CompareViewer'))
const Inspector = lazy(() => import('../features/inspector/Inspector'))

type AppShellProps = {
  themeHealthMode: HealthMode | null
  themeWorkspaceId: string | null
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
  const [current, setCurrent] = useState<string>('/')
  const [query, setQuery] = useState('')
  const [similarityOpen, setSimilarityOpen] = useState(false)
  const [similarityState, setSimilarityState] = useState<SimilarityState | null>(null)
  
  const [requestedZoom, setRequestedZoom] = useState<number | null>(null)
  const [currentZoom, setCurrentZoom] = useState(100)
  const requestViewerZoom = useCallback((percent: number) => {
    setCurrentZoom(Math.round(percent))
    setRequestedZoom(percent)
  }, [])

  const {
    visibleBrowserZoomPercent,
    dismissBrowserZoomWarning,
  } = useBrowserZoomWarning()
  
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
  const { viewportWidth, viewportHeight } = useViewportSize()
  const [leftTool, setLeftTool] = useState<'folders' | 'metrics'>('folders')
  const [themePreset, setThemePreset] = useState<ThemePresetId>(() => (
    loadWorkspaceThemePreset(themeWorkspaceId, themeHealthMode)
  ))
  const [autoloadImageMetadata, setAutoloadImageMetadata] = useState(true)
  const [compareOrderMode, setCompareOrderMode] = useState<CompareOrderMode>('gallery')
  const [scanStableMode, setScanStableMode] = useState(false)
  const [tableSourceColumns, setTableSourceColumns] = useState<TableSourceColumnsPayload | null>(null)
  const [tableSourceSwitching, setTableSourceSwitching] = useState(false)
  const [dismissedTableSourceWarning, setDismissedTableSourceWarning] = useState<string | null>(null)
  
  // Local optimistic updates for star ratings
  const [localStarOverrides, setLocalStarOverrides] = useState<Record<string, StarRating>>({})
  
  const appRef = useRef<HTMLDivElement>(null)
  const browseShellRef = useRef<HTMLDivElement>(null)
  const gridShellRef = useRef<HTMLDivElement>(null)
  const gridScrollRef = useRef<HTMLDivElement>(null)
  const toolbarRef = useRef<HTMLDivElement>(null)
  const itemQueryIndexRef = useRef(new ItemQueryPathIndex())

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

  usePersistedAppShellSettings({
    viewState,
    viewMode,
    gridItemSize,
    leftOpen,
    rightOpen,
    autoloadImageMetadata,
    compareOrderMode,
    setViewState,
    setRandomSeed,
    setViewMode,
    setGridItemSize,
    setLeftOpen,
    setRightOpen,
    setAutoloadImageMetadata,
    setCompareOrderMode,
  })

  const queryClient = useQueryClient()
  const syncStatus = useSyncStatus()
  const pollingEnabled = usePollingEnabled()
  const oldestInflightAgeMs = useOldestInflightAgeMs()
  const [localTypingActive, setLocalTypingActive] = useState(false)

  const refreshTableSourceColumns = useCallback(async () => {
    try {
      const next = await api.getTableSourceColumns()
      setTableSourceColumns(next.enabled ? next : null)
    } catch {
      setTableSourceColumns(null)
    }
  }, [])

  useEffect(() => {
    refreshTableSourceColumns()
  }, [refreshTableSourceColumns])

  const tableSourceWarningKey = tableSourceColumns?.warning
    ? `${tableSourceColumns.current ?? ''}:${tableSourceColumns.warning}`
    : null
  const tableSourceWarning = tableSourceWarningKey && dismissedTableSourceWarning !== tableSourceWarningKey
    ? `${tableSourceColumns?.warning ?? ''} Switch image columns from Settings > Source.`
    : null

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
    categoricalKeys,
    derivedMetric,
    items,
    totalCount,
    filteredCount,
    scopeTotal,
    rootTotal,
    hasMoreFolderItems,
    isLoadingMoreFolderItems,
    loadMoreFolderItems,
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
  const starsInFilter = useMemo(() => getStarsInFilter(viewState.filters), [viewState.filters])

  const itemPaths = useMemo(() => items.map((i) => i.path), [items])
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

  const handleTableSourceColumnChange = useCallback((sourceColumn: string) => {
    if (!sourceColumn || sourceColumn === tableSourceColumns?.current || tableSourceSwitching) return
    setTableSourceSwitching(true)
    api.switchTableSourceColumn(sourceColumn)
      .then((next) => {
        setTableSourceColumns(next.enabled ? next : null)
        setDismissedTableSourceWarning(null)
        fileCache.clear()
        thumbCache.clear()
        queryClient.invalidateQueries()
        setSelectedPaths([])
        setSimilarityState(null)
        resetViewerState()
        setCurrent('/')
        writeHash('/')
        setScopeSessionResetToken((token) => token + 1)
      })
      .catch(() => {})
      .finally(() => setTableSourceSwitching(false))
  }, [queryClient, resetViewerState, setSelectedPaths, tableSourceColumns?.current, tableSourceSwitching])

  useEffect(() => {
    const shell = browseShellRef.current
    if (!shell) return
    if (compareOpen) {
      shell.setAttribute('inert', '')
      shell.setAttribute('aria-hidden', 'true')
      return
    }
    shell.removeAttribute('inert')
    shell.removeAttribute('aria-hidden')
  }, [compareOpen])

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

  const leftOpenRef = useLatestRef(leftOpen)
  const leftToolRef = useLatestRef(leftTool)

  useAppHashRouting({
    setCurrent,
    syncHashImageSelection,
    bumpRestoreGridToSelectionToken,
  })
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

  const {
    indexingBrowseMode,
    handleSwitchToMostRecent,
  } = useIndexingModePersistence({
    indexing,
    setScanStableMode,
    setViewState,
  })

  useEffect(() => {
    setThemePreset(loadWorkspaceThemePreset(themeWorkspaceId, themeHealthMode))
  }, [themeHealthMode, themeWorkspaceId])

  const handleThemePresetChange = useCallback((nextThemePreset: ThemePresetId) => {
    const appliedTheme = applyThemePreset(nextThemePreset)
    writeStoredThemePreset(themeWorkspaceId, themeHealthMode, appliedTheme)
    setThemePreset(appliedTheme)
  }, [themeHealthMode, themeWorkspaceId])

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

  const {
    folderCountsVersion,
    headerRefreshBusy,
    refreshFolderPath,
    handlePullRefreshFolders,
    handleHeaderRefresh,
  } = useFolderRefreshActions({
    current,
    refreshEnabled,
    queryClient,
    refetch,
    invalidateFolderSessionSubtree,
    setScopeSessionResetToken,
  })

  const starCounts = useMemo(() => {
    const baseItems = similarityState ? similarityItems : poolItems
    return buildStarCounts(baseItems, localStarOverrides)
  }, [similarityState, similarityItems, poolItems, localStarOverrides])

  useEffect(() => {
    if (similarityActive) return
    if (!metricKeys.length) return
    setViewState((prev) => {
      const nextKey = resolveSelectedMetricKey(prev.selectedMetric, metricKeys, derivedMetric.key)
      if (nextKey === prev.selectedMetric) return prev
      return { ...prev, selectedMetric: nextKey }
    })
  }, [derivedMetric.key, metricKeys, similarityActive])

  useEffect(() => {
    if (!shouldResetUnavailableMetricSort(
      viewState.sort,
      metricKeys,
      similarityActive,
      derivedMetric.key,
      derivedMetric.status,
    )) return
    setViewState((prev) => ({
      ...prev,
      sort: { kind: 'builtin', key: 'added', dir: prev.sort.dir },
    }))
  }, [derivedMetric.key, derivedMetric.status, metricKeys, viewState.sort, similarityActive])

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

  const handleClearStarsIn = useCallback(() => {
    updateFilters((filters) => setStarsInFilter(filters, []))
  }, [updateFilters])

  const handleClearFilters = useCallback(() => {
    setViewState((prev) => ({
      ...prev,
      filters: { and: [] },
    }))
  }, [])

  const {
    clearSimilarity,
    handleRevealOffView,
    handleSimilaritySearch,
  } = useSimilaritySearchWorkflow({
    similarityState,
    setSimilarityState,
    selectedPaths,
    setSelectedPaths,
    setQuery,
    setViewState,
    bumpRestoreGridToSelectionToken,
  })

  const handleMetricRange = useCallback((key: string, range: { min: number; max: number } | null) => {
    updateFilters((filters) => setMetricRangeFilter(filters, key, range))
  }, [updateFilters])

  const handleCategoricalValues = useCallback((key: string, values: string[] | null) => {
    updateFilters((filters) => setCategoricalInFilter(filters, key, values))
  }, [updateFilters])

  const filterChips = useMemo(() => buildFilterChips(viewState.filters, {
    clearStarsIn: handleClearStarsIn,
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
    clearCategoricalIn: (key: string) => handleCategoricalValues(key, null),
  }), [viewState.filters, handleClearStarsIn, handleMetricRange, handleCategoricalValues, updateFilters])

  const handleToggleStarsIn = useCallback((v: number) => {
    const next = new Set(starsInFilter)
    if (next.has(v)) {
      next.delete(v)
    } else {
      next.add(v)
    }
    setViewState((prev) => ({
      ...prev,
      filters: setStarsInFilter(prev.filters, Array.from(next)),
    }))
  }, [starsInFilter])

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
    if (searching) {
      setSelectedPaths([])
      clearViewerForSearch(current)
    }
  }, [clearViewerForSearch, current, searching, setSelectedPaths])

  const mobileSelectEnabled = viewportWidth <= LAYOUT_BREAKPOINTS.mobileMax

  useEffect(() => {
    if (mobileSelectEnabled) return
    if (!mobileSelectMode) return
    setMobileSelectMode(false)
  }, [mobileSelectEnabled, mobileSelectMode])

  useGridPinchResize({
    shellRef: gridShellRef,
    disabled: Boolean(viewer) || compareOpen,
    gridItemSize,
    setGridItemSize,
  })

  useEffect(() => {
    prefetchFilesAndThumbs(getViewerFilePrefetchPaths(itemPaths, viewer), 'viewer')
  }, [viewer, itemPaths])

  useEffect(() => {
    if (!compareOpen) return
    prefetchFilesAndThumbs(getCompareFilePrefetchPaths(comparePaths, compareIndexClamped), 'compare')
  }, [compareOpen, comparePaths, compareIndexClamped])

  const openFolder = useCallback((p: string) => {
    resetViewerState()
    const safe = sanitizePath(p)
    setCurrent(safe)
    writeHash(safe)
  }, [resetViewerState])

  const focusDesktopSearch = useCallback(() => {
    const searchInput = document.querySelector('.toolbar-right .input') as HTMLInputElement | null
    searchInput?.focus()
  }, [])

  const {
    ctx,
    setCtx,
    openGridActions,
    openFolderActions,
  } = useAppActions({
    selectedPaths,
    setSelectedPaths,
  })

  const {
    views,
    activeViewId,
    activateView,
    clearActiveView,
    saveView: handleSaveView,
  } = useSmartFolders({
    current,
    viewState,
    setViewState,
    openFolder,
  })

  useAppKeyboardShortcuts({
    current,
    items,
    selectedPaths,
    viewerOpen: Boolean(viewer),
    compareOpen,
    mobileSelectMode,
    leftOpen,
    rightOpen,
    viewportWidth,
    openFolder,
    setSelectedPaths,
    setLeftOpen,
    setRightOpen,
    setMobileSelectMode,
    setMobileSearchOpen,
    focusDesktopSearch,
  })

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
      style={cssVars({
        '--grid-left': leftCol,
        '--grid-right': rightCol,
        '--overlay-left': overlayLeft,
        '--overlay-right': overlayRight,
        '--toolbar-h': toolbarHeight,
        '--mobile-drawer-h': mobileDrawerHeight,
      })}
    >
      <Toolbar
        rootRef={toolbarRef}
        onSearch={setQuery}
        viewerActive={!!viewer}
        onBack={closeViewer}
        zoomPercent={viewer ? currentZoom : undefined}
        onZoomPercentChange={requestViewerZoom}
        currentLabel={scopeLabel}
        itemCount={displayItemCount}
        totalCount={displayTotalCount}
        sortSpec={viewState.sort}
        metricKeys={metricKeys}
        onSortChange={handleSortChange}
        sortDisabled={similarityActive || indexingBrowseMode.sortLocked}
        filterCount={activeFilterCount}
        onOpenFilters={openMetricsPanel}
        starsInFilter={starsInFilter}
        onToggleStarsIn={handleToggleStarsIn}
        onClearStarsIn={handleClearStarsIn}
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
        themePreset={themePreset}
        onThemePresetChange={handleThemePresetChange}
        autoloadImageMetadata={autoloadImageMetadata}
        onAutoloadImageMetadataChange={setAutoloadImageMetadata}
        compareOrderMode={compareOrderMode}
        onCompareOrderModeChange={setCompareOrderMode}
        sourceColumns={tableSourceColumns}
        sourceColumnSwitching={tableSourceSwitching}
        onSourceColumnChange={handleTableSourceColumnChange}
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
        data-overlay-inert={compareOpen ? 'true' : 'false'}
      >
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
            onActivateView={activateView}
            onSaveView={handleSaveView}
            current={current}
            data={data}
            onOpenFolder={(p) => { clearActiveView(); openFolder(p) }}
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
            categoricalKeys={categoricalKeys}
            selectedItems={selectedItems}
            selectedMetric={viewState.selectedMetric}
            onSelectMetric={(key) => setViewState((prev) => ({ ...prev, selectedMetric: key }))}
            filters={viewState.filters}
            onChangeRange={handleMetricRange}
            onChangeCategoricalValues={handleCategoricalValues}
            onChangeFilters={handleFiltersChange}
            onResize={onResizeLeft}
            themePreset={themePreset}
            onThemePresetChange={handleThemePresetChange}
            autoloadImageMetadata={autoloadImageMetadata}
            onAutoloadImageMetadataChange={setAutoloadImageMetadata}
            compareOrderMode={compareOrderMode}
            onCompareOrderModeChange={setCompareOrderMode}
            tableSourceColumns={tableSourceColumns}
            tableSourceSwitching={tableSourceSwitching}
            onTableSourceColumnChange={handleTableSourceColumnChange}
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
              tableSourceWarning,
              onDismissTableSourceWarning: tableSourceWarningKey
                ? () => setDismissedTableSourceWarning(tableSourceWarningKey)
                : undefined,
            }}
            actionError={null}
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
                hasMore={hasMoreFolderItems}
                isLoadingMore={isLoadingMoreFolderItems}
                onLoadMore={loadMoreFolderItems}
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
      {ctx && (
        <AppContextMenuItems
          ctx={ctx}
          current={current}
          items={items}
          setCtx={setCtx}
          refreshEnabled={refreshEnabled}
          refreshDisabledReason={refreshDisabledReason}
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
