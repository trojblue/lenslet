import { QueryClient } from '@tanstack/react-query'
import { describe, expect, it } from 'vitest'
import type { BrowseFolderPayload, BrowseItemPayload, BrowseSearchResultsPayload } from '../../lib/types'
import {
  ItemQueryPathIndex,
  patchIndexedItemQueries,
} from '../model/appShellStateSync'

function makeItem(path: string, overrides: Partial<BrowseItemPayload> = {}): BrowseItemPayload {
  return {
    path,
    name: path.split('/').pop() ?? path,
    mime: 'image/jpeg',
    width: 100,
    height: 100,
    size: 1,
    has_thumbnail: true,
    has_metadata: true,
    ...overrides,
  }
}

function makeFolder(path: string, items: BrowseItemPayload[]): BrowseFolderPayload {
  return {
    version: 1,
    path,
    generated_at: '2026-03-07T00:00:00Z',
    metric_keys: [],
    categorical_keys: [],
    items,
    folders: [],
  }
}

function makeSearch(items: BrowseItemPayload[]): BrowseSearchResultsPayload {
  return { items }
}

function makeBrowseQueryPages(items: BrowseItemPayload[]) {
  return {
    pages: [{
      version: 1,
      path: '/shots',
      generated_at: '2026-03-07T00:00:00Z',
      generation_token: 'gen',
      request_token: 'req',
      scope_total: items.length,
      filtered_total: items.length,
      offset: 0,
      limit: 1000,
      items,
      folders: [],
      metric_keys: [],
      categorical_keys: [],
      dependency_manifest: {
        fields: ['added_at'],
        metric_keys: [],
        categorical_keys: [],
        unknown: false,
      },
    }],
    pageParams: [0],
  }
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
      notes: 'fresh note',
    })

    const nextFolderShots = queryClient.getQueryData<BrowseFolderPayload>(['folder', '/shots'])
    const nextFolderArchive = queryClient.getQueryData<BrowseFolderPayload>(['folder', '/archive'])
    const nextSearchB = queryClient.getQueryData<BrowseSearchResultsPayload>(['search', 'b', '/'])

    expect(nextFolderShots).not.toBe(folderShots)
    expect(nextSearchB).not.toBe(searchB)
    expect(nextFolderArchive).toBe(folderArchive)
    expect(nextFolderShots?.items[1].star).toBe(5)
    expect(nextFolderShots?.items[1].notes).toBe('fresh note')
    expect(nextSearchB?.items[0].star).toBe(5)
    expect(nextSearchB?.items[0].notes).toBe('fresh note')
  })

  it('patches paged backend browse-query results that contain the item path', () => {
    const queryClient = new QueryClient()
    const itemA = makeItem('/shots/a.jpg', { star: 1 })
    const itemB = makeItem('/shots/b.jpg', { star: 2 })
    const queryKey = [
      'folder-query',
      [
        'analysis-query',
        '/shots',
        'recursive',
        { and: [] },
        { kind: 'builtin', key: 'added', dir: 'desc' },
        '',
        null,
        null,
        null,
      ],
      0,
      1000,
      null,
    ]
    const browseQuery = makeBrowseQueryPages([itemA, itemB])

    queryClient.setQueryData(queryKey, browseQuery)

    const index = new ItemQueryPathIndex()
    index.seed(queryClient.getQueryCache().getAll())

    patchIndexedItemQueries(queryClient, index, {
      path: '/shots/b.jpg',
      star: 5,
      notes: 'backend note',
    })

    const nextBrowseQuery = queryClient.getQueryData<typeof browseQuery>(queryKey)
    expect(nextBrowseQuery).not.toBe(browseQuery)
    expect(nextBrowseQuery?.pages[0].items[1].star).toBe(5)
    expect(nextBrowseQuery?.pages[0].items[1].notes).toBe('backend note')
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

    const nextSearch = queryClient.getQueryData<BrowseSearchResultsPayload>(['search', 'shots', '/'])
    expect(nextSearch?.items[0].path).toBe('/shots/z.jpg')
    expect(nextSearch?.items[0].star).toBeUndefined()
  })

  it('removes a loaded item that conclusively fails the active star filter', () => {
    const queryClient = new QueryClient()
    const queryKey = [
      'folder-query',
      [
        'analysis-query',
        '/shots',
        'recursive',
        { and: [{ starsIn: { values: [0] } }] },
        { kind: 'builtin', key: 'added', dir: 'desc' },
        '',
        null,
        null,
        null,
      ],
      0,
      1000,
      null,
    ]
    queryClient.setQueryData(queryKey, makeBrowseQueryPages([
      makeItem('/shots/unrated.jpg', { star: null }),
      makeItem('/shots/unrelated.jpg', { star: 1 }),
    ]))
    const index = new ItemQueryPathIndex()
    index.seed(queryClient.getQueryCache().getAll())

    patchIndexedItemQueries(
      queryClient,
      index,
      { path: '/shots/unrated.jpg', star: 1 },
      { removeConclusiveFilterMismatch: true },
    )

    const next = queryClient.getQueryData<ReturnType<typeof makeBrowseQueryPages>>(queryKey)
    expect(next?.pages[0].items.map((item) => item.path)).toEqual(['/shots/unrelated.jpg'])
    expect(next?.pages[0].filtered_total).toBe(1)
  })
})
