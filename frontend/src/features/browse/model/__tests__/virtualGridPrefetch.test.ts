import { describe, expect, it } from 'vitest'
import { getAdjacentThumbPrefetchPaths, getDemandThumbPaths } from '../virtualGridPrefetch'

describe('virtual grid thumb prefetch paths', () => {
  it('collects adjacent grid row item paths', () => {
    const items = [
      { path: '/a.jpg' },
      { path: '/b.jpg' },
      { path: '/c.jpg' },
      { path: '/d.jpg' },
      { path: '/e.jpg' },
    ]
    const virtualRows = [{ index: 1 }, { index: 2 }]
    const layout = { mode: 'grid' as const, columns: 2 }

    const paths = getAdjacentThumbPrefetchPaths(virtualRows, layout, items)
    expect(paths).toEqual(['/a.jpg', '/b.jpg'])
  })

  it('collects adjacent adaptive row item paths', () => {
    const items = [
      { path: '/a.jpg' },
      { path: '/b.jpg' },
      { path: '/c.jpg' },
      { path: '/d.jpg' },
    ]
    const virtualRows = [{ index: 0 }, { index: 1 }]
    const layout = {
      mode: 'adaptive' as const,
      rows: [
        {
          items: [{ item: { path: '/a.jpg' } }, { item: { path: '/b.jpg' } }],
        },
        {
          items: [{ item: { path: '/b.jpg' } }, { item: { path: '/c.jpg' } }],
        },
        {
          items: [{ item: { path: '/d.jpg' } }],
        },
      ],
    }

    const paths = getAdjacentThumbPrefetchPaths(virtualRows, layout, items)
    expect(paths).toEqual(['/d.jpg'])
  })

  it('returns empty list when there are no adjacent rows', () => {
    const items = [{ path: '/a.jpg' }, { path: '/b.jpg' }]
    const virtualRows = [{ index: 0 }]
    const layout = { mode: 'grid' as const, columns: 2 }

    expect(getAdjacentThumbPrefetchPaths(virtualRows, layout, items)).toEqual([])
  })

  it('collects viewport-intersecting rows as visible thumbnail demand', () => {
    const items = [
      { path: '/a.jpg' },
      { path: '/b.jpg' },
      { path: '/c.jpg' },
      { path: '/d.jpg' },
      { path: '/e.jpg' },
      { path: '/f.jpg' },
    ]
    const virtualRows = [
      { index: 0, start: 0, end: 100 },
      { index: 1, start: 100, end: 200 },
      { index: 2, start: 200, end: 300 },
    ]
    const layout = { mode: 'grid' as const, columns: 2 }

    expect(getDemandThumbPaths(virtualRows, layout, items, 125, 60)).toEqual(['/c.jpg', '/d.jpg'])
  })

  it('treats rows without geometry as demand so visible loads are not starved', () => {
    const items = [{ path: '/a.jpg' }, { path: '/b.jpg' }]
    const virtualRows = [{ index: 0 }]
    const layout = { mode: 'grid' as const, columns: 2 }

    expect(getDemandThumbPaths(virtualRows, layout, items, 0, 100)).toEqual(['/a.jpg', '/b.jpg'])
  })
})
