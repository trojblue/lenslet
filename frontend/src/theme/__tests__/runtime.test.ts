import { describe, expect, it } from 'vitest'
import { applyThemePreset, buildThemedFaviconHref } from '../runtime'

const DYNAMIC_FAVICON_ATTR = 'data-lenslet-dynamic-favicon'
const DYNAMIC_FAVICON_SELECTOR = `link[${DYNAMIC_FAVICON_ATTR}="1"]`

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
  links: HTMLLinkElement[]
  getRootAttribute: (name: string) => string | null
  getRootToken: (token: string) => string
} {
  const links: HTMLLinkElement[] = []
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
        links.push(link)
        return node
      },
    },
    createElement: (_tag: string) => createFakeLink(),
  } as unknown as Document

  return {
    doc,
    links,
    getRootAttribute: (name: string) => rootAttrs.get(name) ?? null,
    getRootToken: (token: string) => styleValues.get(token) ?? '',
  }
}

describe('theme runtime apply contracts', () => {
  it('applies preset tokens and remains idempotent on repeated apply', () => {
    const fake = createFakeDocument()

    applyThemePreset('teal', fake.doc)
    applyThemePreset('teal', fake.doc)

    expect(fake.getRootAttribute('data-lenslet-theme')).toBe('teal')
    expect(fake.getRootToken('--accent')).toBe('#2dd4bf')
    expect(fake.links).toHaveLength(1)
  })

  it('updates favicon href when accent changes between presets', () => {
    const fake = createFakeDocument()

    applyThemePreset('teal', fake.doc)
    const firstHref = fake.links[0]?.getAttribute('href')
    applyThemePreset('charcoal', fake.doc)
    const secondHref = fake.links[0]?.getAttribute('href')

    expect(fake.links).toHaveLength(1)
    expect(firstHref).not.toEqual(secondHref)
    expect(secondHref).toContain(encodeURIComponent('#86b7ff'))
  })

  it('builds deterministic themed favicon href from accent color', () => {
    const first = buildThemedFaviconHref('#2dd4bf')
    const second = buildThemedFaviconHref('#2dd4bf')
    expect(first).toBe(second)
    expect(first).toContain('data:image/svg+xml,')
  })
})
