import { describe, expect, it } from 'vitest'
import {
  buildCanonicalSearchRequest,
  normalizeSearchQuery,
  normalizeSearchScopePath,
  searchQueryKey,
  shouldKeepSearchPlaceholderData,
} from '../search'

describe('search api contract helpers', () => {
  it('normalizes source-token queries and canonicalizes root scope', () => {
    const request = buildCanonicalSearchRequest('  source:pixiv   artist:foo  ', '   ')
    expect(request).toEqual({
      q: 'source:pixiv artist:foo',
      path: '/',
    })
  })

  it('canonicalizes non-root scope paths and rejects blank queries', () => {
    expect(normalizeSearchScopePath('shots/subset')).toBe('/shots/subset')
    expect(buildCanonicalSearchRequest('   ', '/shots')).toBeNull()
  })

  it('keeps placeholder results stable for source-token searches within the same scope', () => {
    const previousKey = searchQueryKey('source:pixiv artist:foo', '/shots')
    const nextRequest = buildCanonicalSearchRequest('source:pixiv   artist:bar', '/shots')
    expect(shouldKeepSearchPlaceholderData(previousKey, nextRequest)).toBe(true)
  })

  it('drops placeholder results when scope changes to avoid stale cross-folder rendering', () => {
    const previousKey = searchQueryKey('source:pixiv', '/shots')
    const nextRequest = buildCanonicalSearchRequest('source:pixiv', '/other')
    expect(shouldKeepSearchPlaceholderData(previousKey, nextRequest)).toBe(false)
  })

  it('normalizes repeated whitespace in token queries', () => {
    expect(normalizeSearchQuery('  source:foo    url:bar   ')).toBe('source:foo url:bar')
  })
})
