import { describe, expect, it } from 'vitest'
import type { Item } from '../../../../lib/types'
import {
  collectVisiblePaths,
  getRestoreScrollTopForPath,
  getTopAnchorPathForVisibleRows,
  resolveVirtualGridRestoreDecision,
  type VirtualGridLayoutLike,
} from '../virtualGridSession'

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

function makePathToIndex(items: Item[]): Map<string, number> {
  const map = new Map<string, number>()
  items.forEach((item, index) => {
    map.set(item.path, index)
  })
  return map
}

describe('virtual grid session contracts', () => {
  it('collects visible paths and top-anchor for grid layout rows', () => {
    const items = [
      makeItem('/set/0.jpg'),
      makeItem('/set/1.jpg'),
      makeItem('/set/2.jpg'),
      makeItem('/set/3.jpg'),
      makeItem('/set/4.jpg'),
      makeItem('/set/5.jpg'),
    ]
    const layout: VirtualGridLayoutLike = {
      mode: 'grid',
      columns: 3,
      rowH: 140,
    }
    const virtualRows = [{ index: 1 }, { index: 2 }]

    expect(Array.from(collectVisiblePaths(items, layout, virtualRows))).toEqual([
      '/set/3.jpg',
      '/set/4.jpg',
      '/set/5.jpg',
    ])
    expect(getTopAnchorPathForVisibleRows(items, layout, virtualRows)).toBe('/set/3.jpg')
  })

  it('collects visible paths and top-anchor for adaptive rows', () => {
    const items = [
      makeItem('/adaptive/a.jpg'),
      makeItem('/adaptive/b.jpg'),
      makeItem('/adaptive/c.jpg'),
    ]
    const layout: VirtualGridLayoutLike = {
      mode: 'adaptive',
      rows: [
        {
          items: [
            { item: items[0], originalIndex: 0 },
            { item: items[1], originalIndex: 1 },
          ],
        },
        {
          items: [
            { item: items[2], originalIndex: 2 },
          ],
        },
      ],
    }
    const virtualRows = [{ index: 1 }]

    expect(Array.from(collectVisiblePaths(items, layout, virtualRows))).toEqual(['/adaptive/c.jpg'])
    expect(getTopAnchorPathForVisibleRows(items, layout, virtualRows)).toBe('/adaptive/c.jpg')
  })

  it('prioritizes selection restore token but falls back to top-anchor token when selection path is unavailable', () => {
    const availablePaths = new Set(['/set/a.jpg', '/set/b.jpg'])
    const hasPath = (path: string) => availablePaths.has(path)

    const selectionDecision = resolveVirtualGridRestoreDecision({
      selectionToken: 4,
      appliedSelectionToken: 3,
      selectedPath: '/set/a.jpg',
      topAnchorToken: 9,
      appliedTopAnchorToken: 8,
      topAnchorPath: '/set/b.jpg',
      hasPath,
    })
    expect(selectionDecision).toEqual({
      source: 'selection',
      path: '/set/a.jpg',
      token: 4,
    })

    const topAnchorFallback = resolveVirtualGridRestoreDecision({
      selectionToken: 4,
      appliedSelectionToken: 3,
      selectedPath: '/set/missing.jpg',
      topAnchorToken: 9,
      appliedTopAnchorToken: 8,
      topAnchorPath: '/set/b.jpg',
      hasPath,
    })
    expect(topAnchorFallback).toEqual({
      source: 'top-anchor',
      path: '/set/b.jpg',
      token: 9,
    })
  })

  it('computes restore scroll offsets for grid and adaptive layouts', () => {
    const gridItems = [
      makeItem('/grid/a.jpg'),
      makeItem('/grid/b.jpg'),
      makeItem('/grid/c.jpg'),
      makeItem('/grid/d.jpg'),
    ]
    const gridPathToIndex = makePathToIndex(gridItems)
    const gridLayout: VirtualGridLayoutLike = {
      mode: 'grid',
      columns: 2,
      rowH: 100,
    }
    expect(getRestoreScrollTopForPath({
      path: '/grid/d.jpg',
      pathToIndex: gridPathToIndex,
      layout: gridLayout,
      adaptiveRowMeta: null,
    })).toBe(100)

    const adaptiveItems = [
      makeItem('/adaptive/a.jpg'),
      makeItem('/adaptive/b.jpg'),
      makeItem('/adaptive/c.jpg'),
    ]
    const adaptivePathToIndex = makePathToIndex(adaptiveItems)
    const adaptiveLayout: VirtualGridLayoutLike = {
      mode: 'adaptive',
      rows: [
        {
          items: [
            { item: adaptiveItems[0], originalIndex: 0 },
            { item: adaptiveItems[1], originalIndex: 1 },
          ],
        },
        {
          items: [
            { item: adaptiveItems[2], originalIndex: 2 },
          ],
        },
      ],
    }
    expect(getRestoreScrollTopForPath({
      path: '/adaptive/c.jpg',
      pathToIndex: adaptivePathToIndex,
      layout: adaptiveLayout,
      adaptiveRowMeta: [
        { start: 0, height: 88 },
        { start: 88, height: 92 },
      ],
    })).toBe(88)
  })
})
