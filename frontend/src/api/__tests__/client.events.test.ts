import { afterEach, describe, expect, it, vi } from 'vitest'

class MemoryStorage implements Storage {
  private store = new Map<string, string>()

  get length(): number {
    return this.store.size
  }

  clear(): void {
    this.store.clear()
  }

  getItem(key: string): string | null {
    return this.store.has(key) ? this.store.get(key) ?? null : null
  }

  key(index: number): string | null {
    return Array.from(this.store.keys())[index] ?? null
  }

  removeItem(key: string): void {
    this.store.delete(key)
  }

  setItem(key: string, value: string): void {
    this.store.set(key, value)
  }
}

class FakeEventSource {
  static CONNECTING = 0
  static OPEN = 1
  static CLOSED = 2
  static instances: FakeEventSource[] = []

  static reset(): void {
    FakeEventSource.instances = []
  }

  static latest(): FakeEventSource {
    const latest = FakeEventSource.instances[FakeEventSource.instances.length - 1]
    if (!latest) {
      throw new Error('no EventSource instances created')
    }
    return latest
  }

  readyState = FakeEventSource.CONNECTING
  onopen: ((this: EventSource, ev: Event) => unknown) | null = null
  onerror: ((this: EventSource, ev: Event) => unknown) | null = null
  readonly url: string
  private listeners = new Map<string, Array<(evt: MessageEvent) => void>>()

  constructor(url: string) {
    this.url = url
    FakeEventSource.instances.push(this)
  }

  addEventListener(type: string, listener: (evt: MessageEvent) => void): void {
    const existing = this.listeners.get(type) ?? []
    existing.push(listener)
    this.listeners.set(type, existing)
  }

  close(): void {
    this.readyState = FakeEventSource.CLOSED
  }

  emitOpen(): void {
    this.readyState = FakeEventSource.OPEN
    this.onopen?.call(this as unknown as EventSource, new Event('open'))
  }

  emitError(): void {
    this.readyState = FakeEventSource.CLOSED
    this.onerror?.call(this as unknown as EventSource, new Event('error'))
  }

  emitEvent(type: string, data: unknown, id?: number): void {
    const listeners = this.listeners.get(type) ?? []
    const payload = typeof data === 'string' ? data : JSON.stringify(data)
    const evt = {
      data: payload,
      lastEventId: id != null ? String(id) : '',
    } as MessageEvent
    for (const listener of listeners) {
      listener(evt)
    }
  }
}

function setWindow(localStorage: Storage, sessionStorage: Storage): void {
  Object.defineProperty(globalThis, 'window', {
    configurable: true,
    writable: true,
    value: {
      localStorage,
      sessionStorage,
      location: {
        origin: 'http://localhost:5173',
        hostname: 'localhost',
      },
      setTimeout,
      clearTimeout,
    },
  })
}

function setEventSource(value: unknown): void {
  Object.defineProperty(globalThis, 'EventSource', {
    configurable: true,
    writable: true,
    value,
  })
}

afterEach(() => {
  vi.useRealTimers()
  vi.restoreAllMocks()
  FakeEventSource.reset()
  delete (globalThis as { window?: unknown }).window
  delete (globalThis as { EventSource?: unknown }).EventSource
})

describe('event stream reconnect lifecycle', () => {
  it('reconnects with backoff and recovers to live status', async () => {
    vi.useFakeTimers()
    vi.resetModules()
    setWindow(new MemoryStorage(), new MemoryStorage())
    setEventSource(FakeEventSource)

    const client = await import('../client')
    client.__resetClientStateForTests()

    client.connectEvents()
    expect(client.getEventStatus()).toBe('connecting')
    expect(FakeEventSource.instances).toHaveLength(1)

    const first = FakeEventSource.latest()
    first.emitOpen()
    expect(client.getEventStatus()).toBe('live')

    first.emitError()
    expect(client.getEventStatus()).toBe('reconnecting')

    vi.advanceTimersByTime(1000)
    expect(FakeEventSource.instances).toHaveLength(2)

    const second = FakeEventSource.latest()
    second.emitOpen()
    expect(client.getEventStatus()).toBe('live')

    client.disconnectEvents()
    expect(client.getEventStatus()).toBe('offline')
  })

  it('switches to offline + polling mode after max reconnect attempts', async () => {
    vi.useFakeTimers()
    vi.resetModules()
    setWindow(new MemoryStorage(), new MemoryStorage())
    setEventSource(FakeEventSource)

    const client = await import('../client')
    client.__resetClientStateForTests()

    client.connectEvents()
    expect(FakeEventSource.instances).toHaveLength(1)

    const delays = [1000, 2000, 4000, 8000]
    for (const delay of delays) {
      FakeEventSource.latest().emitError()
      expect(client.getEventStatus()).toBe('reconnecting')
      vi.advanceTimersByTime(delay)
    }

    expect(FakeEventSource.instances).toHaveLength(5)
    FakeEventSource.latest().emitError()
    expect(client.getEventStatus()).toBe('offline')
    expect(client.getPollingStatus()).toBe(true)

    client.disconnectEvents()
  })

  it('persists last event id and includes it in reconnect URL', async () => {
    vi.useFakeTimers()
    vi.resetModules()
    const localStorage = new MemoryStorage()
    setWindow(localStorage, new MemoryStorage())
    setEventSource(FakeEventSource)

    const client = await import('../client')
    client.__resetClientStateForTests()

    client.connectEvents()
    const first = FakeEventSource.latest()
    first.emitOpen()
    first.emitEvent('item-updated', { path: '/a.jpg', version: 1 }, 42)
    first.emitError()

    vi.advanceTimersByTime(1000)
    const second = FakeEventSource.latest()
    expect(second.url).toContain('last_event_id=42')

    client.disconnectEvents()
  })
})
