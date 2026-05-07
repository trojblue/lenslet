import { afterEach, describe, expect, it, vi } from 'vitest'
import {
  parseInspectorStoredBool,
  readInspectorStoredBool,
  readInspectorStoredValue,
  writeInspectorStoredBool,
  writeInspectorStoredJson,
} from '../inspectorStorage'

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

function setWindow(localStorage: Storage): void {
  Object.defineProperty(globalThis, 'window', {
    configurable: true,
    writable: true,
    value: { localStorage },
  })
}

afterEach(() => {
  vi.restoreAllMocks()
  delete (globalThis as { window?: unknown }).window
})

describe('inspectorStorage', () => {
  it('rewrites malformed stored payloads through the shared loader', () => {
    const storage = new MemoryStorage()
    storage.setItem('lenslet.inspector.sections', '{"legacy":true}')
    setWindow(storage)

    const result = readInspectorStoredValue(
      'lenslet.inspector.sections',
      () => ({
        value: ['compare', 'notes'],
        rewriteValue: '["compare","notes"]',
      }),
      [],
    )

    expect(result).toEqual(['compare', 'notes'])
    expect(storage.getItem('lenslet.inspector.sections')).toBe('["compare","notes"]')
  })

  it('handles boolean reads and writes without duplicating storage guards', () => {
    const storage = new MemoryStorage()
    storage.setItem('lenslet.inspector.metricsExpanded', 'true')
    setWindow(storage)

    expect(parseInspectorStoredBool('0', true)).toBe(false)
    expect(parseInspectorStoredBool('invalid', true)).toBe(true)
    expect(readInspectorStoredBool('lenslet.inspector.metricsExpanded', false)).toBe(true)

    writeInspectorStoredBool('lenslet.inspector.metricsExpanded', false)
    expect(storage.getItem('lenslet.inspector.metricsExpanded')).toBe('0')

    writeInspectorStoredJson('lenslet.inspector.quickView.paths', ['a', 'b'])
    expect(storage.getItem('lenslet.inspector.quickView.paths')).toBe('["a","b"]')
  })
})
