import { afterEach, describe, expect, it, vi } from 'vitest'

const LEGACY_CLIENT_ID_KEY = 'lenslet.client_id'
const SESSION_CLIENT_ID_KEY = 'lenslet.client_id.session'

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

function setNavigator(value: unknown): void {
  Object.defineProperty(globalThis, 'navigator', {
    configurable: true,
    writable: true,
    value,
  })
}

function setFetch(value: unknown): void {
  Object.defineProperty(globalThis, 'fetch', {
    configurable: true,
    writable: true,
    value,
  })
}

afterEach(() => {
  vi.restoreAllMocks()
  delete (globalThis as { window?: unknown }).window
  delete (globalThis as { navigator?: unknown }).navigator
  delete (globalThis as { fetch?: unknown }).fetch
})

describe('presence client identity', () => {
  it('uses tab-scoped session ids and keeps id stable across refresh for that tab', async () => {
    const sharedLocal = new MemoryStorage()
    sharedLocal.setItem(LEGACY_CLIENT_ID_KEY, 'legacy-shared-id')
    const tab1Session = new MemoryStorage()
    const tab2Session = new MemoryStorage()

    vi.resetModules()
    setWindow(sharedLocal, tab1Session)
    const client = await import('../client')
    client.__resetClientStateForTests()
    const tab1Id = client.getClientId()
    expect(tab1Id).toBeTruthy()
    expect(tab1Session.getItem(SESSION_CLIENT_ID_KEY)).toBe(tab1Id)
    expect(sharedLocal.getItem(LEGACY_CLIENT_ID_KEY)).toBeNull()

    client.__resetClientStateForTests()
    const tab1RefreshId = client.getClientId()
    expect(tab1RefreshId).toBe(tab1Id)

    client.__resetClientStateForTests()
    setWindow(sharedLocal, tab2Session)
    const tab2Id = client.getClientId()
    expect(tab2Id).toBeTruthy()
    expect(tab2Id).not.toBe(tab1Id)
    expect(tab2Session.getItem(SESSION_CLIENT_ID_KEY)).toBe(tab2Id)
  })
})

describe('presence leave transport', () => {
  it('uses navigator.sendBeacon when available', async () => {
    vi.resetModules()
    setWindow(new MemoryStorage(), new MemoryStorage())
    const sendBeacon = vi.fn(() => true)
    setNavigator({ sendBeacon })
    const fetchSpy = vi.fn(async () => new Response(''))
    setFetch(fetchSpy)

    const client = await import('../client')
    const dispatched = client.dispatchPresenceLeave('/gallery', 'lease-123', 'client-1')

    expect(dispatched).toBe(true)
    expect(sendBeacon).toHaveBeenCalledTimes(1)
    const beaconCalls = sendBeacon.mock.calls as unknown[][]
    const beaconPath = beaconCalls[0]?.[0]
    expect(typeof beaconPath === 'string' ? beaconPath : '').toContain('/presence/leave')
    expect(fetchSpy).not.toHaveBeenCalled()
  })

  it('falls back to fetch keepalive when beacon is unavailable', async () => {
    vi.resetModules()
    setWindow(new MemoryStorage(), new MemoryStorage())
    setNavigator({})
    const fetchSpy = vi.fn(async () => new Response(''))
    setFetch(fetchSpy)

    const client = await import('../client')
    const dispatched = client.dispatchPresenceLeave('/gallery', 'lease-123', 'client-1')

    expect(dispatched).toBe(true)
    expect(fetchSpy).toHaveBeenCalledTimes(1)
    const fetchCalls = fetchSpy.mock.calls as unknown[][]
    const fetchCall = fetchCalls[0]
    const init = fetchCall?.[1]
    expect(init).toMatchObject({
      method: 'POST',
      keepalive: true,
    })
  })
})
