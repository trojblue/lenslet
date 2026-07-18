import { useEffect, useLayoutEffect, useMemo, useRef, useState } from 'react'
import type { BrowseItemPayload } from '../../lib/types'
import type { GridStatus } from '../model/loadingState'
import { browseEntityStore } from '../model/browseEntityStore'

export const GRID_PRESENTATION_GRACE_MS = 800

export type GridPresentationPhase = 'steady' | 'grace' | 'loading'

export type PresentedBrowseSnapshot = {
  targetKey: string | null
  requestedTargetKey: string
  resetKey: string
  epoch: number
  membershipPaths: string[]
  ratingPaths: string[]
  items: BrowseItemPayload[]
  ratingItems: BrowseItemPayload[]
  filteredCount: number | null
  displayItemCount: number | null
  displayTotalCount: number | null
  metricsPopulationItemsComplete: boolean
  metricsFilteredItemsComplete: boolean
  metricRailReady: boolean
  metricRailKey: string | null
  metricRailSortDir: 'asc' | 'desc'
  phase: GridPresentationPhase
  retained: boolean
}

export type BrowseSnapshotTarget = {
  targetKey: string
  resetKey: string
  membershipPaths: string[]
  ratingPaths: string[]
  filteredCount: number
  displayItemCount: number
  displayTotalCount: number
  metricsPopulationItemsComplete: boolean
  metricsFilteredItemsComplete: boolean
  metricRailReady: boolean
  metricRailKey: string | null
  metricRailSortDir: 'asc' | 'desc'
  settled: boolean
  statusKind: GridStatus['kind']
}

export type CommittedBrowseSnapshot = Omit<
  PresentedBrowseSnapshot,
  'requestedTargetKey' | 'items' | 'ratingItems' | 'phase' | 'retained'
>

type ResolvedBrowseSnapshot = Omit<PresentedBrowseSnapshot, 'items' | 'ratingItems'>

function targetSnapshot(
  target: BrowseSnapshotTarget,
  previous: CommittedBrowseSnapshot | null,
): CommittedBrowseSnapshot {
  const sameIdentity = previous?.targetKey === target.targetKey
    && previous.resetKey === target.resetKey
  const countsReady = target.settled
  return {
    targetKey: target.targetKey,
    resetKey: target.resetKey,
    epoch: sameIdentity ? previous.epoch : (previous?.epoch ?? 0) + 1,
    membershipPaths: target.membershipPaths,
    ratingPaths: target.ratingPaths,
    filteredCount: countsReady ? target.filteredCount : null,
    displayItemCount: countsReady ? target.displayItemCount : null,
    displayTotalCount: countsReady ? target.displayTotalCount : null,
    metricsPopulationItemsComplete: countsReady && target.metricsPopulationItemsComplete,
    metricsFilteredItemsComplete: countsReady && target.metricsFilteredItemsComplete,
    metricRailReady: countsReady && target.metricRailReady,
    metricRailKey: target.metricRailKey,
    metricRailSortDir: target.metricRailSortDir,
  }
}

export function resolvePresentedBrowseSnapshot({
  target,
  previous,
  expiredTargetKey,
}: {
  target: BrowseSnapshotTarget
  previous: CommittedBrowseSnapshot | null
  expiredTargetKey: string | null
}): ResolvedBrowseSnapshot {
  const pending = target.statusKind === 'loading'
    || (target.statusKind === 'updating' && !target.settled)
  if (!pending) {
    return {
      ...targetSnapshot(target, previous),
      requestedTargetKey: target.targetKey,
      phase: 'steady',
      retained: false,
    }
  }

  const canRetain = previous?.resetKey === target.resetKey
    && previous.membershipPaths.length > 0
    && expiredTargetKey !== target.targetKey
  if (canRetain) {
    return {
      ...previous,
      requestedTargetKey: target.targetKey,
      phase: 'grace',
      retained: true,
    }
  }

  return {
    targetKey: null,
    requestedTargetKey: target.targetKey,
    resetKey: target.resetKey,
    epoch: previous?.epoch ?? 0,
    membershipPaths: [],
    ratingPaths: [],
    filteredCount: null,
    displayItemCount: null,
    displayTotalCount: null,
    metricsPopulationItemsComplete: false,
    metricsFilteredItemsComplete: false,
    metricRailReady: false,
    metricRailKey: null,
    metricRailSortDir: target.metricRailSortDir,
    phase: 'loading',
    retained: false,
  }
}

function committedSnapshot(snapshot: ResolvedBrowseSnapshot): CommittedBrowseSnapshot {
  return {
    targetKey: snapshot.targetKey,
    resetKey: snapshot.resetKey,
    epoch: snapshot.epoch,
    membershipPaths: snapshot.membershipPaths,
    ratingPaths: snapshot.ratingPaths,
    filteredCount: snapshot.filteredCount,
    displayItemCount: snapshot.displayItemCount,
    displayTotalCount: snapshot.displayTotalCount,
    metricsPopulationItemsComplete: snapshot.metricsPopulationItemsComplete,
    metricsFilteredItemsComplete: snapshot.metricsFilteredItemsComplete,
    metricRailReady: snapshot.metricRailReady,
    metricRailKey: snapshot.metricRailKey,
    metricRailSortDir: snapshot.metricRailSortDir,
  }
}

export function overlayLiveBrowseEntity(
  base: BrowseItemPayload | undefined,
  live: BrowseItemPayload | undefined,
): BrowseItemPayload | undefined {
  if (!base) return live
  if (!live || base === live) return base
  const metrics = { ...(base.metrics ?? {}) }
  for (const key of base.mutable_metric_keys ?? []) delete metrics[key]
  for (const key of live.mutable_metric_keys ?? []) {
    const value = live.metrics?.[key]
    if (value != null) metrics[key] = value
  }
  return {
    ...base,
    star: live.star,
    notes: live.notes,
    metrics: Object.keys(metrics).length ? metrics : undefined,
    mutable_metric_keys: live.mutable_metric_keys,
  }
}

function useLivePresentedItems(
  snapshot: ResolvedBrowseSnapshot,
  targetKey: string,
  targetItems: BrowseItemPayload[],
  targetRatingItems: BrowseItemPayload[],
  committedItemsByPath: Map<string, BrowseItemPayload>,
): { items: BrowseItemPayload[]; ratingItems: BrowseItemPayload[] } {
  const ownerRef = useRef<object>({})
  const [version, setVersion] = useState(0)
  const subscribedPaths = useMemo(
    () => Array.from(new Set([...snapshot.membershipPaths, ...snapshot.ratingPaths])),
    [snapshot.membershipPaths, snapshot.ratingPaths],
  )
  const subscribedPathKey = subscribedPaths.join('\u0000')

  useLayoutEffect(() => {
    const owner = ownerRef.current
    browseEntityStore.seed([...targetRatingItems, ...targetItems])
    browseEntityStore.setActivePaths(owner, subscribedPaths)
    const unsubscribers = subscribedPaths.map((path) => (
      browseEntityStore.subscribe(path, () => setVersion((current) => current + 1))
    ))
    setVersion((current) => current + 1)
    return () => {
      for (const unsubscribe of unsubscribers) unsubscribe()
      browseEntityStore.release(owner)
    }
  }, [subscribedPathKey]) // eslint-disable-line react-hooks/exhaustive-deps

  const targetByPath = useMemo(() => {
    const byPath = new Map<string, BrowseItemPayload>()
    for (const item of targetRatingItems) byPath.set(item.path, item)
    for (const item of targetItems) byPath.set(item.path, item)
    return byPath
  }, [targetItems, targetRatingItems])
  const useTargetItems = snapshot.targetKey === targetKey && !snapshot.retained

  return useMemo(() => {
    const resolve = (paths: string[]) => paths.flatMap((path) => {
      const base = useTargetItems ? targetByPath.get(path) : committedItemsByPath.get(path)
      const item = overlayLiveBrowseEntity(base, browseEntityStore.get(path))
      return item ? [item] : []
    })
    return {
      items: resolve(snapshot.membershipPaths),
      ratingItems: resolve(snapshot.ratingPaths),
    }
  }, [
    snapshot.membershipPaths,
    snapshot.ratingPaths,
    committedItemsByPath,
    targetByPath,
    useTargetItems,
    version,
  ])
}

export function useGridPresentation({
  targetKey,
  resetKey,
  targetItems,
  targetRatingItems,
  targetFilteredCount,
  targetDisplayItemCount,
  targetDisplayTotalCount,
  targetMetricsPopulationItemsComplete,
  targetMetricsFilteredItemsComplete,
  targetMetricRailReady,
  targetMetricRailKey,
  targetMetricRailSortDir,
  targetSettled,
  targetStatus,
}: {
  targetKey: string
  resetKey: string
  targetItems: BrowseItemPayload[]
  targetRatingItems: BrowseItemPayload[]
  targetFilteredCount: number
  targetDisplayItemCount: number
  targetDisplayTotalCount: number
  targetMetricsPopulationItemsComplete: boolean
  targetMetricsFilteredItemsComplete: boolean
  targetMetricRailReady: boolean
  targetMetricRailKey: string | null
  targetMetricRailSortDir: 'asc' | 'desc'
  targetSettled: boolean
  targetStatus: GridStatus
}): PresentedBrowseSnapshot {
  const committedRef = useRef<CommittedBrowseSnapshot | null>(null)
  const committedItemsRef = useRef(new Map<string, BrowseItemPayload>())
  const latestTargetKeyRef = useRef(targetKey)
  const [expiredTargetKey, setExpiredTargetKey] = useState<string | null>(null)
  latestTargetKeyRef.current = targetKey

  const target = useMemo<BrowseSnapshotTarget>(() => ({
    targetKey,
    resetKey,
    membershipPaths: targetItems.map((item) => item.path),
    ratingPaths: targetRatingItems.map((item) => item.path),
    filteredCount: targetFilteredCount,
    displayItemCount: targetDisplayItemCount,
    displayTotalCount: targetDisplayTotalCount,
    metricsPopulationItemsComplete: targetMetricsPopulationItemsComplete,
    metricsFilteredItemsComplete: targetMetricsFilteredItemsComplete,
    metricRailReady: targetMetricRailReady,
    metricRailKey: targetMetricRailKey,
    metricRailSortDir: targetMetricRailSortDir,
    settled: targetSettled,
    statusKind: targetStatus.kind,
  }), [
    resetKey,
    targetDisplayItemCount,
    targetDisplayTotalCount,
    targetFilteredCount,
    targetItems,
    targetKey,
    targetMetricRailReady,
    targetMetricRailKey,
    targetMetricRailSortDir,
    targetMetricsPopulationItemsComplete,
    targetMetricsFilteredItemsComplete,
    targetRatingItems,
    targetSettled,
    targetStatus.kind,
  ])
  const resolved = resolvePresentedBrowseSnapshot({
    target,
    previous: committedRef.current,
    expiredTargetKey,
  })
  const liveItems = useLivePresentedItems(
    resolved,
    targetKey,
    targetItems,
    targetRatingItems,
    committedItemsRef.current,
  )
  const targetPending = targetStatus.kind === 'loading'
    || (targetStatus.kind === 'updating' && !targetSettled)
  const canRetain = targetPending
    && committedRef.current?.resetKey === resetKey
    && (committedRef.current?.membershipPaths.length ?? 0) > 0

  useLayoutEffect(() => {
    setExpiredTargetKey(null)
  }, [resetKey, targetKey])

  useEffect(() => {
    if (!canRetain) return
    const timeoutId = window.setTimeout(() => {
      if (latestTargetKeyRef.current === targetKey) setExpiredTargetKey(targetKey)
    }, GRID_PRESENTATION_GRACE_MS)
    return () => window.clearTimeout(timeoutId)
  }, [canRetain, resetKey, targetKey])

  useLayoutEffect(() => {
    if (resolved.phase !== 'steady') return
    if (latestTargetKeyRef.current !== targetKey) return
    committedRef.current = committedSnapshot(resolved)
    const itemsByPath = new Map<string, BrowseItemPayload>()
    for (const item of targetRatingItems) itemsByPath.set(item.path, item)
    for (const item of targetItems) itemsByPath.set(item.path, item)
    committedItemsRef.current = itemsByPath
  }, [resolved, targetItems, targetKey, targetRatingItems])

  return {
    ...resolved,
    ...liveItems,
  }
}
