import { describe, expect, it } from 'vitest'
import { resolveScopeFromHashTarget } from '../utils/appShellHelpers'

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
