import { describe, expect, it } from 'vitest'
import { getAdjacentThumbPrefetchPaths } from '../virtualGridPrefetch'

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
})
