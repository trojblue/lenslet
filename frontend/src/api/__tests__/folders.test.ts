import { describe, expect, it } from 'vitest'
import { buildFolderQuery } from '../client'
import { folderQueryKey } from '../folders'

describe('folder api query helpers', () => {
  it('builds recursive query params with pagination', () => {
    const query = buildFolderQuery('/shots', { recursive: true, page: 2, pageSize: 250 })
    const params = new URLSearchParams(query)

    expect(params.get('path')).toBe('/shots')
    expect(params.get('recursive')).toBe('1')
    expect(params.get('page')).toBe('2')
    expect(params.get('page_size')).toBe('250')
  })

  it('adds legacy recursive mode when requested', () => {
    const query = buildFolderQuery('/shots', { recursive: true, legacyRecursive: true })
    const params = new URLSearchParams(query)

    expect(params.get('recursive')).toBe('1')
    expect(params.get('legacy_recursive')).toBe('1')
  })

  it('separates recursive cache keys by page and page size', () => {
    expect(folderQueryKey('/shots', true, 1, 200)).toEqual(['folder', '/shots', 'recursive', 1, 200])
    expect(folderQueryKey('/shots', true, 2, 200)).toEqual(['folder', '/shots', 'recursive', 2, 200])
    expect(folderQueryKey('/shots', true, 1, 300)).toEqual(['folder', '/shots', 'recursive', 1, 300])
  })
})
