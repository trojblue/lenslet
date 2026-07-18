import { describe, expect, it, vi } from 'vitest'
import type {
  AcceptedEventIdentity,
  LabelPersistenceState,
  SidecarMutationResponse,
} from '../../lib/types'
import {
  LabelPersistenceTracker,
  requestLabelPersistenceRefresh,
  subscribeLabelPersistenceRefresh,
} from '../labelPersistence'

function identity(bootEpoch: string, eventId: number): AcceptedEventIdentity {
  return { boot_epoch: bootEpoch, event_id: eventId }
}

function status(
  bootEpoch: string,
  eventId: number,
  state: LabelPersistenceState['state'] = 'saved',
): LabelPersistenceState {
  return {
    enabled: true,
    boot_epoch: bootEpoch,
    state,
    durable_watermark: identity(bootEpoch, eventId),
    pending_count: state === 'pending' ? 1 : 0,
    pending_bytes: state === 'pending' ? 128 : 0,
    max_pending_count: 10_000,
    max_pending_bytes: 16 * 1024 * 1024,
    error: state === 'failed' ? 'disk full' : null,
    failure_total: state === 'failed' ? 1 : 0,
    deadline_breach_total: 0,
  }
}

function response(bootEpoch: string, eventId: number): SidecarMutationResponse {
  return {
    sidecar: {
      v: 1,
      tags: [],
      notes: '',
      version: 2,
      updated_at: '',
      updated_by: 'test',
    },
    mutation_id: `mutation-${eventId}`,
    accepted_event: identity(bootEpoch, eventId),
    persistence: 'pending',
    durable_watermark: identity(bootEpoch, eventId - 1),
  }
}

function noopResponse(
  bootEpoch: string,
  eventId: number,
  persistence: SidecarMutationResponse['persistence'] = 'pending',
): SidecarMutationResponse {
  return {
    ...response(bootEpoch, eventId),
    accepted_event: null,
    persistence,
    durable_watermark: identity(bootEpoch, eventId),
  }
}

describe('LabelPersistenceTracker', () => {
  it('routes explicit status refresh requests to the reconciliation owner', () => {
    const listener = vi.fn()
    const unsubscribe = subscribeLabelPersistenceRefresh(listener)

    requestLabelPersistenceRefresh()
    unsubscribe()
    requestLabelPersistenceRefresh()

    expect(listener).toHaveBeenCalledTimes(1)
  })

  it('deduplicates response/event reordering and saves only at the watermark', () => {
    const tracker = new LabelPersistenceTracker()
    const listener = vi.fn()
    tracker.subscribe(listener)

    tracker.observeMutation('/a.jpg', response('epoch-a', 2))
    tracker.observeAccepted('/a.jpg', identity('epoch-a', 2), 'pending', identity('epoch-a', 1))
    expect(tracker.snapshot()).toMatchObject({ state: 'saving', pendingCount: 1 })

    tracker.observeStatus(status('epoch-a', 1, 'pending'))
    expect(tracker.snapshot().state).toBe('saving')
    tracker.observeStatus(status('epoch-a', 2))
    expect(tracker.snapshot()).toMatchObject({ state: 'saved', pendingCount: 0 })
    expect(listener).toHaveBeenCalled()
  })

  it('tracks tabs independently while converging on one durable watermark', () => {
    const owner = new LabelPersistenceTracker()
    const remote = new LabelPersistenceTracker()
    owner.observeMutation('/a.jpg', response('epoch-a', 3))
    remote.observeAccepted('/a.jpg', identity('epoch-a', 3), 'pending', identity('epoch-a', 2))

    expect(owner.snapshot().state).toBe('saving')
    expect(remote.snapshot().state).toBe('saving')
    owner.observeStatus(status('epoch-a', 3))
    remote.observeStatus(status('epoch-a', 3))
    expect(owner.snapshot().state).toBe('saved')
    expect(remote.snapshot().state).toBe('saved')
  })

  it('does not regress to Saving when the durable event beats its HTTP response', () => {
    const tracker = new LabelPersistenceTracker()
    tracker.observeStatus(status('epoch-a', 2))

    tracker.observeMutation('/a.jpg', response('epoch-a', 2))

    expect(tracker.snapshot()).toMatchObject({ state: 'saved', pendingCount: 0 })
  })

  it('keeps a no-op Pending response unsaved until server status catches up', () => {
    const tracker = new LabelPersistenceTracker()

    tracker.observeMutation('/a.jpg', noopResponse('epoch-a', 1))
    expect(tracker.snapshot()).toMatchObject({ state: 'saving', pendingCount: 1 })
    tracker.observeStatus(status('epoch-a', 1, 'pending'))
    expect(tracker.snapshot().state).toBe('saving')

    tracker.observeStatus(status('epoch-a', 2))
    expect(tracker.snapshot()).toMatchObject({ state: 'saved', pendingCount: 0 })
  })

  it('repairs a no-op Pending path when the server epoch changes', () => {
    const tracker = new LabelPersistenceTracker()
    tracker.observeMutation('/a.jpg', noopResponse('epoch-a', 1))

    const repairs = tracker.observeStatus(status('epoch-b', 0))

    expect(repairs.map(({ path }) => path)).toEqual(['/a.jpg'])
    expect(tracker.snapshot().state).toBe('saving')
  })

  it('returns affected paths for epoch repair and never compares cross-epoch ids', () => {
    const tracker = new LabelPersistenceTracker()
    tracker.observeMutation('/a.jpg', response('epoch-a', 40))
    tracker.observeMutation('/b.jpg', response('epoch-a', 41))

    const repair = tracker.observeStatus(status('epoch-b', 5))

    expect(new Set(repair.map(({ path }) => path))).toEqual(new Set(['/a.jpg', '/b.jpg']))
    expect(tracker.snapshot()).toMatchObject({ state: 'saving', bootEpoch: 'epoch-b' })
    tracker.acknowledgeRepairs(repair)
    expect(tracker.snapshot()).toMatchObject({ state: 'saved', bootEpoch: 'epoch-b' })
  })

  it('retains epoch repairs until the reconciliation owner acknowledges them', () => {
    const tracker = new LabelPersistenceTracker()
    tracker.observeMutation('/a.jpg', response('epoch-a', 40))

    tracker.observeStatus(status('epoch-b', 5)) // Health polling observes this first.
    const repair = tracker.observeStatus(status('epoch-b', 5))

    expect(repair.map(({ path }) => path)).toEqual(['/a.jpg'])
    tracker.acknowledgeRepairs(repair)
    expect(tracker.observeStatus(status('epoch-b', 5))).toEqual([])
  })

  it('does not let an older repair acknowledgement clear a newer epoch repair', () => {
    const tracker = new LabelPersistenceTracker()
    tracker.observeMutation('/a.jpg', response('epoch-a', 40))
    const firstRepair = tracker.observeStatus(status('epoch-b', 5))
    tracker.observeAccepted('/a.jpg', identity('epoch-b', 6), 'pending', identity('epoch-b', 5))
    const secondRepair = tracker.observeStatus(status('epoch-c', 1))

    tracker.acknowledgeRepairs(firstRepair)
    expect(tracker.snapshot().state).toBe('saving')
    expect(tracker.observeStatus(status('epoch-c', 1))).toEqual(secondRepair)

    tracker.acknowledgeRepairs(secondRepair)
    expect(tracker.snapshot().state).toBe('saved')
  })

  it('keeps failure actionable until a healthy status confirms recovery', () => {
    const tracker = new LabelPersistenceTracker()
    tracker.observeMutation('/a.jpg', response('epoch-a', 2))
    tracker.observeStatus(status('epoch-a', 1, 'failed'))
    expect(tracker.snapshot()).toMatchObject({ state: 'failed', error: 'disk full' })

    tracker.observeStatus(status('epoch-a', 2))
    expect(tracker.snapshot()).toMatchObject({ state: 'saved', error: null, pendingCount: 0 })
  })

  it('ignores delayed retired-epoch events after a failed sync-state transition', () => {
    const tracker = new LabelPersistenceTracker()
    const refresh = vi.fn()
    const unsubscribe = subscribeLabelPersistenceRefresh(refresh)
    tracker.observeStatus(status('epoch-a', 3), 'sync')
    tracker.observeStatus(status('epoch-b', 0, 'failed'), 'sync')

    tracker.observeStatus(status('epoch-a', 3), 'event')
    tracker.observeAccepted(
      '/a.jpg',
      identity('epoch-a', 3),
      'saved',
      identity('epoch-a', 3),
    )

    expect(tracker.snapshot()).toMatchObject({
      state: 'failed',
      bootEpoch: 'epoch-b',
      error: 'disk full',
    })
    expect(refresh).toHaveBeenCalledTimes(2)
    unsubscribe()
  })

  it('requires sync-state confirmation to clear a same-epoch failure', () => {
    const tracker = new LabelPersistenceTracker()
    const refresh = vi.fn()
    const unsubscribe = subscribeLabelPersistenceRefresh(refresh)

    tracker.observeStatus(status('epoch-a', 1, 'failed'), 'event')
    tracker.observeStatus(status('epoch-a', 1), 'health')
    tracker.observeStatus(status('epoch-a', 1), 'event')

    expect(tracker.snapshot()).toMatchObject({ state: 'failed', error: 'disk full' })
    expect(refresh).toHaveBeenCalledTimes(3)
    tracker.observeStatus(status('epoch-a', 1), 'sync')
    expect(tracker.snapshot()).toMatchObject({ state: 'saved', error: null })
    unsubscribe()
  })
})
