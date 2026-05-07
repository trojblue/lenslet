import { describe, expect, it } from 'vitest'
import {
  getBrowserZoomWarningBucket,
  resolveScopeFromHashTarget,
  resolveVisibleBrowserZoomPercent,
} from '../utils/appShellHelpers'

describe('resolveScopeFromHashTarget', () => {
  it('uses the image folder on initial hash sync', () => {
    expect(resolveScopeFromHashTarget('/', '/parent/child', '/parent/child/a.jpg', true)).toBe('/parent/child')
  })

  it('keeps current scope when image is inside it after initial sync', () => {
    expect(resolveScopeFromHashTarget('/parent', '/parent/child', '/parent/child/a.jpg', false)).toBe('/parent')
  })

  it('keeps root scope when already browsing root', () => {
    expect(resolveScopeFromHashTarget('/', '/parent/child', '/parent/child/a.jpg', false)).toBe('/')
  })

  it('switches to target folder when image is outside current scope', () => {
    expect(resolveScopeFromHashTarget('/other', '/parent/child', '/parent/child/a.jpg', false)).toBe('/parent/child')
  })

  it('uses folder target for non-image hashes', () => {
    expect(resolveScopeFromHashTarget('/parent', '/parent/child', null, false)).toBe('/parent/child')
  })
})

describe('browser zoom warning helpers', () => {
  it('does not warn at effective 100% zoom', () => {
    expect(getBrowserZoomWarningBucket(null)).toBe(null)
    expect(getBrowserZoomWarningBucket(100)).toBe(null)
    expect(getBrowserZoomWarningBucket(101)).toBe(null)
    expect(resolveVisibleBrowserZoomPercent(101, null)).toBe(null)
  })

  it('keeps dismissal stable across measurement jitter', () => {
    const dismissedBucket = getBrowserZoomWarningBucket(110)

    expect(resolveVisibleBrowserZoomPercent(110, dismissedBucket)).toBe(null)
    expect(resolveVisibleBrowserZoomPercent(111, dismissedBucket)).toBe(null)
    expect(resolveVisibleBrowserZoomPercent(113, dismissedBucket)).toBe(113)
  })
})
