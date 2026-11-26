import { describe, expect, it } from 'vitest'
import { joinPath, sanitizePath } from '../paths'

describe('path utilities', () => {
  it('normalizes safe gallery paths', () => {
    expect(sanitizePath('gallery//cats/')).toBe('/gallery/cats')
    expect(sanitizePath('/gallery/@owner/item.png')).toBe('/gallery/@owner/item.png')
  })

  it('preserves Unicode names and spaces in folder paths and URL hashes', () => {
    const path = '/3 高/アニメ/한글/画面.webp'
    expect(sanitizePath(path)).toBe(path)
    expect(sanitizePath(encodeURI(path))).toBe(path)
  })

  it.each(['1.50–1.75', 'score—high', '画面－高'])('preserves Unicode dashes in %s', (name) => {
    const path = `/${name}`
    expect(sanitizePath(path)).toBe(path)
    expect(sanitizePath(encodeURI(path))).toBe(path)
  })

  it('falls back to root for unsafe paths', () => {
    expect(sanitizePath('/gallery/line\nbreak')).toBe('/')
    expect(sanitizePath('%E0%A4%A')).toBe('/')
  })

  it('joins path segments with one leading slash', () => {
    expect(joinPath('/', 'cats')).toBe('/cats')
    expect(joinPath('/gallery/', '/cats')).toBe('/gallery/cats')
  })
})
