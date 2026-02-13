import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'
import {
  cancelBrowseRequests,
  getBrowseRequestBudgetSnapshot,
  resetBrowseRequestBudgetForTests,
  runWithRequestBudget,
} from '../requestBudget'

function createDeferred<T>() {
  let resolve!: (value: T) => void
  let reject!: (reason?: unknown) => void
  const promise = new Promise<T>((res, rej) => {
    resolve = res
    reject = rej
  })
  return { promise, resolve, reject }
}

beforeEach(() => {
  resetBrowseRequestBudgetForTests()
})

afterEach(() => {
  cancelBrowseRequests()
  resetBrowseRequestBudgetForTests()
  vi.restoreAllMocks()
})

type EndpointName = 'folders' | 'thumb' | 'file'
type EndpointRun = {
  endpoint: EndpointName
  deferred: ReturnType<typeof createDeferred<number>>
  task: ReturnType<typeof runWithRequestBudget<number>>
}

describe('browse request budget', () => {
  it('keeps endpoint peaks within configured limits', async () => {
    const endpoints = [
      { name: 'folders' as const, limit: 2 },
      { name: 'thumb' as const, limit: 6 },
      { name: 'file' as const, limit: 3 },
    ]
    const runs: EndpointRun[] = []

    for (const endpoint of endpoints) {
      for (let idx = 0; idx < endpoint.limit + 1; idx += 1) {
        const deferred = createDeferred<number>()
        const task = runWithRequestBudget(endpoint.name, () => ({ promise: deferred.promise }))
        runs.push({ endpoint: endpoint.name, deferred, task })
      }
    }

    const queuedSnapshot = getBrowseRequestBudgetSnapshot()
    expect(queuedSnapshot.inflight).toEqual({ folders: 2, thumb: 6, file: 3 })
    expect(queuedSnapshot.queued).toEqual({ folders: 1, thumb: 1, file: 1 })

    for (const endpoint of endpoints) {
      const endpointRuns = runs.filter((run) => run.endpoint === endpoint.name)
      endpointRuns[0].deferred.resolve(1)
      await expect(endpointRuns[0].task.promise).resolves.toBe(1)
    }
    await Promise.resolve()

    for (const run of runs.slice(1)) {
      run.deferred.resolve(2)
    }
    await Promise.all(runs.slice(1).map((run) => run.task.promise))

    const snapshot = getBrowseRequestBudgetSnapshot()
    expect(snapshot.peakInflight).toEqual({ folders: 2, thumb: 6, file: 3 })
    expect(snapshot.inflight).toEqual({ folders: 0, thumb: 0, file: 0 })
    expect(snapshot.queued).toEqual({ folders: 0, thumb: 0, file: 0 })
  })

  it('enforces endpoint in-flight caps and queues overflow', async () => {
    const started: number[] = []
    const d1 = createDeferred<number>()
    const d2 = createDeferred<number>()
    const d3 = createDeferred<number>()

    const r1 = runWithRequestBudget('folders', () => {
      started.push(1)
      return { promise: d1.promise }
    })
    const r2 = runWithRequestBudget('folders', () => {
      started.push(2)
      return { promise: d2.promise }
    })
    const r3 = runWithRequestBudget('folders', () => {
      started.push(3)
      return { promise: d3.promise }
    })

    expect(started).toEqual([1, 2])
    expect(getBrowseRequestBudgetSnapshot().inflight.folders).toBe(2)
    expect(getBrowseRequestBudgetSnapshot().queued.folders).toBe(1)

    d1.resolve(11)
    await expect(r1.promise).resolves.toBe(11)
    await Promise.resolve()

    expect(started).toEqual([1, 2, 3])
    expect(getBrowseRequestBudgetSnapshot().inflight.folders).toBe(2)
    expect(getBrowseRequestBudgetSnapshot().queued.folders).toBe(0)

    d2.resolve(22)
    d3.resolve(33)
    await expect(r2.promise).resolves.toBe(22)
    await expect(r3.promise).resolves.toBe(33)

    const snapshot = getBrowseRequestBudgetSnapshot()
    expect(snapshot.inflight.folders).toBe(0)
    expect(snapshot.peakInflight.folders).toBe(2)
  })

  it('cancels queued and in-flight endpoint requests', async () => {
    const d1 = createDeferred<number>()
    const d2 = createDeferred<number>()
    const d3 = createDeferred<number>()
    const d4 = createDeferred<number>()
    const abortCalls = { count: 0 }

    const makeTask = (deferred: ReturnType<typeof createDeferred<number>>) => runWithRequestBudget('file', () => ({
      promise: deferred.promise,
      abort: () => {
        abortCalls.count += 1
      },
    }))

    const r1 = makeTask(d1)
    const r2 = makeTask(d2)
    const r3 = makeTask(d3)
    const r4 = makeTask(d4)

    expect(getBrowseRequestBudgetSnapshot().inflight.file).toBe(3)
    expect(getBrowseRequestBudgetSnapshot().queued.file).toBe(1)

    cancelBrowseRequests(['file'])

    await expect(r1.promise).rejects.toMatchObject({ name: 'AbortError' })
    await expect(r2.promise).rejects.toMatchObject({ name: 'AbortError' })
    await expect(r3.promise).rejects.toMatchObject({ name: 'AbortError' })
    await expect(r4.promise).rejects.toMatchObject({ name: 'AbortError' })

    expect(abortCalls.count).toBe(3)
    const snapshot = getBrowseRequestBudgetSnapshot()
    expect(snapshot.inflight.file).toBe(0)
    expect(snapshot.queued.file).toBe(0)
  })
})
