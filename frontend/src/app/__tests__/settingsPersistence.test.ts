import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'
import {
  createDeferredWriteScheduler,
  type PersistedAppShellSettings,
} from '../model/appShellStateSync'
import {
  readInitialPersistedAppShellSettings,
  readPersistedSettingsFromStorage,
  writePersistedSettingsToStorage,
} from '../hooks/usePersistedAppShellSettings'

class MemoryStorage implements Storage {
  private values = new Map<string, string>()

  get length(): number {
    return this.values.size
  }

  clear(): void {
    this.values.clear()
  }

  getItem(key: string): string | null {
    return this.values.get(key) ?? null
  }

  key(index: number): string | null {
    return Array.from(this.values.keys())[index] ?? null
  }

  removeItem(key: string): void {
    this.values.delete(key)
  }

  setItem(key: string, value: string): void {
    this.values.set(key, value)
  }
}

function makeSettings(overrides: Partial<PersistedAppShellSettings> = {}): PersistedAppShellSettings {
  return {
    viewMode: 'adaptive',
    gridItemSize: 220,
    leftOpen: true,
    rightOpen: true,
    autoloadImageMetadata: true,
    compareOrderMode: 'gallery',
    proxyHttpOriginals: false,
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

    const scheduler = createDeferredWriteScheduler<PersistedAppShellSettings>((snapshot) => {
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
    const scheduler = createDeferredWriteScheduler<PersistedAppShellSettings>((snapshot) => {
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

describe('settings persistence view-state contract', () => {
  it('persists personal display settings and clears stored analysis state', () => {
    const storage = new MemoryStorage()
    storage.setItem('viewState', JSON.stringify({
      sort: { kind: 'metric', key: 'saved_score', dir: 'desc' },
      filters: { and: [{ starsIn: { values: [5] } }] },
    }))
    storage.setItem('sortSpec', JSON.stringify({ kind: 'builtin', key: 'name', dir: 'asc' }))
    storage.setItem('filterAst', JSON.stringify({ and: [{ starsIn: { values: [5] } }] }))
    storage.setItem('selectedMetric', 'score')

    writePersistedSettingsToStorage(storage, makeSettings({
      viewMode: 'grid',
      gridItemSize: 260,
      leftOpen: false,
      compareOrderMode: 'selection',
      proxyHttpOriginals: true,
    }))

    expect(storage.getItem('viewState')).toBeNull()
    expect(storage.getItem('sortSpec')).toBeNull()
    expect(storage.getItem('filterAst')).toBeNull()
    expect(storage.getItem('selectedMetric')).toBeNull()

    expect(readPersistedSettingsFromStorage(storage)).toEqual({
      viewMode: 'grid',
      gridItemSize: 260,
      leftOpen: false,
      autoloadImageMetadata: true,
      compareOrderMode: 'selection',
      proxyHttpOriginals: true,
    })
  })

  it('does not restore legacy separate sort, filter, or selected metric keys', () => {
    const storage = new MemoryStorage()
    storage.setItem('sortSpec', JSON.stringify({ kind: 'metric', key: '@derived/rubric_1', dir: 'desc' }))
    storage.setItem('filterAst', JSON.stringify({ and: [{ metricRange: { key: '@derived/rubric_1', min: 0, max: 1 } }] }))
    storage.setItem('selectedMetric', '@derived/rubric_1')

    expect(readPersistedSettingsFromStorage(storage)).toEqual({})
  })

  it('rejects invalid personal settings while retaining independently valid values', () => {
    const storage = new MemoryStorage()
    storage.setItem('viewMode', 'masonry')
    storage.setItem('gridItemSize', '9999')
    storage.setItem('leftOpen', 'sometimes')
    storage.setItem('rightOpen', '0')
    storage.setItem('autoloadImageMetadata', 'true')
    storage.setItem('compareOrderMode', 'side-by-side')
    storage.setItem('proxyHttpOriginals', '1')

    expect(readPersistedSettingsFromStorage(storage)).toEqual({
      rightOpen: false,
      autoloadImageMetadata: true,
      proxyHttpOriginals: true,
    })
  })

  it('uses deterministic defaults when no browser storage exists', () => {
    expect(readInitialPersistedAppShellSettings()).toEqual({})
  })
})
