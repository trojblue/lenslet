import { describe, expect, it } from 'vitest'
import { buildFolderQuery } from '../client'
import {
  folderQueryKey,
  shouldRemoveRecursiveFolderQuery,
  shouldRetainRecursiveFolderQuery,
} from '../folders'

describe('folder api query helpers', () => {
  it('builds recursive query params', () => {
    const query = buildFolderQuery('/shots', { recursive: true })
    const params = new URLSearchParams(query)

    expect(params.get('path')).toBe('/shots')
    expect(params.get('recursive')).toBe('1')
    expect(params.get('page')).toBeNull()
    expect(params.get('page_size')).toBeNull()
  })

  it('does not emit retired legacy recursive params', () => {
    const query = buildFolderQuery('/shots', { recursive: true })
    const params = new URLSearchParams(query)

    expect(params.get('recursive')).toBe('1')
    expect(params.get('legacy_recursive')).toBeNull()
  })

  it('separates recursive cache keys from non-recursive', () => {
    expect(folderQueryKey('/shots', { recursive: true })).toEqual(['folder', '/shots', 'recursive'])
    expect(folderQueryKey('/shots', { recursive: false })).toEqual(['folder', '/shots'])
  })

  it('retains only current/root recursive queries', () => {
    expect(shouldRetainRecursiveFolderQuery(['folder', '/shots', 'recursive'], '/shots')).toBe(true)
    expect(shouldRetainRecursiveFolderQuery(['folder', '/', 'recursive'], '/shots')).toBe(true)
    expect(shouldRetainRecursiveFolderQuery(['folder', '/other', 'recursive'], '/shots')).toBe(false)
    expect(shouldRetainRecursiveFolderQuery(['folder', '/', 'recursive'], '/shots', false)).toBe(false)
  })

  it('removes only stale recursive folder queries', () => {
    expect(shouldRemoveRecursiveFolderQuery(['folder', '/shots', 'recursive'], '/shots')).toBe(false)
    expect(shouldRemoveRecursiveFolderQuery(['folder', '/other', 'recursive'], '/shots')).toBe(true)
    expect(shouldRemoveRecursiveFolderQuery(['folder', '/shots'], '/shots')).toBe(false)
    expect(shouldRemoveRecursiveFolderQuery(['search', '/shots'], '/shots')).toBe(false)
    expect(shouldRemoveRecursiveFolderQuery('folder', '/shots')).toBe(false)
  })
})
