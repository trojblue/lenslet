import { QueryClient } from '@tanstack/react-query'
import { describe, expect, it } from 'vitest'
import type { FolderIndex, Item, SearchResult } from '../../lib/types'
import {
  ItemQueryPathIndex,
  patchIndexedItemQueries,
} from '../model/appShellStateSync'

function makeItem(path: string, overrides: Partial<Item> = {}): Item {
  return {
    path,
    name: path.split('/').pop() ?? path,
    type: 'image/jpeg',
    w: 100,
    h: 100,
    size: 1,
    hasThumb: true,
    hasMeta: true,
    ...overrides,
  }
}

function makeFolder(path: string, items: Item[]): FolderIndex {
  return {
    v: 1,
    path,
    generatedAt: '2026-03-07T00:00:00Z',
    metricKeys: [],
    items,
    dirs: [],
  }
}

function makeSearch(items: Item[]): SearchResult {
  return { items }
}

describe('live update cache patching', () => {
  it('patches only folder/search queries that already contain the item path', () => {
    const queryClient = new QueryClient()
    const itemA = makeItem('/shots/a.jpg', { star: 1 })
    const itemB = makeItem('/shots/b.jpg', { star: 2 })
    const itemC = makeItem('/archive/c.jpg', { star: 3 })

    const folderShots = makeFolder('/shots', [itemA, itemB])
    const folderArchive = makeFolder('/archive', [itemC])
    const searchB = makeSearch([itemB])

    queryClient.setQueryData(['folder', '/shots'], folderShots)
    queryClient.setQueryData(['folder', '/archive'], folderArchive)
    queryClient.setQueryData(['search', 'b', '/'], searchB)

    const index = new ItemQueryPathIndex()
    index.seed(queryClient.getQueryCache().getAll())

    patchIndexedItemQueries(queryClient, index, {
      path: '/shots/b.jpg',
      star: 5,
      comments: 'fresh note',
    })

    const nextFolderShots = queryClient.getQueryData<FolderIndex>(['folder', '/shots'])
    const nextFolderArchive = queryClient.getQueryData<FolderIndex>(['folder', '/archive'])
    const nextSearchB = queryClient.getQueryData<SearchResult>(['search', 'b', '/'])

    expect(nextFolderShots).not.toBe(folderShots)
    expect(nextSearchB).not.toBe(searchB)
    expect(nextFolderArchive).toBe(folderArchive)
    expect(nextFolderShots?.items[1].star).toBe(5)
    expect(nextFolderShots?.items[1].comments).toBe('fresh note')
    expect(nextSearchB?.items[0].star).toBe(5)
    expect(nextSearchB?.items[0].comments).toBe('fresh note')
  })

  it('drops stale memberships after a query result set changes', () => {
    const queryClient = new QueryClient()
    queryClient.setQueryData(['search', 'shots', '/'], makeSearch([makeItem('/shots/a.jpg')]))

    const index = new ItemQueryPathIndex()
    index.seed(queryClient.getQueryCache().getAll())

    queryClient.setQueryData(['search', 'shots', '/'], makeSearch([makeItem('/shots/z.jpg')]))
    const updatedQuery = queryClient.getQueryCache().getAll()[0]
    index.syncQuery(updatedQuery)

    patchIndexedItemQueries(queryClient, index, {
      path: '/shots/a.jpg',
      star: 4,
    })

    const nextSearch = queryClient.getQueryData<SearchResult>(['search', 'shots', '/'])
    expect(nextSearch?.items[0].path).toBe('/shots/z.jpg')
    expect(nextSearch?.items[0].star).toBeUndefined()
  })
})
