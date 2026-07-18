import { useCallback, useEffect, useLayoutEffect, useMemo, useRef, useState } from 'react'
import type { Dispatch, SetStateAction } from 'react'
import type { CompareOrderMode, BrowseItemPayload } from '../../lib/types'
import { replaceHash, replaceImageHash, writeImageHash } from '../routing/hash'
import { browseEntityStore } from '../model/browseEntityStore'
import { overlayLiveBrowseEntity } from './useGridPresentation'

type UseAppSelectionViewerCompareParams = {
  current: string
  itemPaths: string[]
  items: BrowseItemPayload[]
  selectionPool: BrowseItemPayload[]
  compareOrderMode: CompareOrderMode
  membershipSettled: boolean
  membershipComplete: boolean
  focusGridCell: (path: string | null | undefined) => void
}

type UseAppSelectionViewerCompareResult = {
  selectedPaths: string[]
  setSelectedPaths: Dispatch<SetStateAction<string[]>>
  viewer: string | null
  compareOpen: boolean
  restoreGridToSelectionToken: number
  bumpRestoreGridToSelectionToken: () => void
  selectedItems: BrowseItemPayload[]
  compareItems: BrowseItemPayload[]
  comparePaths: string[]
  compareIndexClamped: number
  compareA: BrowseItemPayload | null
  compareB: BrowseItemPayload | null
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
  resetForScopeBoundary: (explicitViewerPath?: string | null) => void
  syncHashImageSelection: (imageTarget: string | null) => void
}

type OverlayPopstateResult = {
  resetViewer: boolean
  resetCompare: boolean
}

export function shouldCloseCompareForSelectionChange(
  compareOpen: boolean,
  compareEnabled: boolean,
): boolean {
  return compareOpen && !compareEnabled
}

export function resolveOverlayPopstateResult(
  viewer: string | null,
  compareOpen: boolean,
): OverlayPopstateResult {
  return {
    resetViewer: viewer !== null,
    resetCompare: compareOpen,
  }
}

export function resolveSelectionOrderedItems(
  selectedPaths: readonly string[],
  selectionPool: readonly BrowseItemPayload[],
  items: readonly BrowseItemPayload[],
): BrowseItemPayload[] {
  if (!selectedPaths.length) return []
  const poolByPath = new Map(selectionPool.map((it) => [it.path, it]))
  const itemsByPath = new Map(items.map((it) => [it.path, it]))
  return selectedPaths
    .map((path) => poolByPath.get(path) ?? itemsByPath.get(path))
    .filter((it): it is BrowseItemPayload => !!it)
}

export function resolveGalleryOrderedItems(
  selectedPaths: readonly string[],
  items: readonly BrowseItemPayload[],
): BrowseItemPayload[] {
  if (!selectedPaths.length) return []
  const selectedSet = new Set(selectedPaths)
  return items.filter((item) => selectedSet.has(item.path))
}

export function resolveCompareOrderedItems(
  selectedPaths: readonly string[],
  selectionPool: readonly BrowseItemPayload[],
  items: readonly BrowseItemPayload[],
  compareOrderMode: CompareOrderMode,
): BrowseItemPayload[] {
  if (compareOrderMode === 'selection') {
    return resolveSelectionOrderedItems(selectedPaths, selectionPool, items)
  }
  return resolveGalleryOrderedItems(selectedPaths, items)
}

export function canCommitCompareMembership(
  selectedPaths: readonly string[],
  targetItems: readonly BrowseItemPayload[],
  membershipSettled: boolean,
  membershipComplete: boolean,
): boolean {
  if (!membershipSettled) return false
  if (membershipComplete) return true
  const targetPaths = new Set(targetItems.map((item) => item.path))
  return selectedPaths.every((path) => targetPaths.has(path))
}

export function reconcileSettledSearchSelection(
  selectedPaths: string[],
  membershipPaths: readonly string[],
  membershipComplete: boolean,
): string[] {
  if (!membershipComplete || !selectedPaths.length) return selectedPaths
  const membership = new Set(membershipPaths)
  const next = selectedPaths.filter((path) => membership.has(path))
  return next.length === selectedPaths.length ? selectedPaths : next
}

export function resolveRetainedSelectedItems(
  selectedPaths: readonly string[],
  candidates: readonly BrowseItemPayload[],
): BrowseItemPayload[] {
  const candidatesByPath = new Map(candidates.map((item) => [item.path, item]))
  return selectedPaths.flatMap((path) => {
    const item = candidatesByPath.get(path)
    return item ? [item] : []
  })
}

export function resolveRetainedCompareItems(
  selectedPaths: readonly string[],
  retainedItems: readonly BrowseItemPayload[],
  selectedItems: readonly BrowseItemPayload[],
): BrowseItemPayload[] {
  const selected = new Set(selectedPaths)
  const liveByPath = new Map(selectedItems.map((item) => [item.path, item]))
  return retainedItems
    .filter((item) => selected.has(item.path))
    .map((item) => liveByPath.get(item.path) ?? item)
}

export function resolveAdjacentImagePath(
  itemPaths: readonly string[],
  currentPath: string | null | undefined,
  delta: number,
): string | null {
  if (!itemPaths.length || !currentPath) return null
  const idx = itemPaths.indexOf(currentPath)
  if (idx === -1) return null
  const next = Math.min(itemPaths.length - 1, Math.max(0, idx + delta))
  const nextPath = itemPaths[next]
  if (!nextPath || nextPath === currentPath) return null
  return nextPath
}

export function resolveViewerGridRestorePath(
  selectedPaths: readonly string[],
  viewerPath: string | null | undefined,
  rememberedPath: string | null | undefined,
): string | null {
  return selectedPaths[0] ?? viewerPath ?? rememberedPath ?? null
}

export function resolveScopeBoundaryViewerPath(explicitViewerPath: string | null | undefined): string | null {
  return explicitViewerPath || null
}

export function useAppSelectionViewerCompare({
  current,
  itemPaths,
  items,
  selectionPool,
  compareOrderMode,
  membershipSettled,
  membershipComplete,
  focusGridCell,
}: UseAppSelectionViewerCompareParams): UseAppSelectionViewerCompareResult {
  const [selectedPaths, setSelectedPaths] = useState<string[]>([])
  const [viewer, setViewer] = useState<string | null>(null)
  const [compareOpen, setCompareOpen] = useState(false)
  const [compareIndex, setCompareIndex] = useState(0)
  const [viewerNavPaths, setViewerNavPaths] = useState<string[]>([])
  const [restoreGridToSelectionToken, setRestoreGridToSelectionToken] = useState(0)
  const viewerHistoryPushedRef = useRef(false)
  const compareHistoryPushedRef = useRef(false)
  const lastFocusedPathRef = useRef<string | null>(null)
  const selectedOwnerRef = useRef<object>({})
  const selectedItemsRef = useRef<BrowseItemPayload[]>([])
  const compareItemsRef = useRef<BrowseItemPayload[]>([])
  const [selectedEntityVersion, setSelectedEntityVersion] = useState(0)

  const selectedPathKey = selectedPaths.join('\u0000')
  useLayoutEffect(() => {
    const owner = selectedOwnerRef.current
    browseEntityStore.setActivePaths(owner, selectedPaths)
    const unsubscribers = selectedPaths.map((path) => (
      browseEntityStore.subscribe(path, () => setSelectedEntityVersion((version) => version + 1))
    ))
    setSelectedEntityVersion((version) => version + 1)
    return () => {
      for (const unsubscribe of unsubscribers) unsubscribe()
      browseEntityStore.release(owner)
    }
  }, [selectedPathKey]) // eslint-disable-line react-hooks/exhaustive-deps

  const targetSelectedItems = useMemo(
    () => resolveSelectionOrderedItems(selectedPaths, selectionPool, items),
    [selectedPaths, selectionPool, items],
  )
  const selectedMembershipReady = canCommitCompareMembership(
    selectedPaths,
    targetSelectedItems,
    membershipSettled,
    membershipComplete,
  )
  useLayoutEffect(() => {
    if (selectedMembershipReady) selectedItemsRef.current = targetSelectedItems
  }, [selectedMembershipReady, targetSelectedItems])
  const selectedCandidates = selectedMembershipReady
    ? targetSelectedItems
    : selectedItemsRef.current
  const selectedBaseItems = useMemo(
    () => resolveRetainedSelectedItems(selectedPaths, selectedCandidates),
    [selectedCandidates, selectedPaths],
  )
  const selectedItems = useMemo(() => selectedBaseItems.flatMap((base) => {
    const item = overlayLiveBrowseEntity(base, browseEntityStore.get(base.path))
    return item ? [item] : []
  }), [selectedBaseItems, selectedEntityVersion])
  const targetCompareItems = useMemo(
    () => resolveCompareOrderedItems(selectedPaths, selectionPool, items, compareOrderMode),
    [selectedPaths, selectionPool, items, compareOrderMode],
  )
  const compareMembershipReady = canCommitCompareMembership(
    selectedPaths,
    targetCompareItems,
    membershipSettled,
    membershipComplete,
  )
  useLayoutEffect(() => {
    if (!compareOpen || compareMembershipReady) compareItemsRef.current = targetCompareItems
  }, [compareMembershipReady, compareOpen, targetCompareItems])
  const compareItems = useMemo(() => {
    if (!compareOpen || compareMembershipReady) return targetCompareItems
    return resolveRetainedCompareItems(selectedPaths, compareItemsRef.current, selectedItems)
  }, [compareMembershipReady, compareOpen, selectedItems, selectedPaths, targetCompareItems])
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
  const activeViewerNavPaths = viewer && viewerNavPaths.length ? viewerNavPaths : itemPaths
  const navIdx = navCurrent ? activeViewerNavPaths.indexOf(navCurrent) : -1
  const canPrevImage = navIdx > 0
  const canNextImage = navIdx >= 0 && navIdx < activeViewerNavPaths.length - 1

  useEffect(() => {
    setCompareIndex((prev) => (prev > compareMaxIndex ? compareMaxIndex : prev))
  }, [compareMaxIndex])

  const bumpRestoreGridToSelectionToken = useCallback(() => {
    setRestoreGridToSelectionToken((token) => token + 1)
  }, [])

  const restoreGridToPath = useCallback((path: string | null | undefined) => {
    if (!path) return
    lastFocusedPathRef.current = path
    setRestoreGridToSelectionToken((token) => token + 1)
    focusGridCell(path)
  }, [focusGridCell])

  const rememberFocusedPath = useCallback((path: string) => {
    lastFocusedPathRef.current = path
  }, [])

  const resetViewerState = useCallback(() => {
    setViewer(null)
    setViewerNavPaths([])
    viewerHistoryPushedRef.current = false
  }, [])

  const resetForScopeBoundary = useCallback((explicitViewerPath?: string | null) => {
    const preservedViewer = resolveScopeBoundaryViewerPath(explicitViewerPath)
    setCompareOpen(false)
    setCompareIndex(0)
    compareHistoryPushedRef.current = false
    viewerHistoryPushedRef.current = false

    if (preservedViewer) {
      setViewer(preservedViewer)
      setViewerNavPaths(itemPaths.includes(preservedViewer) ? itemPaths : [])
      setSelectedPaths([preservedViewer])
      lastFocusedPathRef.current = preservedViewer
      return
    }

    setSelectedPaths([])
    setViewer(null)
    setViewerNavPaths([])
    lastFocusedPathRef.current = null
  }, [itemPaths])

  const syncHashImageSelection = useCallback((imageTarget: string | null) => {
    if (imageTarget) {
      setViewer(imageTarget)
      setViewerNavPaths(itemPaths.includes(imageTarget) ? itemPaths : [])
      setSelectedPaths([imageTarget])
      return
    }
    if (viewer) {
      restoreGridToPath(resolveViewerGridRestorePath(selectedPaths, viewer, lastFocusedPathRef.current))
    }
    resetViewerState()
  }, [itemPaths, resetViewerState, restoreGridToPath, selectedPaths, viewer])

  const openViewer = useCallback((path: string) => {
    setViewer(path)
    setViewerNavPaths(itemPaths.includes(path) ? itemPaths : [])
    viewerHistoryPushedRef.current = true
    writeImageHash(path)
  }, [itemPaths])

  const closeViewer = useCallback(() => {
    const restorePath = resolveViewerGridRestorePath(selectedPaths, viewer, lastFocusedPathRef.current)
    setViewer(null)
    setViewerNavPaths([])
    if (viewerHistoryPushedRef.current) {
      viewerHistoryPushedRef.current = false
      window.history.back()
    } else {
      replaceHash(current)
    }
    restoreGridToPath(restorePath)
  }, [current, restoreGridToPath, selectedPaths, viewer])

  const openCompare = useCallback(() => {
    if (compareOpen || !compareEnabled) return
    if (selectedPaths[0]) lastFocusedPathRef.current = selectedPaths[0]
    setCompareIndex(0)
    setCompareOpen(true)

    if (viewer) {
      setViewer(null)
      setViewerNavPaths([])
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
    const currentPath = viewer ?? selectedPaths[0]
    const nextPath = resolveAdjacentImagePath(activeViewerNavPaths, currentPath, delta)
    if (!nextPath) return
    if (viewer) {
      setViewer(nextPath)
      replaceImageHash(nextPath)
    }
    lastFocusedPathRef.current = nextPath
    setSelectedPaths([nextPath])
  }, [activeViewerNavPaths, selectedPaths, viewer])

  useEffect(() => {
    if (!viewer || viewerNavPaths.length || !itemPaths.includes(viewer)) return
    setViewerNavPaths(itemPaths)
  }, [itemPaths, viewer, viewerNavPaths.length])

  useLayoutEffect(() => {
    if (!shouldCloseCompareForSelectionChange(compareOpen, compareEnabled)) return
    closeCompare()
  }, [compareOpen, compareEnabled, closeCompare])

  // Keep browser history semantics for compare/viewer overlays.
  useEffect(() => {
    const onPop = () => {
      const next = resolveOverlayPopstateResult(viewer, compareOpen)
      if (next.resetViewer) {
        restoreGridToPath(resolveViewerGridRestorePath(selectedPaths, viewer, lastFocusedPathRef.current))
        viewerHistoryPushedRef.current = false
        setViewer(null)
        setViewerNavPaths([])
      }
      if (next.resetCompare) {
        compareHistoryPushedRef.current = false
        setCompareOpen(false)
      }
    }
    window.addEventListener('popstate', onPop)
    return () => window.removeEventListener('popstate', onPop)
  }, [compareOpen, restoreGridToPath, selectedPaths, viewer])

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
    resetForScopeBoundary,
    syncHashImageSelection,
  }
}
