import { describe, expect, it } from 'vitest'
import {
  SIDEBAR_STORAGE_KEYS,
  clampLeftSidebarWidth,
  clampRightSidebarWidth,
  persistSidebarWidth,
  readPersistedSidebarWidths,
} from '../useSidebars'

class MemoryStorage implements Pick<Storage, 'getItem' | 'setItem' | 'removeItem'> {
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

  removeItem(key: string): void {
    this.data.delete(key)
  }
}

describe('useSidebars resize and persistence helpers', () => {
  it('loads the shared and right widths while pruning obsolete left keys', () => {
    const storage = new MemoryStorage({
      [SIDEBAR_STORAGE_KEYS.left]: '341',
      [SIDEBAR_STORAGE_KEYS.right]: '299',
      'leftW.folders': '286',
      'leftW.metrics': '320',
      'leftW.derived': '520',
      leftW: '250',
    })

    expect(readPersistedSidebarWidths(storage)).toEqual({
      leftW: 341,
      rightW: 299,
    })
    expect(storage.getItem('leftW.folders')).toBeNull()
    expect(storage.getItem('leftW.metrics')).toBeNull()
    expect(storage.getItem('leftW.derived')).toBeNull()
    expect(storage.getItem('leftW')).toBeNull()
  })

  it('ignores invalid persisted values', () => {
    const storage = new MemoryStorage({
      [SIDEBAR_STORAGE_KEYS.left]: '-5',
      [SIDEBAR_STORAGE_KEYS.right]: 'not-a-number',
    })

    expect(readPersistedSidebarWidths(storage)).toEqual({
      leftW: null,
      rightW: null,
    })
  })

  it('persists shared and right widths independently', () => {
    const storage = new MemoryStorage()
    persistSidebarWidth(storage, SIDEBAR_STORAGE_KEYS.left, 332)
    persistSidebarWidth(storage, SIDEBAR_STORAGE_KEYS.right, 304)

    expect(storage.getItem(SIDEBAR_STORAGE_KEYS.left)).toBe('332')
    expect(storage.getItem(SIDEBAR_STORAGE_KEYS.right)).toBe('304')

    persistSidebarWidth(storage, SIDEBAR_STORAGE_KEYS.left, 360)
    expect(storage.getItem(SIDEBAR_STORAGE_KEYS.left)).toBe('360')
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
        leftWidth: 240,
        rightWidth: 300,
      }),
    ).toBe(280)
  })

  it('clamps right resize within min and center-preserving max bounds', () => {
    expect(
      clampRightSidebarWidth({
        clientX: 950,
        appLeft: 100,
        appWidth: 1000,
        leftWidth: 260,
        rightWidth: 300,
      }),
    ).toBe(280)

    expect(
      clampRightSidebarWidth({
        clientX: 150,
        appLeft: 100,
        appWidth: 1000,
        leftWidth: 260,
        rightWidth: 300,
      }),
    ).toBe(380)
  })

  it('allows wide right inspector drag targets on desktop while preserving center width', () => {
    expect(
      clampRightSidebarWidth({
        clientX: -20,
        appLeft: 0,
        appWidth: 1440,
        leftWidth: 240,
        rightWidth: 900,
      }),
    ).toBe(720)
  })

  it('does not return a preview width when the policy disables an impossible drag', () => {
    expect(
      clampLeftSidebarWidth({
        clientX: 300,
        appLeft: 0,
        appWidth: 320,
        leftWidth: 760,
        rightWidth: 300,
        userRightOpen: false,
      }),
    ).toBe(0)
  })
})
