import { describe, expect, it } from 'vitest'
import { getVisibleThumbPrefetchPaths } from '../virtualGridPrefetch'

describe('virtual grid thumb prefetch paths', () => {
  it('collects visible grid row item paths', () => {
    const items = [
      { path: '/a.jpg' },
      { path: '/b.jpg' },
      { path: '/c.jpg' },
      { path: '/d.jpg' },
      { path: '/e.jpg' },
    ]
    const virtualRows = [{ index: 0 }, { index: 1 }, { index: 1 }]
    const layout = { mode: 'grid' as const, columns: 2 }

    const paths = getVisibleThumbPrefetchPaths(virtualRows, layout, items)
    expect(paths).toEqual(['/a.jpg', '/b.jpg', '/c.jpg', '/d.jpg'])
  })

  it('collects visible adaptive row item paths', () => {
    const items = [
      { path: '/a.jpg' },
      { path: '/b.jpg' },
      { path: '/c.jpg' },
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
      ],
    }

    const paths = getVisibleThumbPrefetchPaths(virtualRows, layout, items)
    expect(paths).toEqual(['/a.jpg', '/b.jpg', '/c.jpg'])
  })
})
