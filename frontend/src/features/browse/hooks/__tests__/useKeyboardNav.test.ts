import { describe, expect, it } from 'vitest'
import type { Item } from '../../../../lib/types'
import { getNextIndexForKeyNav } from '../useKeyboardNav'

function makeItems(paths: string[]): Item[] {
  return paths.map((path) => ({
    path,
    name: path.split('/').pop() ?? path,
    type: 'image/jpeg',
    w: 1,
    h: 1,
    size: 1,
    hasThumb: true,
    hasMeta: true,
  }))
}

function keyEvent(key: string): KeyboardEvent {
  return { key } as KeyboardEvent
}

describe('grid keyboard navigation', () => {
  const items = makeItems([
    '/set/a.jpg',
    '/set/b.jpg',
    '/set/c.jpg',
    '/set/d.jpg',
    '/set/e.jpg',
  ])

  it('moves horizontally and vertically with arrow keys', () => {
    expect(getNextIndexForKeyNav(items, 2, '/set/a.jpg', keyEvent('ArrowRight'))).toBe(1)
    expect(getNextIndexForKeyNav(items, 2, '/set/a.jpg', keyEvent('ArrowDown'))).toBe(2)
    expect(getNextIndexForKeyNav(items, 2, '/set/d.jpg', keyEvent('ArrowUp'))).toBe(1)
    expect(getNextIndexForKeyNav(items, 2, '/set/e.jpg', keyEvent('ArrowLeft'))).toBe(3)
  })

  it('clamps at bounds and only opens on Enter when an active path exists', () => {
    expect(getNextIndexForKeyNav(items, 2, '/set/a.jpg', keyEvent('ArrowLeft'))).toBe(0)
    expect(getNextIndexForKeyNav(items, 2, '/set/e.jpg', keyEvent('ArrowDown'))).toBe(4)
    expect(getNextIndexForKeyNav(items, 2, '/set/a.jpg', keyEvent('Enter'))).toBe('open')
    expect(getNextIndexForKeyNav(items, 2, null, keyEvent('Enter'))).toBeNull()
  })
})
