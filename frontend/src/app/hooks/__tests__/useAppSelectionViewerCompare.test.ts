import { describe, expect, it } from 'vitest'
import {
  resolveCompareOrderedItems,
  resolveGalleryOrderedItems,
  resolveSelectionOrderedItems,
  resolveOverlayPopstateResult,
  shouldCloseCompareForSelectionChange,
} from '../useAppSelectionViewerCompare'
import type { Item } from '../../../lib/types'

function buildItem(path: string, name: string): Item {
  return {
    path,
    name,
    type: 'image/png',
    w: 100,
    h: 100,
    size: 1,
    hasThumb: true,
    hasMeta: false,
  }
}

describe('useAppSelectionViewerCompare guards', () => {
  it('resolves compare/selection items in selected path order', () => {
    const selectedPaths = ['/images/b.png', '/images/a.png', '/images/missing.png']
    const selectionPool = [
      buildItem('/images/a.png', 'a-from-pool'),
      buildItem('/images/b.png', 'b-from-pool'),
    ]
    const items = [
      buildItem('/images/a.png', 'a-from-items'),
      buildItem('/images/b.png', 'b-from-items'),
    ]

    const ordered = resolveSelectionOrderedItems(selectedPaths, selectionPool, items)
    expect(ordered.map((item) => item.path)).toEqual(['/images/b.png', '/images/a.png'])
    expect(ordered.map((item) => item.name)).toEqual(['b-from-pool', 'a-from-pool'])
  })

  it('resolves gallery-ordered compare items from current sorted item list', () => {
    const selectedPaths = ['/images/b.png', '/images/a.png']
    const items = [
      buildItem('/images/a.png', 'a-from-items'),
      buildItem('/images/b.png', 'b-from-items'),
      buildItem('/images/c.png', 'c-from-items'),
    ]

    const ordered = resolveGalleryOrderedItems(selectedPaths, items)
    expect(ordered.map((item) => item.path)).toEqual(['/images/a.png', '/images/b.png'])
    expect(ordered.map((item) => item.name)).toEqual(['a-from-items', 'b-from-items'])
  })

  it('switches compare ordering strategy based on compare order mode', () => {
    const selectedPaths = ['/images/b.png', '/images/a.png']
    const selectionPool = [
      buildItem('/images/a.png', 'a-from-pool'),
      buildItem('/images/b.png', 'b-from-pool'),
    ]
    const items = [
      buildItem('/images/a.png', 'a-from-items'),
      buildItem('/images/b.png', 'b-from-items'),
    ]

    const galleryOrdered = resolveCompareOrderedItems(selectedPaths, selectionPool, items, 'gallery')
    expect(galleryOrdered.map((item) => item.path)).toEqual(['/images/a.png', '/images/b.png'])

    const selectionOrdered = resolveCompareOrderedItems(selectedPaths, selectionPool, items, 'selection')
    expect(selectionOrdered.map((item) => item.path)).toEqual(['/images/b.png', '/images/a.png'])
  })

  it('auto-closes compare only when compare is open and selection drops below compare support', () => {
    expect(shouldCloseCompareForSelectionChange(false, false)).toBe(false)
    expect(shouldCloseCompareForSelectionChange(false, true)).toBe(false)
    expect(shouldCloseCompareForSelectionChange(true, true)).toBe(false)
    expect(shouldCloseCompareForSelectionChange(true, false)).toBe(true)
  })

  it('resolves popstate overlays by clearing active viewer/compare overlays only', () => {
    expect(resolveOverlayPopstateResult(null, false)).toEqual({
      resetViewer: false,
      resetCompare: false,
    })
    expect(resolveOverlayPopstateResult('/images/a.png', false)).toEqual({
      resetViewer: true,
      resetCompare: false,
    })
    expect(resolveOverlayPopstateResult(null, true)).toEqual({
      resetViewer: false,
      resetCompare: true,
    })
    expect(resolveOverlayPopstateResult('/images/a.png', true)).toEqual({
      resetViewer: true,
      resetCompare: true,
    })
  })
})
