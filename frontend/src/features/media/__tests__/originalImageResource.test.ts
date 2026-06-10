import { describe, expect, it } from 'vitest'
import { directOriginalImageUrl, isHttpOriginalUrl, originalMediaAllowsDirect } from '../originalImageResource'
import type { BrowseItemPayload, OriginalMediaPolicy } from '../../../lib/types'

const directPolicy: OriginalMediaPolicy = {
  mode: 'browser_direct_preferred_with_proxy_fallback',
  source_kind: 'http',
  proxy_available: true,
  direct_allowed_reason: 'test',
  redacted_origin: 'https://cdn.example.test/[redacted]',
  warnings: [],
}

function item(overrides: Partial<BrowseItemPayload>): BrowseItemPayload {
  return {
    path: '/a.jpg',
    name: 'a.jpg',
    mime: 'image/jpeg',
    width: 10,
    height: 10,
    size: 1,
    has_thumbnail: true,
    has_metadata: true,
    ...overrides,
  }
}

describe('original image resource policy', () => {
  it('accepts only http and https original URLs for direct browser display', () => {
    expect(isHttpOriginalUrl('https://cdn.example.test/a')).toBe(true)
    expect(isHttpOriginalUrl('http://cdn.example.test/a')).toBe(true)
    expect(isHttpOriginalUrl('s3://bucket/a.jpg')).toBe(false)
    expect(isHttpOriginalUrl('/file?path=%2Fa.jpg')).toBe(false)
  })

  it('uses direct HTTP originals by default and falls back when proxying is enabled', () => {
    const sourceItem = item({ source: 'https://cdn.example.test/a', original_media: directPolicy })

    expect(directOriginalImageUrl(sourceItem, false)).toBe('https://cdn.example.test/a')
    expect(directOriginalImageUrl(sourceItem, true)).toBeNull()
  })

  it('requires backend policy before direct browser handoff', () => {
    const sourceItem = item({ source: 'https://cdn.example.test/a' })

    expect(directOriginalImageUrl(sourceItem, false)).toBeNull()
    expect(originalMediaAllowsDirect({
      ...directPolicy,
      mode: 'backend_proxy_required',
    })).toBe(false)
  })

  it('prefers explicit URL over source when both are present', () => {
    const sourceItem = item({
      url: 'https://cdn.example.test/display',
      source: 'https://origin.example.test/source',
      original_media: directPolicy,
    })

    expect(directOriginalImageUrl(sourceItem, false)).toBe('https://cdn.example.test/display')
  })

  it('falls back after a per-item direct display failure', () => {
    const sourceItem = item({
      source: 'https://cdn.example.test/a',
      original_media: directPolicy,
    })

    expect(directOriginalImageUrl(sourceItem, false, new Set(['/a.jpg']))).toBeNull()
    expect(directOriginalImageUrl(sourceItem, false, (path) => path === '/a.jpg')).toBeNull()
  })
})
