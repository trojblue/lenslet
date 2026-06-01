import { describe, expect, it } from 'vitest'
import { resolveHashTargets } from '../hash'

describe('resolveHashTargets', () => {
  it('uses explicit viewer hashbang routes for extensionless image ids', () => {
    const path = '/img.metanomaly.co/r2/a2Vtb25vX2NodW5rXzAwMjc2JDg3MDkxMzUzNiQxNjIzNDY'

    expect(resolveHashTargets(`!${path}`)).toEqual({
      folderTarget: '/img.metanomaly.co/r2',
      imageTarget: path,
    })
  })

  it('keeps plain extensionless hashes as folder routes', () => {
    const path = '/img.metanomaly.co/r2'

    expect(resolveHashTargets(path)).toEqual({
      folderTarget: path,
      imageTarget: null,
    })
  })

  it('keeps loaded item paths as folder hashes unless the route uses hashbang', () => {
    const path = '/img.metanomaly.co/r2/extensionless-image-id'

    expect(resolveHashTargets(path)).toEqual({
      folderTarget: path,
      imageTarget: null,
    })
  })

  it('keeps plain extension-based hashes as folder routes', () => {
    expect(resolveHashTargets('/gallery/sample.webp')).toEqual({
      folderTarget: '/gallery/sample.webp',
      imageTarget: null,
    })
  })
})
