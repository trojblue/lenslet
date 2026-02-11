import { describe, expect, it } from 'vitest'
import type { FolderIndex, Item } from '../../../../lib/types'
import { getRemainingPagesPlan, hydrateFolderPages, mergeFolderPages, normalizeFolderPage } from '../pagedFolder'

function makeItem(path: string): Item {
  const name = path.split('/').pop() || path
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

function makeFolder(path: string, itemPaths: string[], overrides?: Partial<FolderIndex>): FolderIndex {
  return {
    v: 1,
    path,
    generatedAt: '2026-02-06T00:00:00Z',
    dirs: [],
    items: itemPaths.map((itemPath) => makeItem(itemPath)),
    ...overrides,
  }
}

describe('paged folder merge', () => {
  it('normalizes duplicate items within a page', () => {
    const page = makeFolder('/set', ['/set/a.jpg', '/set/a.jpg', '/set/b.jpg'])
    const normalized = normalizeFolderPage(page)
    expect(normalized.items.map((item) => item.path)).toEqual(['/set/a.jpg', '/set/b.jpg'])
  })

  it('merges pages without duplicates and keeps stable order', () => {
    const first = makeFolder('/set', ['/set/a.jpg', '/set/b.jpg'], {
      page: 1,
      pageSize: 2,
      pageCount: 2,
      totalItems: 4,
    })
    const second = makeFolder('/set', ['/set/b.jpg', '/set/c.jpg', '/set/d.jpg'], {
      page: 2,
      pageSize: 2,
      pageCount: 2,
      totalItems: 4,
    })

    const merged = mergeFolderPages(first, second)
    expect(merged.items.map((item) => item.path)).toEqual([
      '/set/a.jpg',
      '/set/b.jpg',
      '/set/c.jpg',
      '/set/d.jpg',
    ])
    expect(merged.page).toBe(2)
    expect(merged.pageSize).toBe(2)
    expect(merged.pageCount).toBe(2)
    expect(merged.totalItems).toBe(4)
  })

  it('resets when a later response points to a different path', () => {
    const first = makeFolder('/set-a', ['/set-a/a.jpg'])
    const second = makeFolder('/set-b', ['/set-b/b.jpg'])
    const merged = mergeFolderPages(first, second)
    expect(merged.path).toBe('/set-b')
    expect(merged.items.map((item) => item.path)).toEqual(['/set-b/b.jpg'])
  })

  it('computes remaining pages from first page metadata', () => {
    const first = makeFolder('/set', ['/set/a.jpg'], {
      page: 1,
      pageSize: 2,
      pageCount: 3,
      totalItems: 5,
    })
    expect(getRemainingPagesPlan(first, 200)).toEqual({
      startPage: 2,
      endPage: 3,
      pageSize: 2,
    })
  })

  it('hydrates and merges paged folder responses', async () => {
    const first = makeFolder('/set', ['/set/a.jpg', '/set/b.jpg'], {
      page: 1,
      pageSize: 2,
      pageCount: 2,
      totalItems: 3,
    })
    const second = makeFolder('/set', ['/set/b.jpg', '/set/c.jpg'], {
      page: 2,
      pageSize: 2,
      pageCount: 2,
      totalItems: 3,
    })

    const snapshots: FolderIndex[] = []
    await hydrateFolderPages(first, {
      defaultPageSize: 200,
      fetchPage: async (page) => {
        if (page === 2) return second
        throw new Error(`unexpected page: ${page}`)
      },
      onUpdate: (value) => {
        snapshots.push(value)
      },
    })

    expect(snapshots).toHaveLength(2)
    expect(snapshots[0].items.map((item) => item.path)).toEqual(['/set/a.jpg', '/set/b.jpg'])
    expect(snapshots[1].items.map((item) => item.path)).toEqual(['/set/a.jpg', '/set/b.jpg', '/set/c.jpg'])
  })

  it('can defer intermediate updates until hydration completes', async () => {
    const first = makeFolder('/set', ['/set/a.jpg'], {
      page: 1,
      pageSize: 1,
      pageCount: 3,
      totalItems: 3,
    })
    const second = makeFolder('/set', ['/set/b.jpg'], {
      page: 2,
      pageSize: 1,
      pageCount: 3,
      totalItems: 3,
    })
    const third = makeFolder('/set', ['/set/c.jpg'], {
      page: 3,
      pageSize: 1,
      pageCount: 3,
      totalItems: 3,
    })

    const snapshots: FolderIndex[] = []
    await hydrateFolderPages(first, {
      defaultPageSize: 200,
      progressiveUpdates: false,
      fetchPage: async (page) => {
        if (page === 2) return second
        if (page === 3) return third
        throw new Error(`unexpected page: ${page}`)
      },
      onUpdate: (value) => {
        snapshots.push(value)
      },
    })

    expect(snapshots).toHaveLength(2)
    expect(snapshots[0].items.map((item) => item.path)).toEqual(['/set/a.jpg'])
    expect(snapshots[1].items.map((item) => item.path)).toEqual(['/set/a.jpg', '/set/b.jpg', '/set/c.jpg'])
  })
})
