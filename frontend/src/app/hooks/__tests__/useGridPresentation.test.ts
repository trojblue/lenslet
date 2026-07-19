import { describe, expect, it } from 'vitest'
import {
  GRID_PRESENTATION_GRACE_MS,
  overlayLiveBrowseEntity,
  resolvePresentedBrowseSnapshot,
  type BrowseSnapshotTarget,
  type CommittedBrowseSnapshot,
} from '../useGridPresentation'
import type { BrowseItemPayload } from '../../../lib/types'

function item(
  path: string,
  overrides: Partial<BrowseItemPayload> = {},
): BrowseItemPayload {
  return {
    path,
    name: path,
    mime: 'image/jpeg',
    width: 8,
    height: 6,
    size: 1,
    has_thumbnail: true,
    has_metadata: false,
    star: null,
    ...overrides,
  }
}

function target(
  targetKey: string,
  overrides: Partial<BrowseSnapshotTarget> = {},
): BrowseSnapshotTarget {
  return {
    targetKey,
    resetKey: 'workspace:/scope-a:session-1',
    membershipPaths: [`/${targetKey}.jpg`],
    ratingPaths: [`/${targetKey}.jpg`],
    filteredCount: 1,
    displayItemCount: 1,
    displayTotalCount: 10,
    metricsPopulationItemsComplete: true,
    metricsFilteredItemsComplete: true,
    metricRailState: 'ready',
    metricRailHistogram: { bins: [1, 2], min: 0, max: 1, count: 3 },
    metricRailKey: 'score',
    metricRailSortDir: 'desc',
    settled: true,
    statusKind: 'ready',
    ...overrides,
  }
}

function commit(
  nextTarget: BrowseSnapshotTarget,
  previous: CommittedBrowseSnapshot | null = null,
): CommittedBrowseSnapshot {
  const resolved = resolvePresentedBrowseSnapshot({
    target: nextTarget,
    previous,
    expiredTargetKey: null,
  })
  const {
    requestedTargetKey: _requestedTargetKey,
    phase: _phase,
    retained: _retained,
    ...snapshot
  } = resolved
  return snapshot
}

describe('presented browse snapshot continuity', () => {
  const settledA = commit(target('a'))

  it('retains one atomic prior snapshot inside the grace window', () => {
    const result = resolvePresentedBrowseSnapshot({
      target: target('b', {
        membershipPaths: [],
        ratingPaths: [],
        filteredCount: 0,
        displayItemCount: 0,
        displayTotalCount: 0,
        metricsFilteredItemsComplete: false,
        metricRailState: 'pending',
        settled: false,
        statusKind: 'loading',
      }),
      previous: settledA,
      expiredTargetKey: null,
    })

    expect(result).toMatchObject({
      targetKey: 'a',
      requestedTargetKey: 'b',
      membershipPaths: ['/a.jpg'],
      filteredCount: 1,
      displayItemCount: 1,
      displayTotalCount: 10,
      metricsPopulationItemsComplete: true,
      metricsFilteredItemsComplete: true,
      metricRailState: 'ready',
      phase: 'grace',
      retained: true,
    })
    expect(GRID_PRESENTATION_GRACE_MS).toBe(800)
  })

  it('retains the complete prior bundle after grace while exposing delayed status phase', () => {
    const result = resolvePresentedBrowseSnapshot({
      target: target('b', { settled: false, statusKind: 'loading' }),
      previous: settledA,
      expiredTargetKey: 'b',
    })

    expect(result).toMatchObject({
      targetKey: 'a',
      requestedTargetKey: 'b',
      membershipPaths: ['/a.jpg'],
      ratingPaths: ['/a.jpg'],
      filteredCount: 1,
      displayItemCount: 1,
      displayTotalCount: 10,
      metricsPopulationItemsComplete: true,
      metricsFilteredItemsComplete: true,
      metricRailState: 'ready',
      metricRailHistogram: { bins: [1, 2], min: 0, max: 1, count: 3 },
      phase: 'loading',
      retained: true,
    })
  })

  it('keeps browse membership pending until the independent metric rail is ready', () => {
    const pendingRail = resolvePresentedBrowseSnapshot({
      target: target('b', {
        settled: false,
        statusKind: 'ready',
        metricRailState: 'pending',
        metricRailHistogram: null,
      }),
      previous: settledA,
      expiredTargetKey: null,
    })
    const readyRail = commit(target('b', {
      metricRailState: 'ready',
      metricRailHistogram: { bins: [3, 1], min: 10, max: 20, count: 4 },
    }), settledA)

    expect(pendingRail).toMatchObject({
      targetKey: 'a',
      requestedTargetKey: 'b',
      metricRailHistogram: { bins: [1, 2], min: 0, max: 1, count: 3 },
      retained: true,
    })
    expect(readyRail).toMatchObject({
      targetKey: 'b',
      metricRailHistogram: { bins: [3, 1], min: 10, max: 20, count: 4 },
    })
  })

  it('increments epochs only when a target or reset boundary commits', () => {
    const refreshedA = commit(target('a', { filteredCount: 2 }), settledA)
    const settledB = commit(target('b'), refreshedA)
    const resetB = commit(target('b', { resetKey: 'workspace:/scope-b:session-2' }), settledB)

    expect(settledA.epoch).toBe(1)
    expect(refreshedA.epoch).toBe(1)
    expect(settledB.epoch).toBe(2)
    expect(resetB.epoch).toBe(3)
  })

  it('commits terminal empty and error targets atomically', () => {
    const empty = commit(target('empty', {
      membershipPaths: [],
      ratingPaths: [],
      filteredCount: 0,
      displayItemCount: 0,
      displayTotalCount: 10,
      metricRailState: 'empty',
      statusKind: 'empty',
    }), settledA)
    const failed = commit(target('failed', {
      membershipPaths: [],
      ratingPaths: [],
      filteredCount: 0,
      displayItemCount: 0,
      displayTotalCount: 0,
      metricsFilteredItemsComplete: false,
      metricsPopulationItemsComplete: false,
      metricRailState: 'pending',
      settled: false,
      statusKind: 'failed',
    }), empty)

    expect(empty).toMatchObject({
      targetKey: 'empty',
      membershipPaths: [],
      filteredCount: 0,
      displayItemCount: 0,
      metricsFilteredItemsComplete: true,
    })
    expect(failed).toMatchObject({
      targetKey: 'failed',
      membershipPaths: [],
      filteredCount: null,
      displayItemCount: null,
      displayTotalCount: null,
      metricsFilteredItemsComplete: false,
      metricRailState: 'error',
      metricRailHistogram: null,
      metricRailKey: null,
    })
  })

  it('invalidates retention immediately across an incompatible reset', () => {
    const result = resolvePresentedBrowseSnapshot({
      target: target('b', {
        resetKey: 'workspace:/scope-b:session-2',
        settled: false,
        statusKind: 'loading',
      }),
      previous: settledA,
      expiredTargetKey: null,
    })

    expect(result).toMatchObject({
      targetKey: null,
      membershipPaths: [],
      phase: 'loading',
      retained: false,
    })
  })

  it('treats unresolved updating data as pending instead of committing cached reset data', () => {
    const result = resolvePresentedBrowseSnapshot({
      target: target('a', {
        resetKey: 'workspace:/scope-a:session-2',
        settled: false,
        statusKind: 'updating',
      }),
      previous: settledA,
      expiredTargetKey: null,
    })

    expect(result).toMatchObject({
      targetKey: null,
      requestedTargetKey: 'a',
      membershipPaths: [],
      phase: 'loading',
      retained: false,
    })
  })

  it('keeps A through A-to-B-to-C and ignores B expiry for the latest C target', () => {
    const pendingB = resolvePresentedBrowseSnapshot({
      target: target('b', { settled: false, statusKind: 'loading' }),
      previous: settledA,
      expiredTargetKey: null,
    })
    const pendingC = resolvePresentedBrowseSnapshot({
      target: target('c', { settled: false, statusKind: 'loading' }),
      previous: settledA,
      expiredTargetKey: 'b',
    })
    const settledC = commit(target('c'), settledA)

    expect(pendingB).toMatchObject({ targetKey: 'a', requestedTargetKey: 'b', phase: 'grace' })
    expect(pendingC).toMatchObject({ targetKey: 'a', requestedTargetKey: 'c', phase: 'grace' })
    expect(settledC).toMatchObject({ targetKey: 'c', membershipPaths: ['/c.jpg'], epoch: 2 })
  })

  it('keeps committed similarity payloads while overlaying live annotations', () => {
    const committed = item('/similar.jpg', {
      star: 1,
      metrics: { derived_score: 0.8, reviewer_score: 1 },
      mutable_metric_keys: ['reviewer_score'],
    })
    const live = item('/similar.jpg', {
      name: 'target-b-name',
      star: 5,
      notes: 'updated during grace',
      metrics: { target_b_score: 99, reviewer_score: 4 },
      mutable_metric_keys: ['reviewer_score'],
    })

    expect(overlayLiveBrowseEntity(committed, undefined)).toBe(committed)
    expect(overlayLiveBrowseEntity(committed, live)).toMatchObject({
      star: 5,
      notes: 'updated during grace',
      metrics: { derived_score: 0.8, reviewer_score: 4 },
    })
    expect(overlayLiveBrowseEntity(committed, live)?.name).toBe('/similar.jpg')
  })
})
