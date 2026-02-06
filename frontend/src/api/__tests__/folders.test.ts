import { describe, expect, it } from 'vitest'
import { buildFolderQuery } from '../client'
import {
  folderQueryKey,
  shouldRemoveRecursiveFolderQuery,
  shouldRetainRecursiveFolderQuery,
} from '../folders'

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
    expect(folderQueryKey('/shots', { recursive: true, page: 1, pageSize: 200 })).toEqual(['folder', '/shots', 'recursive', 1, 200])
    expect(folderQueryKey('/shots', { recursive: true, page: 2, pageSize: 200 })).toEqual(['folder', '/shots', 'recursive', 2, 200])
    expect(folderQueryKey('/shots', { recursive: true, page: 1, pageSize: 300 })).toEqual(['folder', '/shots', 'recursive', 1, 300])
  })

  it('retains only current/root first-page recursive queries', () => {
    expect(shouldRetainRecursiveFolderQuery(['folder', '/shots', 'recursive', 1, 200], '/shots')).toBe(true)
    expect(shouldRetainRecursiveFolderQuery(['folder', '/', 'recursive', 1, 200], '/shots')).toBe(true)
    expect(shouldRetainRecursiveFolderQuery(['folder', '/other', 'recursive', 1, 200], '/shots')).toBe(false)
    expect(shouldRetainRecursiveFolderQuery(['folder', '/shots', 'recursive', 2, 200], '/shots')).toBe(false)
    expect(shouldRetainRecursiveFolderQuery(['folder', '/', 'recursive', 1, 200], '/shots', false)).toBe(false)
  })

  it('removes only stale recursive folder queries', () => {
    expect(shouldRemoveRecursiveFolderQuery(['folder', '/shots', 'recursive', 1, 200], '/shots')).toBe(false)
    expect(shouldRemoveRecursiveFolderQuery(['folder', '/other', 'recursive', 1, 200], '/shots')).toBe(true)
    expect(shouldRemoveRecursiveFolderQuery(['folder', '/shots'], '/shots')).toBe(false)
    expect(shouldRemoveRecursiveFolderQuery(['search', '/shots'], '/shots')).toBe(false)
    expect(shouldRemoveRecursiveFolderQuery('folder', '/shots')).toBe(false)
  })
})
