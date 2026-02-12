import { describe, expect, it } from 'vitest'
import type { FolderIndex, Item } from '../../../lib/types'
import {
  extractTopAnchorPath,
  invalidateFolderSession,
  invalidateIncompatibleScopeTransition,
  invalidateFolderSessionSubtree,
  isScopeTransitionCompatible,
  upsertFolderSessionSnapshot,
  upsertFolderSessionTopAnchor,
  type FolderSessionState,
} from '../useFolderSessionState'

function makeItem(path: string): Item {
  const name = path.split('/').pop() ?? path
  return {
    path,
    name,
    type: 'image/jpeg',
    w: 1,
    h: 1,
    size: 1,
    hasThumb: true,
    hasMeta: true,
  }
}

function makeFolder(path: string, itemPaths: string[], generatedAt = '2026-02-12T00:00:00Z'): FolderIndex {
  return {
    v: 1,
    path,
    generatedAt,
    dirs: [],
    items: itemPaths.map((itemPath) => makeItem(itemPath)),
    totalItems: itemPaths.length,
  }
}

describe('folder session state contracts', () => {
  it('records hydrated snapshot metadata and preserves top anchor across updates', () => {
    const firstSnapshot = makeFolder('/set', ['/set/a.jpg', '/set/b.jpg'], '2026-02-12T00:00:00Z')
    const secondSnapshot = makeFolder('/set', ['/set/a.jpg', '/set/b.jpg', '/set/c.jpg'], '2026-02-12T00:01:00Z')

    let state: FolderSessionState = {}
    state = upsertFolderSessionSnapshot(state, '/set', firstSnapshot, 100)
    state = upsertFolderSessionTopAnchor(state, '/set', '/set/b.jpg')
    state = upsertFolderSessionSnapshot(state, '/set', secondSnapshot, 200)

    expect(state['/set']).toEqual({
      path: '/set',
      hydratedSnapshot: secondSnapshot,
      hydratedGeneratedAt: '2026-02-12T00:01:00Z',
      hydratedItemCount: 3,
      hydratedAtMs: 200,
      topAnchorPath: '/set/b.jpg',
    })
  })

  it('extracts the first visible path as top anchor', () => {
    const visiblePaths = new Set<string>(['/set/first.jpg', '/set/second.jpg'])
    expect(extractTopAnchorPath(visiblePaths)).toBe('/set/first.jpg')
    expect(extractTopAnchorPath(new Set())).toBeNull()
  })

  it('invalidates one exact folder session without affecting siblings', () => {
    const setSnapshot = makeFolder('/set', ['/set/a.jpg'])
    const otherSnapshot = makeFolder('/other', ['/other/b.jpg'])
    let state: FolderSessionState = {}
    state = upsertFolderSessionSnapshot(state, '/set', setSnapshot, 100)
    state = upsertFolderSessionTopAnchor(state, '/set', '/set/a.jpg')
    state = upsertFolderSessionSnapshot(state, '/other', otherSnapshot, 110)

    const next = invalidateFolderSession(state, '/set')
    expect(next['/set']).toBeUndefined()
    expect(next['/other']).toBeDefined()
  })

  it('invalidates a subtree and keeps unrelated paths', () => {
    const rootSnapshot = makeFolder('/', ['/a.jpg'])
    const catsSnapshot = makeFolder('/cats', ['/cats/a.jpg'])
    const deepSnapshot = makeFolder('/cats/portraits', ['/cats/portraits/a.jpg'])
    const dogsSnapshot = makeFolder('/dogs', ['/dogs/a.jpg'])
    let state: FolderSessionState = {}
    state = upsertFolderSessionSnapshot(state, '/', rootSnapshot, 10)
    state = upsertFolderSessionSnapshot(state, '/cats', catsSnapshot, 20)
    state = upsertFolderSessionSnapshot(state, '/cats/portraits', deepSnapshot, 30)
    state = upsertFolderSessionSnapshot(state, '/dogs', dogsSnapshot, 40)

    const next = invalidateFolderSessionSubtree(state, '/cats')
    expect(next['/']).toBeDefined()
    expect(next['/dogs']).toBeDefined()
    expect(next['/cats']).toBeUndefined()
    expect(next['/cats/portraits']).toBeUndefined()
  })

  it('classifies scope transition compatibility by hierarchy', () => {
    expect(isScopeTransitionCompatible('/cats', '/cats/portraits')).toBe(true)
    expect(isScopeTransitionCompatible('/cats/portraits', '/cats')).toBe(true)
    expect(isScopeTransitionCompatible('/', '/dogs')).toBe(true)
    expect(isScopeTransitionCompatible('/cats', '/dogs')).toBe(false)
    expect(isScopeTransitionCompatible('/cats/portraits', '/dogs/portraits')).toBe(false)
  })

  it('invalidates target session state for incompatible scope transitions only', () => {
    const catsSnapshot = makeFolder('/cats', ['/cats/a.jpg'])
    const dogsSnapshot = makeFolder('/dogs', ['/dogs/a.jpg'])
    const dogsPupsSnapshot = makeFolder('/dogs/pups', ['/dogs/pups/a.jpg'])
    let state: FolderSessionState = {}
    state = upsertFolderSessionSnapshot(state, '/cats', catsSnapshot, 10)
    state = upsertFolderSessionSnapshot(state, '/dogs', dogsSnapshot, 20)
    state = upsertFolderSessionSnapshot(state, '/dogs/pups', dogsPupsSnapshot, 30)
    state = upsertFolderSessionTopAnchor(state, '/dogs', '/dogs/a.jpg')

    const incompatibleNext = invalidateIncompatibleScopeTransition(state, '/cats', '/dogs')
    expect(incompatibleNext['/cats']).toBeDefined()
    expect(incompatibleNext['/dogs']).toBeUndefined()
    expect(incompatibleNext['/dogs/pups']).toBeDefined()

    const compatibleNext = invalidateIncompatibleScopeTransition(state, '/dogs', '/dogs/pups')
    expect(compatibleNext).toBe(state)
  })
})
