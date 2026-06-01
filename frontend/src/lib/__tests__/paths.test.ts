import { describe, expect, it } from 'vitest'
import { joinPath, sanitizePath } from '../paths'

describe('path utilities', () => {
  it('normalizes safe gallery paths', () => {
    expect(sanitizePath('gallery//cats/')).toBe('/gallery/cats')
    expect(sanitizePath('/gallery/@owner/item.png')).toBe('/gallery/@owner/item.png')
  })

  it('falls back to root for unsafe paths', () => {
    expect(sanitizePath('/gallery/space name.png')).toBe('/')
    expect(sanitizePath('%E0%A4%A')).toBe('/')
  })

  it('joins path segments with one leading slash', () => {
    expect(joinPath('/', 'cats')).toBe('/cats')
    expect(joinPath('/gallery/', '/cats')).toBe('/gallery/cats')
  })
})
