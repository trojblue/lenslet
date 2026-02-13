import type { BrowseEndpoint, BrowseRequestBudgetSnapshot } from '../lib/browseHotpath'
import { reportBrowseRequestBudget } from '../lib/browseHotpath'

type BudgetTask<T> = {
  promise: Promise<T>
  abort?: () => void
}

type BudgetFactory<T> = () => BudgetTask<T>

type QueueEntry = {
  id: number
  start: () => void
  reject: (reason?: unknown) => void
}

type ActiveEntry = {
  abort?: () => void
  reject: (reason?: unknown) => void
}

type EndpointState = {
  limit: number
  inflight: Map<number, ActiveEntry>
  queued: QueueEntry[]
  peakInflight: number
}

const ENDPOINTS: BrowseEndpoint[] = ['folders', 'thumb', 'file']

const DEFAULT_LIMITS: Record<BrowseEndpoint, number> = {
  folders: 2,
  thumb: 6,
  file: 3,
}

let nextTaskId = 1

const endpointState: Record<BrowseEndpoint, EndpointState> = {
  folders: { limit: DEFAULT_LIMITS.folders, inflight: new Map(), queued: [], peakInflight: 0 },
  thumb: { limit: DEFAULT_LIMITS.thumb, inflight: new Map(), queued: [], peakInflight: 0 },
  file: { limit: DEFAULT_LIMITS.file, inflight: new Map(), queued: [], peakInflight: 0 },
}

function makeAbortError(): Error {
  if (typeof DOMException !== 'undefined') {
    return new DOMException('request aborted', 'AbortError')
  }
  const error = new Error('request aborted')
  error.name = 'AbortError'
  return error
}

function snapshotCounts(): BrowseRequestBudgetSnapshot {
  return {
    limits: {
      folders: endpointState.folders.limit,
      thumb: endpointState.thumb.limit,
      file: endpointState.file.limit,
    },
    inflight: {
      folders: endpointState.folders.inflight.size,
      thumb: endpointState.thumb.inflight.size,
      file: endpointState.file.inflight.size,
    },
    queued: {
      folders: endpointState.folders.queued.length,
      thumb: endpointState.thumb.queued.length,
      file: endpointState.file.queued.length,
    },
    peakInflight: {
      folders: endpointState.folders.peakInflight,
      thumb: endpointState.thumb.peakInflight,
      file: endpointState.file.peakInflight,
    },
    updatedAtMs: Date.now(),
  }
}

function publishSnapshot(): void {
  reportBrowseRequestBudget(snapshotCounts())
}

function drainQueue(endpoint: BrowseEndpoint): void {
  const state = endpointState[endpoint]
  while (state.inflight.size < state.limit && state.queued.length > 0) {
    const next = state.queued.shift()
    if (!next) break
    next.start()
  }
}

export function runWithRequestBudget<T>(
  endpoint: BrowseEndpoint,
  factory: BudgetFactory<T>,
): BudgetTask<T> {
  const state = endpointState[endpoint]
  const taskId = nextTaskId
  nextTaskId += 1
  let settled = false
  let started = false
  let activeEntry: ActiveEntry | null = null

  const promise = new Promise<T>((resolve, reject) => {
    const finish = () => {
      if (!started) return
      started = false
      state.inflight.delete(taskId)
      drainQueue(endpoint)
      publishSnapshot()
    }

    const start = () => {
      if (settled || started) return
      started = true
      let scheduled: BudgetTask<T>
      try {
        scheduled = factory()
      } catch (error) {
        settled = true
        finish()
        reject(error)
        return
      }

      activeEntry = {
        abort: scheduled.abort,
        reject,
      }
      state.inflight.set(taskId, activeEntry)
      state.peakInflight = Math.max(state.peakInflight, state.inflight.size)
      publishSnapshot()

      scheduled.promise.then(
        (value) => {
          if (settled) return
          settled = true
          finish()
          resolve(value)
        },
        (error) => {
          if (settled) return
          settled = true
          finish()
          reject(error)
        },
      )
    }

    if (state.inflight.size < state.limit) {
      start()
      return
    }

    state.queued.push({
      id: taskId,
      start,
      reject,
    })
    publishSnapshot()
  })

  const abort = () => {
    if (settled) return
    settled = true
    if (started) {
      state.inflight.delete(taskId)
      if (activeEntry?.abort) {
        try {
          activeEntry.abort()
        } catch {
          // Ignore abort errors.
        }
      }
      activeEntry?.reject(makeAbortError())
      drainQueue(endpoint)
      publishSnapshot()
      return
    }

    const queueIndex = state.queued.findIndex((entry) => entry.id === taskId)
    if (queueIndex >= 0) {
      const [queued] = state.queued.splice(queueIndex, 1)
      queued.reject(makeAbortError())
      publishSnapshot()
    }
  }

  return { promise, abort }
}

export function cancelBrowseRequests(endpoints: readonly BrowseEndpoint[] = ENDPOINTS): void {
  for (const endpoint of endpoints) {
    const state = endpointState[endpoint]
    for (const active of Array.from(state.inflight.values())) {
      if (active.abort) {
        try {
          active.abort()
        } catch {
          // Ignore abort errors.
        }
      }
      active.reject(makeAbortError())
    }
    state.inflight.clear()
    const queued = state.queued.splice(0, state.queued.length)
    for (const entry of queued) {
      entry.reject(makeAbortError())
    }
  }
  publishSnapshot()
}

export function getBrowseRequestBudgetSnapshot(): BrowseRequestBudgetSnapshot {
  return snapshotCounts()
}

export function resetBrowseRequestBudgetForTests(): void {
  nextTaskId = 1
  for (const endpoint of ENDPOINTS) {
    const state = endpointState[endpoint]
    state.inflight.clear()
    state.queued = []
    state.peakInflight = 0
    state.limit = DEFAULT_LIMITS[endpoint]
  }
  publishSnapshot()
}

publishSnapshot()
