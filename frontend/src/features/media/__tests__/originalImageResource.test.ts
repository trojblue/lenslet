import { describe, expect, it } from 'vitest'
import { directOriginalImageUrl, isHttpOriginalUrl } from '../originalImageResource'
import type { BrowseItemPayload } from '../../../lib/types'

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
    const sourceItem = item({ source: 'https://cdn.example.test/a' })

    expect(directOriginalImageUrl(sourceItem, false)).toBe('https://cdn.example.test/a')
    expect(directOriginalImageUrl(sourceItem, true)).toBeNull()
  })

  it('prefers explicit URL over source when both are present', () => {
    const sourceItem = item({
      url: 'https://cdn.example.test/display',
      source: 'https://origin.example.test/source',
    })

    expect(directOriginalImageUrl(sourceItem, false)).toBe('https://cdn.example.test/display')
  })
})
