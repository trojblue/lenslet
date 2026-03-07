import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'
import {
  createDeferredWriteScheduler,
  type PersistedAppShellSettings,
} from '../model/appShellStateSync'

function makeSettings(overrides: Partial<PersistedAppShellSettings> = {}): PersistedAppShellSettings {
  return {
    sortSpec: { kind: 'builtin', key: 'added', dir: 'desc' },
    starFilters: [],
    filterAst: { and: [] },
    selectedMetric: undefined,
    viewMode: 'adaptive',
    gridItemSize: 220,
    leftOpen: true,
    rightOpen: true,
    autoloadImageMetadata: true,
    compareOrderMode: 'gallery',
    ...overrides,
  }
}

describe('settings persistence scheduling', () => {
  beforeEach(() => {
    vi.useFakeTimers()
  })

  afterEach(() => {
    vi.useRealTimers()
    vi.restoreAllMocks()
    delete (globalThis as { requestIdleCallback?: unknown }).requestIdleCallback
    delete (globalThis as { cancelIdleCallback?: unknown }).cancelIdleCallback
  })

  it('coalesces repeated writes and commits the latest snapshot during idle time', () => {
    const writes: PersistedAppShellSettings[] = []
    const requestIdleCallback = vi.fn((callback: () => void) => {
      callback()
      return 1
    })
    const cancelIdleCallback = vi.fn()
    Object.assign(globalThis, { requestIdleCallback, cancelIdleCallback })

    const scheduler = createDeferredWriteScheduler((snapshot) => {
      writes.push(snapshot)
    }, 100)

    scheduler.schedule(makeSettings({ viewMode: 'grid' }))
    scheduler.schedule(makeSettings({ viewMode: 'adaptive', gridItemSize: 260 }))

    vi.advanceTimersByTime(99)
    expect(writes).toEqual([])

    vi.advanceTimersByTime(1)
    expect(requestIdleCallback).toHaveBeenCalledTimes(1)
    expect(writes).toEqual([makeSettings({ viewMode: 'adaptive', gridItemSize: 260 })])
  })

  it('flushes the pending snapshot immediately', () => {
    const writes: PersistedAppShellSettings[] = []
    const scheduler = createDeferredWriteScheduler((snapshot) => {
      writes.push(snapshot)
    }, 100)

    const pending = makeSettings({ leftOpen: false })
    scheduler.schedule(pending)
    scheduler.flush()

    expect(writes).toEqual([pending])

    vi.runAllTimers()
    expect(writes).toEqual([pending])
  })
})
