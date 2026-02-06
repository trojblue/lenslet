import React, { useCallback, useEffect, useMemo, useRef, useState } from 'react'
import Toolbar from '../shared/ui/Toolbar'
import VirtualGrid from '../features/browse/components/VirtualGrid'
import MetricScrollbar from '../features/browse/components/MetricScrollbar'
import Viewer from '../features/viewer/Viewer'
import CompareViewer from '../features/compare/CompareViewer'
import Inspector from '../features/inspector/Inspector'
import SimilarityModal from '../features/embeddings/SimilarityModal'
import { useFolder } from '../shared/api/folders'
import { useSearch } from '../shared/api/search'
import { useEmbeddings } from '../shared/api/embeddings'
import { api, connectEvents, disconnectEvents, subscribeEvents, subscribeEventStatus } from '../shared/api/client'
import type { ConnectionStatus, SyncEvent } from '../shared/api/client'
import { useOldestInflightAgeMs, useSyncStatus, updateConflictFromServer, sidecarQueryKey } from '../shared/api/items'
import { usePollingEnabled } from '../shared/api/polling'
import { readHash, writeHash, replaceHash, sanitizePath, getParentPath, isTrashPath, isLikelyImagePath } from './routing/hash'
import { applyFilters, applySort } from '../features/browse/model/apply'
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
import ContextMenu, { MenuItem } from './menu/ContextMenu'
import { mapItemsToRatings, toRatingsCsv, toRatingsJson } from '../features/ratings/services/exportRatings'
import { useDebounced } from '../shared/hooks/useDebounced'
import type { FilterAST, Item, SavedView, SortSpec, ContextMenuState, StarRating, ViewMode, ViewsPayload, ViewState, FolderIndex, SearchResult, PresenceEvent, Sidecar, EmbeddingSearchItem, EmbeddingSearchRequest } from '../lib/types'
import type { SyncIndicatorState } from '../shared/ui/SyncIndicator'
import { isInputElement } from '../lib/keyboard'
import { formatAbsoluteTime, formatRelativeTime, parseTimestampMs, safeJsonParse } from '../lib/util'
import { fileCache, thumbCache } from '../lib/blobCache'
import { FetchError } from '../lib/fetcher'
import LeftSidebar from './components/LeftSidebar'
import StatusBar from './components/StatusBar'
import { EDITING_HOLD_MS, LAST_EDIT_RELATIVE_MS, LONG_SYNC_THRESHOLD_MS, RECENT_EDIT_FLASH_MS } from '../lib/constants'

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

type RecentActivity = {
  path: string
  ts: number
  kind: 'item-updated' | 'metrics-updated'
}

type RecentTouchDisplay = {
  path: string
  label: string
  timeLabel: string
}

type SimilarityState = {
  embedding: string
  queryPath: string | null
  queryVector: string | null
  topK: number
  minScore: number | null
  items: EmbeddingSearchItem[]
  createdAt: number
}

function getConnectionLabel(status: ConnectionStatus): string {
  switch (status) {
    case 'live':
      return 'Live'
    case 'reconnecting':
      return 'Reconnecting…'
    case 'offline':
      return 'Offline'
    case 'connecting':
    case 'idle':
    default:
      return 'Connecting…'
  }
}

function getIndicatorState(options: {
  isOffline: boolean
  isUnstable: boolean
  recentEditActive: boolean
  editingActive: boolean
}): SyncIndicatorState {
  if (options.isOffline) return 'offline'
  if (options.isUnstable) return 'unstable'
  if (options.recentEditActive) return 'recent'
  if (options.editingActive) return 'editing'
  return 'live'
}

function formatTimestampLabel(timestampMs: number, nowMs: number): string {
  if (nowMs - timestampMs < LAST_EDIT_RELATIVE_MS) {
    return formatRelativeTime(timestampMs, nowMs)
  }
  return formatAbsoluteTime(timestampMs)
}

function buildRecentSummary(recentActivity: RecentActivity[], items: Item[]) {
  if (!recentActivity.length) return null
  const seen = new Set<string>()
  const paths: string[] = []
  for (const entry of recentActivity) {
    if (seen.has(entry.path)) continue
    seen.add(entry.path)
    paths.push(entry.path)
  }
  const names = paths.slice(0, 2).map((p) => {
    const match = items.find((it) => it.path === p)
    return match?.name ?? p.split('/').pop() ?? p
  })
  return {
    count: paths.length,
    names,
    extra: Math.max(0, paths.length - names.length),
  }
}

function buildRecentTouchesDisplay(recentTouches: RecentActivity[], items: Item[], nowMs: number): RecentTouchDisplay[] {
  if (!recentTouches.length) return []
  return recentTouches.map((entry) => {
    const match = items.find((it) => it.path === entry.path)
    const label = match?.name ?? entry.path.split('/').pop() ?? entry.path
    const timeLabel = formatTimestampLabel(entry.ts, nowMs)
    return { path: entry.path, label, timeLabel }
  })
}

function getEmbeddingsError(isError: boolean, error: unknown): string | null {
  if (!isError) return null
  if (error instanceof FetchError) return error.message
  if (error instanceof Error) return error.message
  return 'Failed to load embeddings.'
}

function getDisplayItemCount(
  similarityActive: boolean,
  showFilteredCounts: boolean,
  filteredCount: number,
  scopeTotal: number
): number {
  if (similarityActive) return filteredCount
  return showFilteredCounts ? filteredCount : scopeTotal
}

function getDisplayTotalCount(
  similarityActive: boolean,
  showFilteredCounts: boolean,
  totalCount: number,
  scopeTotal: number,
  rootTotal: number,
  current: string
): number {
  if (similarityActive) return totalCount
  if (showFilteredCounts) return scopeTotal
  return current === '/' ? scopeTotal : rootTotal
}

export default function AppShell() {
  // Navigation state
  const [current, setCurrent] = useState<string>('/')
  const [query, setQuery] = useState('')
  const [selectedPaths, setSelectedPaths] = useState<string[]>([])
  const [similarityOpen, setSimilarityOpen] = useState(false)
  const [similarityState, setSimilarityState] = useState<SimilarityState | null>(null)
  const [viewer, setViewer] = useState<string | null>(null)
  const [compareOpen, setCompareOpen] = useState(false)
  const [compareIndex, setCompareIndex] = useState(0)
  const [restoreGridToSelectionToken, setRestoreGridToSelectionToken] = useState(0)
  
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
  const [leftOpen, setLeftOpen] = useState(true)
  const [rightOpen, setRightOpen] = useState(true)
  const [leftTool, setLeftTool] = useState<'folders' | 'metrics'>('folders')
  const [views, setViews] = useState<SavedView[]>([])
  const [activeViewId, setActiveViewId] = useState<string | null>(null)
  const [scopeTotalCount, setScopeTotalCount] = useState<number | null>(null)
  const [rootTotalCount, setRootTotalCount] = useState<number | null>(null)
  const [folderCountsVersion, setFolderCountsVersion] = useState(0)
  
  // Local optimistic updates for star ratings
  const [localStarOverrides, setLocalStarOverrides] = useState<Record<string, StarRating>>({})
  
  // Refs
  const appRef = useRef<HTMLDivElement>(null)
  const gridShellRef = useRef<HTMLDivElement>(null)
  const gridScrollRef = useRef<HTMLDivElement>(null)
  const toolbarRef = useRef<HTMLDivElement>(null)
  const viewerHistoryPushedRef = useRef(false)
  const compareHistoryPushedRef = useRef(false)
  const lastFocusedPathRef = useRef<string | null>(null)
  const countCacheRef = useRef<Map<string, number>>(new Map())
  const countInflightRef = useRef<Map<string, Promise<number>>>(new Map())
  const similarityPrevSelectionRef = useRef<string[] | null>(null)

  const { leftW, rightW, onResizeLeft, onResizeRight } = useSidebars(appRef, leftTool)

  // Drag and drop state
  const [isDraggingOver, setDraggingOver] = useState(false)
  
  // Context menu state
  const [ctx, setCtx] = useState<ContextMenuState | null>(null)
  const queryClient = useQueryClient()
  const syncStatus = useSyncStatus()
  const pollingEnabled = usePollingEnabled()
  const oldestInflightAgeMs = useOldestInflightAgeMs()
  const [connectionStatus, setConnectionStatus] = useState<ConnectionStatus>('idle')
  const [presenceByGallery, setPresenceByGallery] = useState<Record<string, PresenceEvent>>({})
  const [recentActivity, setRecentActivity] = useState<RecentActivity[]>([])
  const [recentTouches, setRecentTouches] = useState<RecentActivity[]>([])
  const [recentBannerClosedAt, setRecentBannerClosedAt] = useState<number | null>(null)
  const [dismissRecentForSession, setDismissRecentForSession] = useState(false)
  const [highlightedPaths, setHighlightedPaths] = useState<Set<string>>(new Set())
  const highlightTimersRef = useRef<Map<string, number>>(new Map())
  const [lastEditedAt, setLastEditedAt] = useState<number | null>(null)
  const [recentEditAt, setRecentEditAt] = useState<number | null>(null)
  const [recentEditActive, setRecentEditActive] = useState(false)
  const [lastEditedNow, setLastEditedNow] = useState(() => Date.now())
  const [persistenceEnabled, setPersistenceEnabled] = useState(true)

  // Initialize current folder from URL hash and keep in sync
  useEffect(() => {
    const applyHash = (raw: string) => {
      const norm = sanitizePath(raw)
      const imageTarget = isLikelyImagePath(norm) ? norm : null
      const folderTarget = imageTarget ? getParentPath(norm) : norm
      if (imageTarget) {
        setViewer(imageTarget)
        setSelectedPaths([imageTarget])
      } else {
        setViewer(null)
        viewerHistoryPushedRef.current = false
      }
      // Only trigger "restore selection into view" when the folder/tab actually changes
      setCurrent((prev) => {
        if (prev === folderTarget) return prev
        setRestoreGridToSelectionToken((t) => t + 1)
        return folderTarget
      })
    }

    applyHash(readHash())
    const onHash = () => applyHash(readHash())
    window.addEventListener('hashchange', onHash)
    return () => window.removeEventListener('hashchange', onHash)
  }, [])

  useEffect(() => {
    return () => {
      for (const timeoutId of highlightTimersRef.current.values()) {
        window.clearTimeout(timeoutId)
      }
      highlightTimersRef.current.clear()
    }
  }, [])

  useEffect(() => {
    if (recentEditAt == null) {
      setRecentEditActive(false)
      return
    }
    setRecentEditActive(true)
    const id = window.setTimeout(() => setRecentEditActive(false), RECENT_EDIT_FLASH_MS)
    return () => window.clearTimeout(id)
  }, [recentEditAt])

  useEffect(() => {
    if (lastEditedAt == null) return
    setLastEditedNow(Date.now())
    const id = window.setInterval(() => setLastEditedNow(Date.now()), 10_000)
    return () => window.clearInterval(id)
  }, [lastEditedAt])

  const { data, refetch, isLoading, isError } = useFolder(current, true)
  const similarityActive = similarityState !== null
  const searching = !similarityActive && query.trim().length > 0
  const debouncedQ = useDebounced(query, 250)
  const normalizedQ = useMemo(() => debouncedQ.trim().replace(/\s+/g, ' '), [debouncedQ])
  const search = useSearch(searching ? normalizedQ : '', current)
  const embeddingsQuery = useEmbeddings()
  const embeddings = embeddingsQuery.data?.embeddings ?? []
  const embeddingsRejected = embeddingsQuery.data?.rejected ?? []
  const embeddingsAvailable = embeddings.length > 0
  const embeddingsError = getEmbeddingsError(embeddingsQuery.isError, embeddingsQuery.error)
  const starFilters = useMemo(() => getStarFilter(viewState.filters), [viewState.filters])

  // Pool items (current scope) + derived view (filters/sort)
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
    return applySort(filtered, viewState.sort, randomSeed)
  }, [similarityState, similarityItems, poolItems, viewState.filters, viewState.sort, randomSeed])

  const totalCount = similarityState ? similarityItems.length : poolItems.length
  const filteredCount = items.length

  const itemPaths = useMemo(() => items.map((i) => i.path), [items])
  const selectedSet = useMemo(() => new Set(selectedPaths), [selectedPaths])
  const selectedItems = useMemo(() => {
    if (!selectedPaths.length) return []
    const selectionPool = similarityState ? similarityItems : poolItems
    const poolByPath = new Map(selectionPool.map((it) => [it.path, it]))
    const itemsByPath = new Map(items.map((it) => [it.path, it]))
    return selectedPaths
      .map((path) => poolByPath.get(path) ?? itemsByPath.get(path))
      .filter((it): it is Item => !!it)
  }, [selectedPaths, similarityState, similarityItems, poolItems, items])
  const compareItems = useMemo(() => items.filter((it) => selectedSet.has(it.path)), [items, selectedSet])
  const compareMaxIndex = Math.max(0, compareItems.length - 2)
  const compareIndexClamped = Math.min(compareIndex, compareMaxIndex)
  const compareA = compareItems[compareIndexClamped] ?? null
  const compareB = compareItems[compareIndexClamped + 1] ?? null
  const canComparePrev = compareIndexClamped > 0
  const canCompareNext = compareIndexClamped < compareItems.length - 2
  const compareEnabled = compareItems.length >= 2
  const metricsBaseItems = similarityState ? similarityItems : poolItems
  const metricSortKey = similarityState ? null : (viewState.sort.kind === 'metric' ? viewState.sort.key : null)
  const hasMetricScrollbar = useMemo(() => {
    if (!metricSortKey) return false
    return items.some((it) => {
      const raw = it.metrics?.[metricSortKey]
      return raw != null && !Number.isNaN(raw)
    })
  }, [items, metricSortKey])

  useEffect(() => {
    setCompareIndex((prev) => (prev > compareMaxIndex ? compareMaxIndex : prev))
  }, [compareMaxIndex])

  const markHighlight = useCallback((path: string) => {
    setHighlightedPaths((prev) => {
      if (prev.has(path)) return prev
      const next = new Set(prev)
      next.add(path)
      return next
    })
    const timers = highlightTimersRef.current
    const existing = timers.get(path)
    if (existing) window.clearTimeout(existing)
    const timeoutId = window.setTimeout(() => {
      setHighlightedPaths((prev) => {
        if (!prev.has(path)) return prev
        const next = new Set(prev)
        next.delete(path)
        return next
      })
      timers.delete(path)
    }, RECENT_EDIT_FLASH_MS)
    timers.set(path, timeoutId)
  }, [])

  const updateLastEdited = useCallback((updatedAt?: string | null) => {
    const now = Date.now()
    const parsed = parseTimestampMs(updatedAt)
    const candidate = parsed ?? now
    const safeCandidate = candidate > now ? now : candidate
    setLastEditedAt((prev) => {
      if (prev == null) return safeCandidate
      return prev > safeCandidate ? prev : safeCandidate
    })
    setRecentEditAt(now)
    setLastEditedNow(now)
  }, [])

  const markRecentTouch = useCallback((path: string, kind: RecentActivity['kind'], updatedAt?: string | null) => {
    const now = Date.now()
    const ts = parseTimestampMs(updatedAt) ?? now
    setRecentTouches((prev) => {
      const filtered = prev.filter((entry) => entry.path !== path)
      const next = [{ path, ts, kind }, ...filtered]
      return next.slice(0, 10)
    })
  }, [])

  const markRecentActivity = useCallback((path: string, kind: RecentActivity['kind']) => {
    const now = Date.now()
    setRecentActivity((prev) => {
      const filtered = prev.filter((entry) => entry.path !== path)
      const next = [{ path, ts: now, kind }, ...filtered]
      return next.slice(0, 6)
    })
    markHighlight(path)
  }, [markHighlight])

  const updateItemCaches = useCallback((payload: { path: string; star?: StarRating | null; metrics?: Record<string, number | null>; comments?: string | null }) => {
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
        next = { ...next, metrics: payload.metrics ?? null }
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

  const countFolderImages = useCallback(async (path: string): Promise<number> => {
    const target = sanitizePath(path || '/')
    const cache = countCacheRef.current
    const inflight = countInflightRef.current
    const cached = cache.get(target)
    if (cached !== undefined) return cached

    const pending = inflight.get(target)
    if (pending) return pending

    const promise = (async () => {
      try {
        const folder = await api.getFolder(target, undefined, true)
        const count = folder.items.length
        cache.set(target, count)
        return count
      } finally {
        inflight.delete(target)
      }
    })()

    inflight.set(target, promise)
    return promise
  }, [])

  const invalidateDerivedCounts = useCallback(() => {
    countCacheRef.current.clear()
    countInflightRef.current.clear()
    setScopeTotalCount(null)
    setRootTotalCount(null)
    setFolderCountsVersion((prev) => prev + 1)
  }, [])

  useEffect(() => {
    let cancelled = false
    const target = sanitizePath(current || '/')

    const run = async () => {
      const rootPromise = countFolderImages('/')
      const scopePromise = target === '/' ? rootPromise : countFolderImages(target)
      const [root, scope] = await Promise.all([rootPromise, scopePromise])
      if (cancelled) return
      setRootTotalCount(root)
      setScopeTotalCount(scope)
    }

    run().catch((err) => console.warn('Failed to compute folder counts:', err))
    return () => {
      cancelled = true
    }
  }, [current, countFolderImages, folderCountsVersion])

  useEffect(() => {
    connectEvents()
    const offEvents = subscribeEvents((evt: SyncEvent) => {
      if (evt.type === 'presence') {
        const data = evt.data
        if (!data?.gallery_id) return
        setPresenceByGallery((prev) => ({ ...prev, [data.gallery_id]: data }))
        return
      }

      const data = evt.data as { path?: string }
      if (!data?.path) return
      const path = data.path

      if (evt.type === 'item-updated') {
        const payload = evt.data
        const sidecar: Sidecar = {
          v: 1,
          tags: payload.tags ?? [],
          notes: payload.notes ?? '',
          star: payload.star ?? null,
          version: payload.version ?? 1,
          updated_at: payload.updated_at ?? '',
          updated_by: payload.updated_by ?? 'server',
        }
        queryClient.setQueryData(sidecarQueryKey(path), sidecar)
        updateItemCaches({
          path,
          star: payload.star ?? null,
          metrics: payload.metrics,
          comments: payload.notes ?? '',
        })
        updateConflictFromServer(path, sidecar)
        markRecentActivity(path, 'item-updated')
        markRecentTouch(path, 'item-updated', payload.updated_at)
        updateLastEdited(payload.updated_at)
        setLocalStarOverrides((prev) => {
          if (prev[path] === undefined) return prev
          const next = { ...prev }
          delete next[path]
          return next
        })
      } else if (evt.type === 'metrics-updated') {
        const payload = evt.data
        updateItemCaches({ path, metrics: payload.metrics })
        markRecentActivity(path, 'metrics-updated')
        markRecentTouch(path, 'metrics-updated', payload.updated_at)
        updateLastEdited(payload.updated_at)
      }
    })
    const offStatus = subscribeEventStatus(setConnectionStatus)
    return () => {
      offEvents()
      offStatus()
      disconnectEvents()
    }
  }, [markRecentActivity, markRecentTouch, queryClient, updateItemCaches, updateLastEdited])

  useEffect(() => {
    let cancelled = false
    const galleryId = sanitizePath(current || '/')
    const send = async () => {
      try {
        const res = await api.postPresence(galleryId)
        if (!cancelled && res?.gallery_id) {
          setPresenceByGallery((prev) => ({ ...prev, [res.gallery_id]: res }))
        }
      } catch {
        // Ignore presence errors
      }
    }
    send()
    const id = window.setInterval(send, 30_000)
    return () => {
      cancelled = true
      window.clearInterval(id)
    }
  }, [current])

  useEffect(() => {
    let cancelled = false
    api.getHealth()
      .then((res) => {
        if (cancelled) return
        const enabled = res?.labels?.enabled ?? true
        setPersistenceEnabled(enabled)
      })
      .catch(() => {})
    return () => {
      cancelled = true
    }
  }, [])

  // Compute star counts for the filter UI
  const starCounts = useMemo(() => {
    const baseItems = similarityState ? similarityItems : poolItems
    const counts: Record<string, number> = { '0': 0, '1': 0, '2': 0, '3': 0, '4': 0, '5': 0 }
    for (const it of baseItems) {
      const star = localStarOverrides[it.path] ?? it.star ?? 0
      counts[String(star)] = (counts[String(star)] || 0) + 1
    }
    return counts
  }, [similarityState, similarityItems, poolItems, localStarOverrides])

  const metricKeys = useMemo(() => {
    const keys = new Set<string>()
    let scanned = 0
    const baseItems = similarityState ? similarityItems : poolItems
    for (const it of baseItems) {
      const metrics = it.metrics
      if (metrics) {
        for (const key of Object.keys(metrics)) {
          keys.add(key)
        }
      }
      scanned += 1
      if (scanned >= 250 && keys.size > 0) break
    }
    return Array.from(keys).sort()
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
  const scopeTotal = scopeTotalCount ?? totalCount
  const rootTotal = rootTotalCount ?? scopeTotal
  const showFilteredCounts = similarityActive || searching || activeFilterCount > 0

  const presence = presenceByGallery[current]
  const syncLabel = (() => {
    if (syncStatus.state === 'syncing') return 'Syncing…'
    if (syncStatus.state === 'error') {
      return syncStatus.message ? `Not saved — ${syncStatus.message}` : 'Not saved — retry'
    }
    return 'All changes saved'
  })()
  const connectionLabel = getConnectionLabel(connectionStatus)
  const hasEdits = lastEditedAt != null
  const lastEditedLabel = useMemo(() => {
    if (!hasEdits || lastEditedAt == null) return 'No edits yet.'
    return formatTimestampLabel(lastEditedAt, lastEditedNow)
  }, [hasEdits, lastEditedAt, lastEditedNow])
  const editHoldMs = lastEditedAt == null ? null : Math.max(0, lastEditedNow - lastEditedAt)
  const editingActive = (presence?.editing ?? 0) > 0 || (editHoldMs != null && editHoldMs < EDITING_HOLD_MS)
  const longSync = oldestInflightAgeMs != null && oldestInflightAgeMs > LONG_SYNC_THRESHOLD_MS
  const isOffline = connectionStatus === 'offline' || connectionStatus === 'connecting' || connectionStatus === 'idle'
  const isUnstable = connectionStatus === 'reconnecting' || pollingEnabled || syncStatus.state === 'error' || longSync
  const indicatorState = getIndicatorState({
    isOffline,
    isUnstable,
    recentEditActive,
    editingActive,
  })

  const recentSummary = useMemo(
    () => buildRecentSummary(recentActivity, items),
    [recentActivity, items],
  )
  const latestRecentActivityTs = useMemo(() => {
    if (!recentActivity.length) return null
    return recentActivity.reduce((acc, entry) => Math.max(acc, entry.ts), 0)
  }, [recentActivity])
  const hideRecentBanner = dismissRecentForSession
    || (recentBannerClosedAt != null && latestRecentActivityTs != null && latestRecentActivityTs <= recentBannerClosedAt)
  const visibleRecentSummary = hideRecentBanner ? null : recentSummary
  const recentTouchesDisplay = useMemo(
    () => buildRecentTouchesDisplay(recentTouches, items, lastEditedNow),
    [items, lastEditedNow, recentTouches],
  )
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

  const similarityQueryLabel = useMemo(() => {
    if (!similarityState) return null
    if (similarityState.queryPath) {
      const parts = similarityState.queryPath.split('/').filter(Boolean)
      return parts.length ? parts[parts.length - 1] : similarityState.queryPath
    }
    if (similarityState.queryVector) return 'Vector query'
    return null
  }, [similarityState])

  const similarityCountLabel = useMemo(() => {
    if (!similarityState) return null
    if (activeFilterCount > 0) return `${filteredCount} of ${totalCount}`
    return `${totalCount}`
  }, [similarityState, activeFilterCount, filteredCount, totalCount])

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
      setRestoreGridToSelectionToken((token) => token + 1)
    } else {
      setSelectedPaths([])
    }
  }, [])

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
      setRestoreGridToSelectionToken((token) => token + 1)
    } else {
      setSelectedPaths([])
    }
  }, [similarityState, selectedPaths])

  const handleMetricRange = useCallback((key: string, range: { min: number; max: number } | null) => {
    updateFilters((filters) => setMetricRangeFilter(filters, key, range))
  }, [updateFilters])

  const filterChips = useMemo(() => {
    const chips: { id: string; label: string; onRemove: () => void }[] = []
    for (const clause of viewState.filters.and) {
      if ('stars' in clause) {
        const stars = clause.stars || []
        if (!stars.length) continue
        chips.push({
          id: 'stars',
          label: `Rating in: ${formatStarValues(stars)}`,
          onRemove: () => handleClearStars(),
        })
      } else if ('starsIn' in clause) {
        const stars = clause.starsIn.values || []
        if (!stars.length) continue
        chips.push({
          id: 'stars-in',
          label: `Rating in: ${formatStarValues(stars)}`,
          onRemove: () => handleClearStars(),
        })
      } else if ('starsNotIn' in clause) {
        const stars = clause.starsNotIn.values || []
        if (!stars.length) continue
        chips.push({
          id: 'stars-not-in',
          label: `Rating not in: ${formatStarValues(stars)}`,
          onRemove: () => updateFilters((filters) => setStarsNotInFilter(filters, [])),
        })
      } else if ('nameContains' in clause) {
        const value = clause.nameContains.value?.trim()
        if (!value) continue
        chips.push({
          id: 'name-contains',
          label: `Filename contains: ${value}`,
          onRemove: () => updateFilters((filters) => setNameContainsFilter(filters, '')),
        })
      } else if ('nameNotContains' in clause) {
        const value = clause.nameNotContains.value?.trim()
        if (!value) continue
        chips.push({
          id: 'name-not-contains',
          label: `Filename not: ${value}`,
          onRemove: () => updateFilters((filters) => setNameNotContainsFilter(filters, '')),
        })
      } else if ('commentsContains' in clause) {
        const value = clause.commentsContains.value?.trim()
        if (!value) continue
        chips.push({
          id: 'comments-contains',
          label: `Comments contain: ${value}`,
          onRemove: () => updateFilters((filters) => setCommentsContainsFilter(filters, '')),
        })
      } else if ('commentsNotContains' in clause) {
        const value = clause.commentsNotContains.value?.trim()
        if (!value) continue
        chips.push({
          id: 'comments-not-contains',
          label: `Comments not: ${value}`,
          onRemove: () => updateFilters((filters) => setCommentsNotContainsFilter(filters, '')),
        })
      } else if ('urlContains' in clause) {
        const value = clause.urlContains.value?.trim()
        if (!value) continue
        chips.push({
          id: 'url-contains',
          label: `URL contains: ${value}`,
          onRemove: () => updateFilters((filters) => setUrlContainsFilter(filters, '')),
        })
      } else if ('urlNotContains' in clause) {
        const value = clause.urlNotContains.value?.trim()
        if (!value) continue
        chips.push({
          id: 'url-not-contains',
          label: `URL not: ${value}`,
          onRemove: () => updateFilters((filters) => setUrlNotContainsFilter(filters, '')),
        })
      } else if ('dateRange' in clause) {
        const { from, to } = clause.dateRange
        if (!from && !to) continue
        chips.push({
          id: 'date-range',
          label: `Date: ${formatDateRange(from, to)}`,
          onRemove: () => updateFilters((filters) => setDateRangeFilter(filters, null)),
        })
      } else if ('widthCompare' in clause) {
        const { op, value } = clause.widthCompare
        chips.push({
          id: 'width-compare',
          label: `Width ${op} ${value}`,
          onRemove: () => updateFilters((filters) => setWidthCompareFilter(filters, null)),
        })
      } else if ('heightCompare' in clause) {
        const { op, value } = clause.heightCompare
        chips.push({
          id: 'height-compare',
          label: `Height ${op} ${value}`,
          onRemove: () => updateFilters((filters) => setHeightCompareFilter(filters, null)),
        })
      } else if ('metricRange' in clause) {
        const { key, min, max } = clause.metricRange
        chips.push({
          id: `metric:${key}`,
          label: `${key}: ${formatRange(min, max)}`,
          onRemove: () => handleMetricRange(key, null),
        })
      }
    }
    return chips
  }, [viewState.filters, handleClearStars, handleMetricRange, updateFilters])

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
      if (viewer) {
        setViewer(null)
        viewerHistoryPushedRef.current = false
        replaceHash(current)
      }
    }
  }, [searching, viewer, current])

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
    if ('ResizeObserver' in window) {
      const ro = new ResizeObserver(update)
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
    if (typeof window === 'undefined') return
    const media = window.matchMedia('(max-width: 900px)')
    const apply = () => {
      if (media.matches) {
        setLeftOpen(false)
        setRightOpen(false)
      }
    }
    apply()
    if ('addEventListener' in media) {
      media.addEventListener('change', apply)
      return () => media.removeEventListener('change', apply)
    }
    media.addListener(apply)
    return () => media.removeListener(apply)
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
      pinchStart = { dist, size: gridItemSize }
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
  }, [viewer, compareOpen, gridItemSize])

  // Prefetch neighbors for the open viewer (previous and next)
  useEffect(() => {
    if (!viewer) return

    const idx = itemPaths.indexOf(viewer)
    if (idx === -1) return

    // Prefetch 2 items in each direction
    const neighbors = [
      itemPaths[idx - 2],
      itemPaths[idx - 1],
      itemPaths[idx + 1],
      itemPaths[idx + 2],
    ].filter((p): p is string => Boolean(p))

    for (const p of neighbors) {
      api.prefetchFile(p)
      api.prefetchThumb(p)
    }
  }, [viewer, itemPaths])

  useEffect(() => {
    if (!compareOpen || compareItems.length < 2) return
    const idx = compareIndexClamped
    const neighborIdx = new Set<number>()
    for (const offset of [-2, -1, 0, 1, 2, 3]) {
      const next = idx + offset
      if (next >= 0 && next < compareItems.length) neighborIdx.add(next)
    }
    for (const i of neighborIdx) {
      const path = compareItems[i]?.path
      if (!path) continue
      api.prefetchFile(path)
      api.prefetchThumb(path)
    }
  }, [compareOpen, compareItems, compareIndexClamped])

  // On folder load, prefetch fullsize for the first few items
  useEffect(() => {
    if (!data?.items?.length) return
    
    const toPreload = data.items.slice(0, 5)
    for (const it of toPreload) {
      api.prefetchFile(it.path)
    }
  }, [data?.path, data?.items])

  // Navigation callbacks
  const openFolder = useCallback((p: string) => {
    setViewer(null)
    viewerHistoryPushedRef.current = false
    const safe = sanitizePath(p)
    setCurrent(safe)
    writeHash(safe)
  }, [])

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

  const focusGridCell = useCallback((path: string | null | undefined) => {
    if (!path) return
    const el = document.getElementById(`cell-${encodeURIComponent(path)}`)
    el?.focus()
  }, [])

  const openViewer = useCallback((p: string) => {
    setViewer(p)
    viewerHistoryPushedRef.current = true
    writeHash(p)
  }, [])

  const closeViewer = useCallback(() => {
    setViewer(null)
    if (viewerHistoryPushedRef.current) {
      viewerHistoryPushedRef.current = false
      window.history.back()
    } else {
      replaceHash(current)
    }
    // Restore focus to the last focused grid cell
    focusGridCell(lastFocusedPathRef.current)
  }, [focusGridCell])

  const openCompare = useCallback(() => {
    if (compareOpen || !compareEnabled) return
    if (selectedPaths[0]) lastFocusedPathRef.current = selectedPaths[0]
    setCompareIndex(0)
    setCompareOpen(true)

    if (viewer) {
      setViewer(null)
      if (viewerHistoryPushedRef.current) {
        viewerHistoryPushedRef.current = false
      }
      replaceHash(current)
    }

    if (!compareHistoryPushedRef.current) {
      window.history.pushState({ compare: true }, '', window.location.href)
      compareHistoryPushedRef.current = true
    }
  }, [compareOpen, compareEnabled, selectedPaths, viewer, current])

  const closeCompare = useCallback(() => {
    setCompareOpen(false)
    if (compareHistoryPushedRef.current) {
      compareHistoryPushedRef.current = false
      window.history.back()
    }
    focusGridCell(lastFocusedPathRef.current ?? selectedPaths[0])
  }, [focusGridCell, selectedPaths])

  const handleCompareNavigate = useCallback((delta: number) => {
    if (compareItems.length < 2) return
    setCompareIndex((prev) => {
      const max = Math.max(0, compareItems.length - 2)
      return Math.min(max, Math.max(0, prev + delta))
    })
  }, [compareItems.length])

  useEffect(() => {
    if (!compareOpen) return
    if (compareEnabled) return
    closeCompare()
  }, [compareOpen, compareEnabled, closeCompare])

  // Handle browser back/forward specifically for closing the viewer.
  // NOTE: We intentionally do NOT touch grid scroll position here – closing
  // the fullscreen viewer should leave the grid exactly where it was.
  useEffect(() => {
    const onPop = () => {
      if (viewer) {
        viewerHistoryPushedRef.current = false
        setViewer(null)
      }
      if (compareOpen) {
        compareHistoryPushedRef.current = false
        setCompareOpen(false)
      }
    }
    window.addEventListener('popstate', onPop)
    return () => window.removeEventListener('popstate', onPop)
  }, [viewer, compareOpen])

  // Drag and drop file upload handling
  useEffect(() => {
    const el = appRef.current
    if (!el) return

    const onDragOver = (e: DragEvent) => {
      if (!e.dataTransfer) return
      if (Array.from(e.dataTransfer.types).includes('Files')) {
        e.preventDefault()
        setDraggingOver(true)
      }
    }

    const onDragLeave = (e: DragEvent) => {
      // Only trigger if leaving the app container entirely
      const related = e.relatedTarget as Node | null
      if (related && el.contains(related)) return
      setDraggingOver(false)
    }

    const onDrop = async (e: DragEvent) => {
      e.preventDefault()
      setDraggingOver(false)
      
      const files = Array.from(e.dataTransfer?.files ?? [])
      if (!files.length) return
      
      // Only allow uploads to leaf folders (no subdirectories)
      const isLeaf = (data?.dirs?.length ?? 0) === 0
      if (!isLeaf) {
        alert('Uploads are only allowed into folders without subdirectories.')
        return
      }
      
      // Upload files sequentially
      for (const f of files) {
        try {
          await api.uploadFile(current, f)
        } catch (err) {
          console.error(`Failed to upload ${f.name}:`, err)
        }
      }
      
      // Refresh folder contents
      refetch()
    }

    el.addEventListener('dragover', onDragOver)
    el.addEventListener('dragleave', onDragLeave)
    el.addEventListener('drop', onDrop)
    
    return () => {
      el.removeEventListener('dragover', onDragOver)
      el.removeEventListener('dragleave', onDragLeave)
      el.removeEventListener('drop', onDrop)
    }
  }, [current, data?.dirs?.length, refetch])

  // Close context menu on click or escape
  useEffect(() => {
    const onGlobalClick = () => setCtx(null)
    const onEsc = (e: KeyboardEvent) => {
      if (e.key === 'Escape') setCtx(null)
    }
    
    window.addEventListener('click', onGlobalClick)
    window.addEventListener('keydown', onEsc)
    
    return () => {
      window.removeEventListener('click', onGlobalClick)
      window.removeEventListener('keydown', onEsc)
    }
  }, [])

  // Global keyboard shortcuts
  useEffect(() => {
    const onKey = (e: KeyboardEvent) => {
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
      if (viewer || compareOpen) return
      
      if (e.key === 'Backspace' || e.key === 'Delete') {
        e.preventDefault()
        openFolder(getParentPath(current))
      } else if ((e.ctrlKey || e.metaKey) && e.key.toLowerCase() === 'a') {
        e.preventDefault()
        setSelectedPaths(items.map((i) => i.path))
      } else if (e.key === 'Escape') {
        if (selectedPaths.length) {
          e.preventDefault()
          setSelectedPaths([])
        }
      } else if (e.key === '/') {
        e.preventDefault()
        const searchInput = document.querySelector('.toolbar-right .input') as HTMLInputElement | null
        searchInput?.focus()
      }
    }
    
    window.addEventListener('keydown', onKey)
    return () => window.removeEventListener('keydown', onKey)
  }, [current, items, selectedPaths, viewer, compareOpen, openFolder])

  const leftCol = leftOpen ? `${leftW}px` : '0px'
  const rightCol = rightOpen ? `${rightW}px` : '0px'

  const navCurrent = viewer ?? selectedPaths[0] ?? null
  const navIdx = navCurrent ? itemPaths.indexOf(navCurrent) : -1
  const canPrevImage = navIdx > 0
  const canNextImage = navIdx >= 0 && navIdx < itemPaths.length - 1

  const handleNavigate = useCallback((delta: number) => {
    if (!itemPaths.length) return
    const currentPath = viewer ?? selectedPaths[0]
    if (!currentPath) return
    const idx = itemPaths.indexOf(currentPath)
    if (idx === -1) return
    const next = Math.min(itemPaths.length - 1, Math.max(0, idx + delta))
    const nextPath = itemPaths[next]
    if (!nextPath || nextPath === currentPath) return
    if (viewer) {
      setViewer(nextPath)
      replaceHash(nextPath)
    }
    setSelectedPaths([nextPath])
  }, [itemPaths, viewer, selectedPaths])

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
        sortDisabled={similarityActive}
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
        syncIndicator={{
          state: indicatorState,
          presence,
          syncLabel,
          connectionLabel,
          lastEditedLabel,
          hasEdits,
          recentTouches: recentTouchesDisplay,
        }}
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
          onContextMenu={(e, p) => { e.preventDefault(); setCtx({ x: e.clientX, y: e.clientY, kind: 'tree', payload: { path: p } }) }}
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
          recentSummary={visibleRecentSummary}
          onDismissRecent={() => setDismissRecentForSession(true)}
          onCloseRecent={() => setRecentBannerClosedAt(latestRecentActivityTs ?? Date.now())}
          browserZoomPercent={browserZoomPercent}
        />
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
        {/* Breadcrumb / path bar intentionally hidden for now */}
        {false && (
          <div className="sticky top-0 z-10 px-3 py-2.5 bg-panel backdrop-blur-sm shadow-[0_1px_0_rgba(255,255,255,.04),0_6px_8px_-6px_rgba(0,0,0,.5)]">
            {(() => {
              const parts = current.split('/').filter(Boolean)
              const segs: { label:string; path:string }[] = []
              let acc = ''
              for (const p of parts) { acc = acc ? `${acc}/${p}` : `/${p}`; segs.push({ label: p, path: acc }) }
              return (
                <>
                  <a href={`#${encodeURI('/')}`} onClick={(e)=>{ e.preventDefault(); openFolder('/') }} className="text-text opacity-85 no-underline hover:opacity-100 hover:underline">Root</a>
                  {segs.map((s, i) => (
                    <span key={s.path}>
                      <span className="opacity-50 mx-1.5">/</span>
                      {i < segs.length-1 ? (
                        <a href={`#${encodeURI(s.path)}`} onClick={(e)=>{ e.preventDefault(); openFolder(s.path) }} className="text-text opacity-85 no-underline hover:opacity-100 hover:underline">{s.label}</a>
                      ) : (
                        <span aria-current="page">{s.label}</span>
                      )}
                    </span>
                  ))}
                  <span className="opacity-0 hover:opacity-100 ml-2 cursor-pointer text-xs text-muted" role="button" aria-label="Copy path" title="Copy path" onClick={()=>{ try { navigator.clipboard.writeText(current) } catch {} }}>⧉</span>
                </>
              )
            })()}
          </div>
        )}
        <div className="flex-1 min-h-0 relative">
          <VirtualGrid
            items={items}
            selected={selectedPaths}
            restoreToSelectionToken={restoreGridToSelectionToken}
            onSelectionChange={setSelectedPaths}
            onOpenViewer={(p)=> { try { lastFocusedPathRef.current = p } catch {} ; openViewer(p); setSelectedPaths([p]) }}
            highlight={searching ? normalizedQ : ''}
            recentlyUpdated={highlightedPaths}
            suppressSelectionHighlight={!!viewer || compareOpen}
            viewMode={viewMode}
            targetCellSize={gridItemSize}
            onContextMenuItem={(e, path)=>{ e.preventDefault(); const paths = selectedPaths.length ? selectedPaths : [path]; setCtx({ x:e.clientX, y:e.clientY, kind:'grid', payload:{ paths } }) }}
            scrollRef={gridScrollRef}
            hideScrollbar={hasMetricScrollbar}
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
          sortSpec={viewState.sort}
          onResize={onResizeRight}
          onStarChanged={(paths, val)=>{
            setLocalStarOverrides(prev => { const next = { ...prev }; for (const p of paths) next[p] = val; return next })
          }}
          onFindSimilar={() => setSimilarityOpen(true)}
          embeddingsAvailable={embeddingsAvailable}
          embeddingsLoading={embeddingsQuery.isLoading}
        />
      )}
      <SimilarityModal
        open={similarityOpen}
        embeddings={embeddings}
        rejected={embeddingsRejected}
        selectedPath={selectedPaths[0] ?? null}
        embeddingsLoading={embeddingsQuery.isLoading}
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
      {isDraggingOver && (
        <div
          className="toolbar-offset fixed inset-0 left-[var(--left)] right-[var(--right)] bg-accent/10 border-2 border-dashed border-accent text-text flex items-center justify-center text-lg z-overlay pointer-events-none"
        >
          Drop images to upload
        </div>
      )}
      {ctx && <ContextMenuItems ctx={ctx} current={current} items={items} refetch={refetch} setCtx={setCtx} onInvalidateCounts={invalidateDerivedCounts} />}
    </div>
  )
}

function makeUniqueViewId(name: string, views: SavedView[]): string {
  const base = slugify(name) || 'view'
  const existing = new Set(views.map((v) => v.id))
  if (!existing.has(base)) return base
  let idx = 2
  while (existing.has(`${base}-${idx}`)) idx += 1
  return `${base}-${idx}`
}

function slugify(input: string): string {
  return input
    .toLowerCase()
    .trim()
    .replace(/[^a-z0-9]+/g, '-')
    .replace(/^-+|-+$/g, '')
}

function formatStarValues(values: number[]): string {
  const stars = values.filter((v) => v > 0).sort((a, b) => b - a)
  const hasNone = values.includes(0)
  const parts = [...stars.map((v) => String(v))]
  if (hasNone) parts.push('None')
  return parts.join(', ')
}

function formatDateRange(from?: string, to?: string): string {
  if (from && to) return `${from} to ${to}`
  if (from) return `from ${from}`
  if (to) return `to ${to}`
  return ''
}

function formatScopeLabel(path: string): string {
  if (path === '/' || path === '') return 'Root'
  const segments = path.split('/').filter(Boolean)
  if (!segments.length) return 'Root'
  if (segments.length <= 2) return `/${segments.join('/')}`
  const tail = segments.slice(-2).join('/')
  return `.../${tail}`
}

function formatRange(min: number, max: number): string {
  return `${formatNumber(min)}–${formatNumber(max)}`
}

function formatNumber(value: number): string {
  const abs = Math.abs(value)
  if (abs >= 1000) return value.toFixed(0)
  if (abs >= 10) return value.toFixed(2)
  return value.toFixed(3)
}

function guessMimeFromPath(path: string): Item['type'] {
  const lower = path.toLowerCase()
  if (lower.endsWith('.png')) return 'image/png'
  if (lower.endsWith('.webp')) return 'image/webp'
  return 'image/jpeg'
}

function buildFallbackItem(path: string, starOverride?: StarRating): Item {
  const name = path.split('/').pop() ?? path
  return {
    path,
    name,
    type: guessMimeFromPath(path),
    w: 0,
    h: 0,
    size: 0,
    hasThumb: true,
    hasMeta: false,
    star: starOverride ?? null,
  }
}

/**
 * Helper function to trigger a file download from a blob.
 */
function downloadBlob(blob: Blob, filename: string): void {
  const url = URL.createObjectURL(blob)
  const a = document.createElement('a')
  a.href = url
  a.download = filename
  document.body.appendChild(a)
  a.click()
  a.remove()
  URL.revokeObjectURL(url)
}

/**
 * Context menu items component - extracted for cleaner render logic.
 */
function ContextMenuItems({
  ctx,
  current,
  items,
  refetch,
  setCtx,
  onInvalidateCounts,
}: {
  ctx: ContextMenuState
  current: string
  items: Item[]
  refetch: () => void
  setCtx: (ctx: ContextMenuState | null) => void
  onInvalidateCounts: () => void
}) {
  const inTrash = isTrashPath(current)
  const queryClient = useQueryClient()
  const [refreshing, setRefreshing] = React.useState(false)
  const [exporting, setExporting] = React.useState<'csv' | 'json' | null>(null)

  const timestamp = () => new Date().toISOString().replace(/[:.]/g, '-')

  const invalidateFolderSubtree = (target: string) => {
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
  }

  const normalizePath = (p: string | undefined): string => {
    const safe = sanitizePath(p || '/')
    return safe === '' ? '/' : safe
  }

  const handleRefresh = async () => {
    const target = normalizePath(ctx.payload.path || '/')
    setRefreshing(true)
    try {
      await api.refreshFolder(target)
      invalidateFolderSubtree(target)
      onInvalidateCounts()

      if (current === target || current.startsWith(target === '/' ? '/' : `${target}/`)) {
        await refetch()
      }

      thumbCache.evictPrefix(target)
      fileCache.evictPrefix(target)
    } catch (err) {
      console.error('Failed to refresh folder:', err)
    } finally {
      setRefreshing(false)
      setCtx(null)
    }
  }

  const exportFolder = (format: 'csv' | 'json') => async () => {
    setExporting(format)
    const folderPath = ctx.payload.path || current
    try {
      const folder = await api.getFolder(folderPath, undefined, true)
      const folderItems = folder.items
      const ratings = mapItemsToRatings(folderItems)
      const content = format === 'csv' ? toRatingsCsv(ratings) : toRatingsJson(ratings)
      const mime = format === 'csv' ? 'text/csv;charset=utf-8' : 'application/json;charset=utf-8'
      const slug = folderPath === '/' ? 'root' : (folderPath.replace(/^\/+/, '') || 'root').replace(/\//g, '_')
      downloadBlob(new Blob([content], { type: mime }), `metadata_${slug}_${timestamp()}.${format}`)
    } catch (err) {
      console.error('Failed to export folder:', err)
      alert('Failed to export folder. See console for details.')
    } finally {
      setExporting(null)
      setCtx(null)
    }
  }
  
  const menuItems: MenuItem[] = ctx.kind === 'tree'
    ? [
        {
          label: refreshing ? 'Refreshing…' : 'Refresh',
          disabled: refreshing,
          onClick: handleRefresh,
        },
        {
          label: exporting === 'csv' ? 'Exporting CSV…' : 'Export metadata (CSV)',
          disabled: !!exporting || refreshing,
          onClick: exportFolder('csv'),
        },
        {
          label: exporting === 'json' ? 'Exporting JSON…' : 'Export metadata (JSON)',
          disabled: !!exporting || refreshing,
          onClick: exportFolder('json'),
        },
      ]
    : (() => {
        const sel = ctx.payload.paths ?? []
        const arr: MenuItem[] = []
        const exportSelection = (format: 'csv' | 'json') => async () => {
          setExporting(format)
          try {
            const selSet = new Set(sel)
            const subset = items.filter((i) => selSet.has(i.path))
            const ratings = mapItemsToRatings(subset)
            const content = format === 'csv' ? toRatingsCsv(ratings) : toRatingsJson(ratings)
            const mime = format === 'csv' ? 'text/csv;charset=utf-8' : 'application/json;charset=utf-8'
            downloadBlob(
              new Blob([content], { type: mime }),
              `metadata_selection_${timestamp()}.${format}`
            )
          } finally {
            setExporting(null)
            setCtx(null)
          }
        }
        
        // Move to trash
        arr.push({
          label: 'Move to trash',
          disabled: inTrash,
          onClick: async () => {
            if (inTrash) return
            for (const p of sel) {
              try {
                await api.moveFile(p, '/_trash_')
              } catch (err) {
                console.error(`Failed to trash ${p}:`, err)
              }
            }
            refetch()
            setCtx(null)
          },
        })
        
        // Trash-specific actions
        if (inTrash) {
          arr.push({
            label: 'Permanent delete',
            danger: true,
            onClick: async () => {
              if (!confirm(`Delete ${sel.length} file(s) permanently? This cannot be undone.`)) {
                return
              }
              try {
                await api.deleteFiles(sel)
              } catch (err) {
                console.error('Failed to delete files:', err)
              }
              refetch()
              setCtx(null)
            },
          })
          
          arr.push({
            label: 'Recover',
            onClick: async () => {
              for (const p of sel) {
                try {
                  const sc = await api.getSidecar(p)
                  const originalPath = sc.original_position
                  const targetDir = originalPath
                    ? originalPath.split('/').slice(0, -1).join('/') || '/'
                    : '/'
                  await api.moveFile(p, targetDir)
                } catch (err) {
                  console.error(`Failed to recover ${p}:`, err)
                }
              }
              refetch()
              setCtx(null)
            },
          })
        }
        
        // Export ratings
        if (sel.length) {
          arr.push({
            label: exporting === 'csv' ? 'Exporting CSV…' : 'Export metadata (CSV)',
            disabled: !!exporting,
            onClick: exportSelection('csv'),
          })
          
          arr.push({
            label: exporting === 'json' ? 'Exporting JSON…' : 'Export metadata (JSON)',
            disabled: !!exporting,
            onClick: exportSelection('json'),
          })
        }
        
        return arr
      })()
  
  return <ContextMenu x={ctx.x} y={ctx.y} items={menuItems} />
}
