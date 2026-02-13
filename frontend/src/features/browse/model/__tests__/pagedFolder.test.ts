import { describe, expect, it } from 'vitest'
import type { FolderIndex, Item } from '../../../../lib/types'
import {
  getRemainingPagesPlan,
  hydrateFolderPages,
  mergeFolderPages,
  normalizeFolderPage,
  type FolderHydrationProgress,
} from '../pagedFolder'

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

function createDeferred<T>() {
  let resolve!: (value: T) => void
  let reject!: (reason?: unknown) => void
  const promise = new Promise<T>((res, rej) => {
    resolve = res
    reject = rej
  })
  return { promise, resolve, reject }
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

  it('throttles progressive updates while preserving the final merged snapshot', async () => {
    const first = makeFolder('/set', ['/set/a.jpg'], {
      page: 1,
      pageSize: 1,
      pageCount: 4,
      totalItems: 4,
    })
    const second = makeFolder('/set', ['/set/b.jpg'], {
      page: 2,
      pageSize: 1,
      pageCount: 4,
      totalItems: 4,
    })
    const third = makeFolder('/set', ['/set/c.jpg'], {
      page: 3,
      pageSize: 1,
      pageCount: 4,
      totalItems: 4,
    })
    const fourth = makeFolder('/set', ['/set/d.jpg'], {
      page: 4,
      pageSize: 1,
      pageCount: 4,
      totalItems: 4,
    })

    const snapshots: FolderIndex[] = []
    await hydrateFolderPages(first, {
      defaultPageSize: 200,
      progressiveUpdates: true,
      progressiveUpdateIntervalMs: 60_000,
      fetchPage: async (page) => {
        if (page === 2) return second
        if (page === 3) return third
        if (page === 4) return fourth
        throw new Error(`unexpected page: ${page}`)
      },
      onUpdate: (value) => {
        snapshots.push(value)
      },
    })

    expect(snapshots).toHaveLength(2)
    expect(snapshots[0].items.map((item) => item.path)).toEqual(['/set/a.jpg'])
    expect(snapshots[1].items.map((item) => item.path)).toEqual([
      '/set/a.jpg',
      '/set/b.jpg',
      '/set/c.jpg',
      '/set/d.jpg',
    ])
  })

  it('supports cache-first two-phase hydration when paged data is still loading', async () => {
    const cached = makeFolder('/set', ['/set/a.jpg', '/set/b.jpg', '/set/c.jpg'], {
      page: 2,
      pageSize: 2,
      pageCount: 2,
      totalItems: 3,
      generatedAt: '2026-02-06T00:00:00Z',
    })
    const first = makeFolder('/set', ['/set/new.jpg', '/set/a.jpg'], {
      page: 1,
      pageSize: 2,
      pageCount: 2,
      totalItems: 4,
      generatedAt: '2026-02-06T00:01:00Z',
    })
    const second = makeFolder('/set', ['/set/b.jpg', '/set/d.jpg'], {
      page: 2,
      pageSize: 2,
      pageCount: 2,
      totalItems: 4,
      generatedAt: '2026-02-06T00:01:00Z',
    })

    const snapshots: FolderIndex[] = [cached]
    await hydrateFolderPages(first, {
      defaultPageSize: 200,
      progressiveUpdates: false,
      skipInitialUpdateIfPaged: true,
      fetchPage: async (page) => {
        if (page === 2) return second
        throw new Error(`unexpected page: ${page}`)
      },
      onUpdate: (value) => {
        snapshots.push(value)
      },
    })

    expect(snapshots).toHaveLength(2)
    expect(snapshots[0].items.map((item) => item.path)).toEqual(['/set/a.jpg', '/set/b.jpg', '/set/c.jpg'])
    expect(snapshots[1].items.map((item) => item.path)).toEqual([
      '/set/new.jpg',
      '/set/a.jpg',
      '/set/b.jpg',
      '/set/d.jpg',
    ])
  })

  it('still emits first page when cache-first mode is enabled without extra pages', async () => {
    const first = makeFolder('/set', ['/set/a.jpg', '/set/b.jpg'], {
      page: 1,
      pageSize: 2,
      pageCount: 1,
      totalItems: 2,
    })

    const snapshots: FolderIndex[] = []
    await hydrateFolderPages(first, {
      defaultPageSize: 200,
      progressiveUpdates: false,
      skipInitialUpdateIfPaged: true,
      fetchPage: async () => {
        throw new Error('unexpected fetchPage call')
      },
      onUpdate: (value) => {
        snapshots.push(value)
      },
    })

    expect(snapshots).toHaveLength(1)
    expect(snapshots[0].items.map((item) => item.path)).toEqual(['/set/a.jpg', '/set/b.jpg'])
  })

  it('keeps cached anchor items stable while late pages hydrate', async () => {
    const anchorPath = '/set/c.jpg'
    const cached = makeFolder('/set', ['/set/a.jpg', '/set/b.jpg', anchorPath], {
      page: 2,
      pageSize: 2,
      pageCount: 2,
      totalItems: 3,
      generatedAt: '2026-02-06T00:00:00Z',
    })
    const first = makeFolder('/set', ['/set/new.jpg', '/set/a.jpg'], {
      page: 1,
      pageSize: 2,
      pageCount: 2,
      totalItems: 4,
      generatedAt: '2026-02-06T00:01:00Z',
    })
    const second = makeFolder('/set', ['/set/b.jpg', anchorPath, '/set/d.jpg'], {
      page: 2,
      pageSize: 2,
      pageCount: 2,
      totalItems: 4,
      generatedAt: '2026-02-06T00:01:00Z',
    })

    const delayedPage = createDeferred<FolderIndex>()
    const snapshots: FolderIndex[] = [cached]
    const hydration = hydrateFolderPages(first, {
      defaultPageSize: 200,
      progressiveUpdates: false,
      skipInitialUpdateIfPaged: true,
      fetchPage: async (page) => {
        if (page !== 2) throw new Error(`unexpected page: ${page}`)
        return delayedPage.promise
      },
      onUpdate: (value) => {
        snapshots.push(value)
      },
    })

    await Promise.resolve()
    expect(snapshots).toHaveLength(1)
    expect(snapshots[0].items.some((item) => item.path === anchorPath)).toBe(true)

    delayedPage.resolve(second)
    await hydration

    expect(snapshots).toHaveLength(2)
    expect(
      snapshots.map((snapshot) => snapshot.items.some((item) => item.path === anchorPath)),
    ).toEqual([true, true])
  })

  it('reports hydration progress for machine-checkable instrumentation', async () => {
    const first = makeFolder('/set', ['/set/a.jpg'], {
      page: 1,
      pageSize: 1,
      pageCount: 2,
      totalItems: 2,
    })
    const second = makeFolder('/set', ['/set/b.jpg'], {
      page: 2,
      pageSize: 1,
      pageCount: 2,
      totalItems: 2,
    })

    const progress: Array<{
      loadedPages: number
      totalPages: number
      loadedItems: number
      totalItems: number
      completed: boolean
    }> = []

    await hydrateFolderPages(first, {
      defaultPageSize: 200,
      fetchPage: async (page) => {
        if (page !== 2) throw new Error(`unexpected page: ${page}`)
        return second
      },
      onUpdate: () => {},
      onProgress: (value) => {
        progress.push(value)
      },
    })

    expect(progress.length).toBeGreaterThan(1)
    expect(progress[0]).toMatchObject({
      loadedPages: 1,
      totalPages: 2,
      loadedItems: 1,
      totalItems: 2,
      completed: false,
    })
    expect(progress[progress.length - 1]).toMatchObject({
      loadedPages: 2,
      totalPages: 2,
      loadedItems: 2,
      totalItems: 2,
      completed: true,
    })
  })

  it('throttles hydration progress updates while preserving completion signal', async () => {
    const first = makeFolder('/set', ['/set/a.jpg'], {
      page: 1,
      pageSize: 1,
      pageCount: 4,
      totalItems: 4,
    })
    const second = makeFolder('/set', ['/set/b.jpg'], {
      page: 2,
      pageSize: 1,
      pageCount: 4,
      totalItems: 4,
    })
    const third = makeFolder('/set', ['/set/c.jpg'], {
      page: 3,
      pageSize: 1,
      pageCount: 4,
      totalItems: 4,
    })
    const fourth = makeFolder('/set', ['/set/d.jpg'], {
      page: 4,
      pageSize: 1,
      pageCount: 4,
      totalItems: 4,
    })

    const progress: FolderHydrationProgress[] = []

    await hydrateFolderPages(first, {
      defaultPageSize: 200,
      progressUpdateIntervalMs: 60_000,
      fetchPage: async (page) => {
        if (page === 2) return second
        if (page === 3) return third
        if (page === 4) return fourth
        throw new Error(`unexpected page: ${page}`)
      },
      onUpdate: () => {},
      onProgress: (value) => {
        progress.push(value)
      },
    })

    expect(progress).toHaveLength(2)
    expect(progress[0]).toMatchObject({
      loadedPages: 1,
      completed: false,
    })
    expect(progress[1]).toMatchObject({
      loadedPages: 4,
      completed: true,
    })
  })
})
