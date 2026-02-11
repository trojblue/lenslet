import { useCallback, useEffect, useMemo, useRef, useState } from 'react'
import type { Dispatch, SetStateAction } from 'react'
import type { Item } from '../../lib/types'
import { replaceHash, writeHash } from '../routing/hash'

type UseAppSelectionViewerCompareParams = {
  current: string
  itemPaths: string[]
  items: Item[]
  selectionPool: Item[]
  focusGridCell: (path: string | null | undefined) => void
}

type UseAppSelectionViewerCompareResult = {
  selectedPaths: string[]
  setSelectedPaths: Dispatch<SetStateAction<string[]>>
  viewer: string | null
  compareOpen: boolean
  restoreGridToSelectionToken: number
  bumpRestoreGridToSelectionToken: () => void
  selectedItems: Item[]
  compareItems: Item[]
  comparePaths: string[]
  compareIndexClamped: number
  compareA: Item | null
  compareB: Item | null
  canComparePrev: boolean
  canCompareNext: boolean
  compareEnabled: boolean
  canPrevImage: boolean
  canNextImage: boolean
  overlayActive: boolean
  rememberFocusedPath: (path: string) => void
  openViewer: (path: string) => void
  closeViewer: () => void
  openCompare: () => void
  closeCompare: () => void
  handleCompareNavigate: (delta: number) => void
  handleNavigate: (delta: number) => void
  resetViewerState: () => void
  clearViewerForSearch: (scopePath: string) => void
  syncHashImageSelection: (imageTarget: string | null) => void
}

export function useAppSelectionViewerCompare({
  current,
  itemPaths,
  items,
  selectionPool,
  focusGridCell,
}: UseAppSelectionViewerCompareParams): UseAppSelectionViewerCompareResult {
  const [selectedPaths, setSelectedPaths] = useState<string[]>([])
  const [viewer, setViewer] = useState<string | null>(null)
  const [compareOpen, setCompareOpen] = useState(false)
  const [compareIndex, setCompareIndex] = useState(0)
  const [restoreGridToSelectionToken, setRestoreGridToSelectionToken] = useState(0)
  const viewerHistoryPushedRef = useRef(false)
  const compareHistoryPushedRef = useRef(false)
  const lastFocusedPathRef = useRef<string | null>(null)

  const selectedSet = useMemo(() => new Set(selectedPaths), [selectedPaths])
  const selectedItems = useMemo(() => {
    if (!selectedPaths.length) return []
    const poolByPath = new Map(selectionPool.map((it) => [it.path, it]))
    const itemsByPath = new Map(items.map((it) => [it.path, it]))
    return selectedPaths
      .map((path) => poolByPath.get(path) ?? itemsByPath.get(path))
      .filter((it): it is Item => !!it)
  }, [selectedPaths, selectionPool, items])
  const compareItems = useMemo(() => items.filter((it) => selectedSet.has(it.path)), [items, selectedSet])
  const comparePaths = useMemo(() => compareItems.map((it) => it.path), [compareItems])
  const compareMaxIndex = Math.max(0, compareItems.length - 2)
  const compareIndexClamped = Math.min(compareIndex, compareMaxIndex)
  const compareA = compareItems[compareIndexClamped] ?? null
  const compareB = compareItems[compareIndexClamped + 1] ?? null
  const canComparePrev = compareIndexClamped > 0
  const canCompareNext = compareIndexClamped < compareItems.length - 2
  const compareEnabled = compareItems.length >= 2
  const overlayActive = viewer != null || compareOpen
  const navCurrent = viewer ?? selectedPaths[0] ?? null
  const navIdx = navCurrent ? itemPaths.indexOf(navCurrent) : -1
  const canPrevImage = navIdx > 0
  const canNextImage = navIdx >= 0 && navIdx < itemPaths.length - 1

  useEffect(() => {
    setCompareIndex((prev) => (prev > compareMaxIndex ? compareMaxIndex : prev))
  }, [compareMaxIndex])

  const bumpRestoreGridToSelectionToken = useCallback(() => {
    setRestoreGridToSelectionToken((token) => token + 1)
  }, [])

  const rememberFocusedPath = useCallback((path: string) => {
    lastFocusedPathRef.current = path
  }, [])

  const resetViewerState = useCallback(() => {
    setViewer(null)
    viewerHistoryPushedRef.current = false
  }, [])

  const syncHashImageSelection = useCallback((imageTarget: string | null) => {
    if (imageTarget) {
      setViewer(imageTarget)
      setSelectedPaths([imageTarget])
      return
    }
    resetViewerState()
  }, [resetViewerState])

  const clearViewerForSearch = useCallback((scopePath: string) => {
    if (!viewer) return
    setViewer(null)
    viewerHistoryPushedRef.current = false
    replaceHash(scopePath)
  }, [viewer])

  const openViewer = useCallback((path: string) => {
    setViewer(path)
    viewerHistoryPushedRef.current = true
    writeHash(path)
  }, [])

  const closeViewer = useCallback(() => {
    setViewer(null)
    if (viewerHistoryPushedRef.current) {
      viewerHistoryPushedRef.current = false
      window.history.back()
    } else {
      replaceHash(current)
    }
    focusGridCell(lastFocusedPathRef.current)
  }, [current, focusGridCell])

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
  }, [compareOpen, compareEnabled, current, selectedPaths, viewer])

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
  }, [itemPaths, selectedPaths, viewer])

  useEffect(() => {
    if (!compareOpen) return
    if (compareEnabled) return
    closeCompare()
  }, [compareOpen, compareEnabled, closeCompare])

  // Keep browser history semantics for compare/viewer overlays.
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

  return {
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
  }
}
