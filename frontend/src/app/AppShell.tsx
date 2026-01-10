import React, { useCallback, useEffect, useMemo, useRef, useState } from 'react'
import Toolbar from '../shared/ui/Toolbar'
import FolderTree from '../features/folders/FolderTree'
import VirtualGrid from '../features/browse/components/VirtualGrid'
import Viewer from '../features/viewer/Viewer'
import Inspector from '../features/inspector/Inspector'
import { useFolder } from '../shared/api/folders'
import { useSearch } from '../shared/api/search'
import { api } from '../shared/api/client'
import { readHash, writeHash, sanitizePath, getParentPath, isTrashPath } from './routing/hash'
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
import MetricsPanel from '../features/metrics/MetricsPanel'
import { useSidebars } from './layout/useSidebars'
import { useQueryClient } from '@tanstack/react-query'
import ContextMenu, { MenuItem } from './menu/ContextMenu'
import { mapItemsToRatings, toRatingsCsv, toRatingsJson } from '../features/ratings/services/exportRatings'
import { useDebounced } from '../shared/hooks/useDebounced'
import type { FilterAST, Item, SavedView, SortSpec, ContextMenuState, StarRating, ViewMode, ViewsPayload, ViewState } from '../lib/types'
import { isInputElement } from '../lib/keyboard'
import { safeJsonParse } from '../lib/util'
import { fileCache, thumbCache } from '../lib/blobCache'
import { FetchError } from '../lib/fetcher'

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

export default function AppShell() {
  // Navigation state
  const [current, setCurrent] = useState<string>('/')
  const [query, setQuery] = useState('')
  const [selectedPaths, setSelectedPaths] = useState<string[]>([])
  const [viewer, setViewer] = useState<string | null>(null)
  const [restoreGridToSelectionToken, setRestoreGridToSelectionToken] = useState(0)
  
  // Viewer zoom state
  const [requestedZoom, setRequestedZoom] = useState<number | null>(null)
  const [currentZoom, setCurrentZoom] = useState(100)
  
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
  
  // Local optimistic updates for star ratings
  const [localStarOverrides, setLocalStarOverrides] = useState<Record<string, StarRating>>({})
  
  // Refs
  const appRef = useRef<HTMLDivElement>(null)
  const gridShellRef = useRef<HTMLDivElement>(null)
  const viewerHistoryPushedRef = useRef(false)
  const lastFocusedPathRef = useRef<string | null>(null)

  const { leftW, rightW, onResizeLeft, onResizeRight } = useSidebars(appRef)

  // Drag and drop state
  const [isDraggingOver, setDraggingOver] = useState(false)
  
  // Context menu state
  const [ctx, setCtx] = useState<ContextMenuState | null>(null)

  // Initialize current folder from URL hash and keep in sync
  useEffect(() => {
    const initPath = sanitizePath(readHash())
    setCurrent(initPath)
    
    const onHash = () => {
      const norm = sanitizePath(readHash())
      setViewer(null)
      // Only trigger "restore selection into view" when the folder/tab actually changes
      setCurrent((prev) => {
        if (prev === norm) return prev
        setRestoreGridToSelectionToken((t) => t + 1)
        return norm
      })
    }
    
    window.addEventListener('hashchange', onHash)
    return () => window.removeEventListener('hashchange', onHash)
  }, [])

  const { data, refetch, isLoading, isError } = useFolder(current)
  const searching = query.trim().length > 0
  const debouncedQ = useDebounced(query, 250)
  const normalizedQ = useMemo(() => debouncedQ.trim().replace(/\s+/g, ' '), [debouncedQ])
  const search = useSearch(searching ? normalizedQ : '', current)
  const starFilters = useMemo(() => getStarFilter(viewState.filters), [viewState.filters])

  // Pool items (current scope) + derived view (filters/sort)
  const poolItems = useMemo((): Item[] => {
    const base = searching ? (search.data?.items ?? []) : (data?.items ?? [])
    return base.map((it) => ({
      ...it,
      star: localStarOverrides[it.path] !== undefined ? localStarOverrides[it.path] : it.star,
    }))
  }, [searching, search.data, data, localStarOverrides])

  const items = useMemo((): Item[] => {
    const filtered = applyFilters(poolItems, viewState.filters)
    return applySort(filtered, viewState.sort, randomSeed)
  }, [poolItems, viewState.filters, viewState.sort, randomSeed])

  const totalCount = poolItems.length
  const filteredCount = items.length

  const itemPaths = useMemo(() => items.map((i) => i.path), [items])

  // Compute star counts for the filter UI
  const starCounts = useMemo(() => {
    const baseItems = poolItems
    const counts: Record<string, number> = { '0': 0, '1': 0, '2': 0, '3': 0, '4': 0, '5': 0 }
    for (const it of baseItems) {
      const star = localStarOverrides[it.path] ?? it.star ?? 0
      counts[String(star)] = (counts[String(star)] || 0) + 1
    }
    return counts
  }, [poolItems, localStarOverrides])

  const metricKeys = useMemo(() => {
    const keys = new Set<string>()
    let scanned = 0
    for (const it of poolItems) {
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
  }, [poolItems])

  useEffect(() => {
    if (!metricKeys.length) return
    setViewState((prev) => {
      const nextKey = prev.selectedMetric && metricKeys.includes(prev.selectedMetric)
        ? prev.selectedMetric
        : metricKeys[0]
      if (nextKey === prev.selectedMetric) return prev
      return { ...prev, selectedMetric: nextKey }
    })
  }, [metricKeys])

  useEffect(() => {
    if (viewState.sort.kind !== 'metric') return
    if (metricKeys.includes(viewState.sort.key)) return
    setViewState((prev) => ({
      ...prev,
      sort: { kind: 'builtin', key: 'added', dir: prev.sort.dir },
    }))
  }, [metricKeys, viewState.sort])

  const activeFilterCount = useMemo(() => countActiveFilters(viewState.filters), [viewState.filters])

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
      setViewer(null)
    }
  }, [searching])

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
      e.preventDefault()
      setGridItemSize((prev) => clamp(prev + (e.deltaY < 0 ? 20 : -20)))
    }
    shell.addEventListener('wheel', onWheel, { passive: false })
    return () => shell.removeEventListener('wheel', onWheel)
  }, [])

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

  const openViewer = useCallback((p: string) => {
    setViewer(p)
    if (!viewerHistoryPushedRef.current) {
      window.history.pushState({ viewer: true }, '', window.location.href)
      viewerHistoryPushedRef.current = true
    }
  }, [])

  const closeViewer = useCallback(() => {
    setViewer(null)
    if (viewerHistoryPushedRef.current) {
      viewerHistoryPushedRef.current = false
      window.history.back()
    }
    // Restore focus to the last focused grid cell
    const p = lastFocusedPathRef.current
    if (p) {
      const el = document.getElementById(`cell-${encodeURIComponent(p)}`)
      el?.focus()
    }
  }, [])

  // Handle browser back/forward specifically for closing the viewer.
  // NOTE: We intentionally do NOT touch grid scroll position here – closing
  // the fullscreen viewer should leave the grid exactly where it was.
  useEffect(() => {
    const onPop = () => {
      if (viewer) {
        viewerHistoryPushedRef.current = false
        setViewer(null)
      }
    }
    window.addEventListener('popstate', onPop)
    return () => window.removeEventListener('popstate', onPop)
  }, [viewer])

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

      // Ignore if viewer is open (viewer has its own handlers) for other shortcuts
      if (viewer) return
      
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
  }, [current, items, selectedPaths, viewer, openFolder])

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
    if (viewer) setViewer(nextPath)
    setSelectedPaths([nextPath])
  }, [itemPaths, viewer, selectedPaths])

  return (
    <div className="grid h-full grid-cols-[var(--left)_1fr_var(--right)] grid-rows-[48px_1fr]" ref={appRef} style={{ ['--left' as any]: leftCol, ['--right' as any]: rightCol }}>
      <Toolbar
        onSearch={setQuery}
        viewerActive={!!viewer}
        onBack={closeViewer}
        zoomPercent={viewer ? currentZoom : undefined}
        onZoomPercentChange={(p)=> setRequestedZoom(p)}
        currentLabel={scopeLabel}
        itemCount={filteredCount}
        totalCount={totalCount}
        sortSpec={viewState.sort}
        metricKeys={metricKeys}
        onSortChange={handleSortChange}
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
      />
      {leftOpen && (
        <div className="col-start-1 row-start-2 relative border-r border-border bg-panel overflow-hidden">
          <div className="absolute inset-y-0 left-0 w-10 border-r border-border flex flex-col items-center gap-2 py-3 bg-surface-overlay">
            <button
              className={`w-7 h-7 rounded-md border border-border flex items-center justify-center transition-colors ${leftTool === 'folders' ? 'bg-accent-muted text-accent' : 'bg-surface text-text hover:bg-surface-hover'}`}
              title="Folders"
              aria-label="Folders"
              aria-pressed={leftTool === 'folders'}
              onClick={() => setLeftTool('folders')}
            >
              <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.8" strokeLinecap="round" strokeLinejoin="round" aria-hidden="true">
                <path d="M3 7.5h6l2-2h10a2 2 0 0 1 2 2v9a2 2 0 0 1-2 2H3a2 2 0 0 1-2-2v-7a2 2 0 0 1 2-2z" />
              </svg>
            </button>
            <button
              className={`w-7 h-7 rounded-md border border-border flex items-center justify-center transition-colors ${leftTool === 'metrics' ? 'bg-accent-muted text-accent' : 'bg-surface text-text hover:bg-surface-hover'}`}
              title="Metrics / Filters"
              aria-label="Metrics and Filters"
              aria-pressed={leftTool === 'metrics'}
              onClick={() => setLeftTool('metrics')}
            >
              <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.8" strokeLinecap="round" strokeLinejoin="round" aria-hidden="true">
                <path d="M4 19V9" />
                <path d="M10 19V5" />
                <path d="M16 19v-7" />
                <path d="M3 19h18" />
              </svg>
            </button>
          </div>
          <div className="ml-10 h-full">
            {leftTool === 'folders' ? (
              <div className="h-full flex flex-col">
                <div className="px-2 py-2 border-b border-border">
                  <div className="flex items-center justify-between mb-2">
                    <div className="text-[11px] uppercase tracking-wide text-muted">Smart Folders</div>
                    <button
                      className="btn btn-sm btn-ghost text-xs"
                      onClick={handleSaveView}
                      title="Save current view as Smart Folder"
                    >
                      + New
                    </button>
                  </div>
                  {views.length ? (
                    <div className="flex flex-col gap-1">
                      {views.map((view) => {
                        const active = view.id === activeViewId
                        return (
                          <button
                            key={view.id}
                            className={`text-left px-2 py-1.5 rounded-md text-sm ${active ? 'bg-accent-muted text-accent' : 'hover:bg-hover text-text'}`}
                            onClick={() => {
                              setActiveViewId(view.id)
                              const safeFilters = normalizeFilterAst(view.view?.filters) ?? { and: [] }
                              setViewState({ ...view.view, filters: safeFilters })
                              openFolder(view.pool.path)
                              setLeftTool('metrics')
                            }}
                          >
                            {view.name}
                          </button>
                        )
                      })}
                    </div>
                  ) : (
                    <div className="text-xs text-muted px-1 py-1.5">No saved Smart Folders yet.</div>
                  )}
                </div>
                <FolderTree
                  current={current}
                  roots={[{ label: 'Root', path: '/' }]}
                  data={data}
                  onOpen={(p) => { setActiveViewId(null); openFolder(p) }}
                  onContextMenu={(e, p)=>{ e.preventDefault(); setCtx({ x:e.clientX, y:e.clientY, kind:'tree', payload:{ path:p } }) }}
                  className="flex-1 min-h-0 overflow-auto scrollbar-thin"
                  showResizeHandle={false}
                />
              </div>
            ) : (
              <MetricsPanel
                items={poolItems}
                filteredItems={items}
                metricKeys={metricKeys}
                selectedMetric={viewState.selectedMetric}
                onSelectMetric={(key) => setViewState((prev) => ({ ...prev, selectedMetric: key }))}
                filters={viewState.filters}
                onChangeRange={handleMetricRange}
                onChangeFilters={handleFiltersChange}
              />
            )}
          </div>
          <div className="absolute top-12 bottom-0 right-0 w-1.5 cursor-col-resize z-10 hover:bg-accent/20" onMouseDown={onResizeLeft} />
        </div>
      )}
      <div className="col-start-2 row-start-2 relative overflow-hidden flex flex-col" ref={gridShellRef}>
        <div aria-live="polite" className="sr-only">
          {selectedPaths.length ? `${selectedPaths.length} selected` : ''}
        </div>
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
        <div className="flex-1 min-h-0">
          <VirtualGrid items={items} selected={selectedPaths} restoreToSelectionToken={restoreGridToSelectionToken} onSelectionChange={setSelectedPaths} onOpenViewer={(p)=> { try { lastFocusedPathRef.current = p } catch {} ; openViewer(p); setSelectedPaths([p]) }}
            highlight={searching ? normalizedQ : ''}
            suppressSelectionHighlight={!!viewer}
            viewMode={viewMode}
            targetCellSize={gridItemSize}
            onContextMenuItem={(e, path)=>{ e.preventDefault(); const paths = selectedPaths.length ? selectedPaths : [path]; setCtx({ x:e.clientX, y:e.clientY, kind:'grid', payload:{ paths } }) }}
          />
        </div>
        {/* Bottom selection bar removed intentionally */}
      </div>
      {rightOpen && (
        <Inspector path={selectedPaths[0] ?? null} selectedPaths={selectedPaths} items={items} onResize={onResizeRight} onStarChanged={(paths, val)=>{
          setLocalStarOverrides(prev => { const next = { ...prev }; for (const p of paths) next[p] = val; return next })
        }} />
      )}
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
      {isDraggingOver && (
        <div className="fixed inset-0 top-[48px] left-[var(--left)] right-[var(--right)] bg-accent/10 border-2 border-dashed border-accent text-text flex items-center justify-center text-lg z-overlay pointer-events-none">Drop images to upload</div>
      )}
      {ctx && <ContextMenuItems ctx={ctx} current={current} items={items} refetch={refetch} setCtx={setCtx} />}
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
}: {
  ctx: ContextMenuState
  current: string
  items: Item[]
  refetch: () => void
  setCtx: (ctx: ContextMenuState | null) => void
}) {
  const inTrash = isTrashPath(current)
  const joinChild = (parent: string, name: string) => (parent === '/' ? `/${name}` : `${parent}/${name}`)
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

  // Recursively collect items for a folder (including subfolders)
  const collectFolderItems = async (root: string): Promise<Item[]> => {
    const stack = [root]
    const seen = new Set<string>()
    const all: Item[] = []

    while (stack.length) {
      const p = stack.pop()!
      if (seen.has(p)) continue
      seen.add(p)
      try {
        const folder = await api.getFolder(p)
        all.push(...folder.items)
        for (const d of folder.dirs) {
          if (d.kind === 'branch') {
            stack.push(joinChild(p, d.name))
          }
        }
      } catch (err) {
        console.error(`Failed to fetch folder ${p}:`, err)
      }
    }

    return all
  }

  const exportFolder = (format: 'csv' | 'json') => async () => {
    setExporting(format)
    const folderPath = ctx.payload.path || current
    try {
      const folderItems = await collectFolderItems(folderPath)
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
            onClick: async () => {
              setExporting('csv')
              try {
                const selSet = new Set(sel)
                const subset = items.filter((i) => selSet.has(i.path))
                const ratings = mapItemsToRatings(subset)
                const csv = toRatingsCsv(ratings)
                downloadBlob(
                  new Blob([csv], { type: 'text/csv;charset=utf-8' }),
                  `metadata_selection_${timestamp()}.csv`
                )
              } finally {
                setExporting(null)
                setCtx(null)
              }
            },
          })
          
          arr.push({
            label: exporting === 'json' ? 'Exporting JSON…' : 'Export metadata (JSON)',
            disabled: !!exporting,
            onClick: async () => {
              setExporting('json')
              try {
                const selSet = new Set(sel)
                const subset = items.filter((i) => selSet.has(i.path))
                const ratings = mapItemsToRatings(subset)
                const json = toRatingsJson(ratings)
                downloadBlob(
                  new Blob([json], { type: 'application/json;charset=utf-8' }),
                  `metadata_selection_${timestamp()}.json`
                )
              } finally {
                setExporting(null)
                setCtx(null)
              }
            },
          })
        }
        
        return arr
      })()
  
  return <ContextMenu x={ctx.x} y={ctx.y} items={menuItems} />
}
