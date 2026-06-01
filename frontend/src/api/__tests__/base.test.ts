import { afterEach, describe, expect, it, vi } from 'vitest'
import { apiUrl } from '../base'

function setWindowLocation(origin: string, hostname: string): void {
  Object.defineProperty(globalThis, 'window', {
    configurable: true,
    writable: true,
    value: {
      location: {
        origin,
        hostname,
      },
    },
  })
}

afterEach(() => {
  vi.unstubAllEnvs()
  delete (globalThis as { window?: unknown }).window
})

describe('api base URL helpers', () => {
  it('computes urls from current runtime location on each call', () => {
    vi.stubEnv('VITE_API_BASE', 'http://localhost:7070')

    setWindowLocation('http://localhost:5173', 'localhost')
    expect(apiUrl('/health')).toBe('http://localhost:7070/health')

    setWindowLocation('https://shared.example.com', 'shared.example.com')
    expect(apiUrl('/health')).toBe('/health')
  })

  it('normalizes paths without a leading slash', () => {
    vi.stubEnv('VITE_API_BASE', '')

    expect(apiUrl('folders')).toBe('/folders')
  })
})
