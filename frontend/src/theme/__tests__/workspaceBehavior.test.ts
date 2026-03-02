import { afterEach, describe, expect, it } from 'vitest'
import { applyThemePreset } from '../runtime'
import { loadWorkspaceThemePreset, writeStoredThemePreset } from '../storage'

const DYNAMIC_FAVICON_ATTR = 'data-lenslet-dynamic-favicon'
const DYNAMIC_FAVICON_SELECTOR = `link[${DYNAMIC_FAVICON_ATTR}="1"]`

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

type FakeLink = {
  attrs: Map<string, string>
  setAttribute: (name: string, value: string) => void
  getAttribute: (name: string) => string | null
}

function createFakeLink(): HTMLLinkElement {
  const attrs = new Map<string, string>()
  const link: FakeLink = {
    attrs,
    setAttribute: (name: string, value: string) => {
      attrs.set(name, value)
    },
    getAttribute: (name: string) => attrs.get(name) ?? null,
  }
  return link as unknown as HTMLLinkElement
}

function createFakeDocument(): {
  doc: Document
  getRootAttribute: (name: string) => string | null
  getRootToken: (token: string) => string
  getFaviconHref: () => string | null
} {
  const rootAttrs = new Map<string, string>()
  const styleValues = new Map<string, string>()
  let dynamicLink: HTMLLinkElement | null = null

  const doc = {
    documentElement: {
      style: {
        setProperty: (name: string, value: string) => {
          styleValues.set(name, value)
        },
        getPropertyValue: (name: string) => styleValues.get(name) ?? '',
      },
      setAttribute: (name: string, value: string) => {
        rootAttrs.set(name, value)
      },
    },
    head: {
      querySelector: (selector: string) => {
        if (selector !== DYNAMIC_FAVICON_SELECTOR) return null
        return dynamicLink
      },
      appendChild: (node: unknown) => {
        const link = node as HTMLLinkElement
        dynamicLink = link
        return node
      },
    },
    createElement: (_tag: string) => createFakeLink(),
  } as unknown as Document

  return {
    doc,
    getRootAttribute: (name: string) => rootAttrs.get(name) ?? null,
    getRootToken: (token: string) => styleValues.get(token) ?? '',
    getFaviconHref: () => dynamicLink?.getAttribute('href') ?? null,
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

describe('workspace theme selection behavior', () => {
  it('persists and applies distinct themes across workspaces with distinct favicons', () => {
    installWindow(new MemoryStorage())

    writeStoredThemePreset('workspace-a', 'memory', 'teal')
    writeStoredThemePreset('workspace-b', 'memory', 'charcoal')

    const aDoc = createFakeDocument()
    const bDoc = createFakeDocument()

    const themeA = loadWorkspaceThemePreset('workspace-a', 'memory')
    const themeB = loadWorkspaceThemePreset('workspace-b', 'memory')

    applyThemePreset(themeA, aDoc.doc)
    applyThemePreset(themeB, bDoc.doc)

    expect(themeA).toBe('teal')
    expect(themeB).toBe('charcoal')
    expect(aDoc.getRootAttribute('data-lenslet-theme')).toBe('teal')
    expect(bDoc.getRootAttribute('data-lenslet-theme')).toBe('charcoal')
    expect(aDoc.getFaviconHref()).not.toEqual(bDoc.getFaviconHref())
  })

  it('keeps default theme behavior when workspace has no persisted selection', () => {
    installWindow(new MemoryStorage())

    const doc = createFakeDocument()
    const themeId = loadWorkspaceThemePreset('workspace-fresh', 'dataset')
    applyThemePreset(themeId, doc.doc)

    expect(themeId).toBe('default')
    expect(doc.getRootAttribute('data-lenslet-theme')).toBe('default')
    expect(doc.getRootToken('--accent')).toBe('#3b82f6')
  })
})
