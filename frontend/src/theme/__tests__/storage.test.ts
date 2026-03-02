import { afterEach, describe, expect, it } from 'vitest'
import {
  buildWorkspaceThemeStorageKey,
  loadWorkspaceThemePreset,
  readStoredThemePreset,
  writeStoredThemePreset,
} from '../storage'

class MemoryStorage implements Storage {
  private store = new Map<string, string>()

  get length(): number {
    return this.store.size
  }

  clear(): void {
    this.store.clear()
  }

  getItem(key: string): string | null {
    return this.store.get(key) ?? null
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

function installWindow(localStorage: Storage): void {
  Object.defineProperty(globalThis, 'window', {
    configurable: true,
    writable: true,
    value: {
      localStorage,
      location: {
        origin: 'http://127.0.0.1:7070',
        pathname: '/',
      },
    },
  })
}

afterEach(() => {
  delete (globalThis as { window?: unknown }).window
})

describe('workspace theme storage keys', () => {
  it('uses hashed workspace key shape with no raw path leakage', () => {
    const key = buildWorkspaceThemeStorageKey('workspace:/private/datasets/demo', 'memory')
    expect(key).toMatch(/^lenslet\.v2\.theme\.[0-9a-f]{16}$/)
    expect(key).not.toContain('/private/datasets/demo')
  })

  it('is stable for same workspace and distinct across workspaces', () => {
    const keyA = buildWorkspaceThemeStorageKey('workspace-alpha', 'table')
    const keyARepeat = buildWorkspaceThemeStorageKey('workspace-alpha', 'table')
    const keyB = buildWorkspaceThemeStorageKey('workspace-beta', 'table')
    expect(keyA).toBe(keyARepeat)
    expect(keyA).not.toBe(keyB)
  })

  it('falls back to deterministic mode+location seed when workspace id is absent', () => {
    const keyA = buildWorkspaceThemeStorageKey(null, 'dataset', 'http://127.0.0.1:7070/gallery')
    const keyB = buildWorkspaceThemeStorageKey(undefined, 'dataset', 'http://127.0.0.1:7070/gallery')
    const keyC = buildWorkspaceThemeStorageKey(undefined, 'memory', 'http://127.0.0.1:7070/gallery')
    expect(keyA).toBe(keyB)
    expect(keyA).not.toBe(keyC)
  })
})

describe('workspace theme storage read/write', () => {
  it('stores and reads preset per workspace key', () => {
    const storage = new MemoryStorage()
    installWindow(storage)

    writeStoredThemePreset('workspace-alpha', 'memory', 'teal')
    expect(readStoredThemePreset('workspace-alpha', 'memory')).toBe('teal')
    expect(loadWorkspaceThemePreset('workspace-alpha', 'memory')).toBe('teal')
  })

  it('defaults to default preset when no value is persisted', () => {
    installWindow(new MemoryStorage())
    expect(loadWorkspaceThemePreset('workspace-alpha', 'memory')).toBe('default')
  })
})
