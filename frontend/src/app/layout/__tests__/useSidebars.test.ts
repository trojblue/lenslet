import { describe, expect, it } from 'vitest'
import {
  SIDEBAR_STORAGE_KEYS,
  clampLeftSidebarWidth,
  clampRightSidebarWidth,
  getLeftSidebarStorageKey,
  persistSidebarWidth,
  readPersistedSidebarWidths,
} from '../useSidebars'

class MemoryStorage implements Pick<Storage, 'getItem' | 'setItem'> {
  private readonly data = new Map<string, string>()

  constructor(initial?: Record<string, string>) {
    if (!initial) return
    for (const [key, value] of Object.entries(initial)) {
      this.data.set(key, value)
    }
  }

  getItem(key: string): string | null {
    return this.data.get(key) ?? null
  }

  setItem(key: string, value: string): void {
    this.data.set(key, value)
  }
}

describe('useSidebars resize and persistence helpers', () => {
  it('loads persisted widths with folders fallback to the legacy key', () => {
    const storage = new MemoryStorage({
      [SIDEBAR_STORAGE_KEYS.leftLegacy]: '286',
      [SIDEBAR_STORAGE_KEYS.leftMetrics]: '341',
      [SIDEBAR_STORAGE_KEYS.right]: '299',
    })

    expect(readPersistedSidebarWidths(storage)).toEqual({
      leftFoldersW: 286,
      leftMetricsW: 341,
      rightW: 299,
    })
  })

  it('ignores invalid persisted values', () => {
    const storage = new MemoryStorage({
      [SIDEBAR_STORAGE_KEYS.leftFolders]: '-5',
      [SIDEBAR_STORAGE_KEYS.leftMetrics]: '0',
      [SIDEBAR_STORAGE_KEYS.right]: 'not-a-number',
    })

    expect(readPersistedSidebarWidths(storage)).toEqual({
      leftFoldersW: null,
      leftMetricsW: null,
      rightW: null,
    })
  })

  it('persists widths using side-specific storage keys', () => {
    const storage = new MemoryStorage()
    persistSidebarWidth(storage, getLeftSidebarStorageKey('folders'), 278.5)
    persistSidebarWidth(storage, getLeftSidebarStorageKey('metrics'), 332)
    persistSidebarWidth(storage, SIDEBAR_STORAGE_KEYS.right, 304)

    expect(storage.getItem(SIDEBAR_STORAGE_KEYS.leftFolders)).toBe('278.5')
    expect(storage.getItem(SIDEBAR_STORAGE_KEYS.leftMetrics)).toBe('332')
    expect(storage.getItem(SIDEBAR_STORAGE_KEYS.right)).toBe('304')
  })

  it('clamps left resize within min and center-preserving max bounds', () => {
    expect(
      clampLeftSidebarWidth({
        clientX: 120,
        appLeft: 100,
        appWidth: 1000,
        rightWidth: 300,
      }),
    ).toBe(200)

    expect(
      clampLeftSidebarWidth({
        clientX: 980,
        appLeft: 100,
        appWidth: 1000,
        rightWidth: 300,
      }),
    ).toBe(500)
  })

  it('clamps right resize within min and center-preserving max bounds', () => {
    expect(
      clampRightSidebarWidth({
        clientX: 950,
        appLeft: 100,
        appWidth: 1000,
        leftWidth: 260,
      }),
    ).toBe(240)

    expect(
      clampRightSidebarWidth({
        clientX: 150,
        appLeft: 100,
        appWidth: 1000,
        leftWidth: 260,
      }),
    ).toBe(540)
  })
})
