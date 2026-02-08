import { describe, expect, it } from 'vitest'
import { isTouchLikePointer, shouldOpenOnTap, toggleSelectedPath } from '../mobileSelection'

describe('mobileSelection', () => {
  it('treats touch and pen as touch-like pointers', () => {
    expect(isTouchLikePointer('touch')).toBe(true)
    expect(isTouchLikePointer('pen')).toBe(true)
    expect(isTouchLikePointer('mouse')).toBe(false)
    expect(isTouchLikePointer(undefined)).toBe(false)
  })

  it('opens on tap when touch-like pointer taps the single selected path', () => {
    expect(shouldOpenOnTap({
      pointerType: 'touch',
      multiSelectMode: false,
      isShift: false,
      isToggle: false,
      selectedPaths: ['/a.jpg'],
      path: '/a.jpg',
    })).toBe(true)
  })

  it('does not open on tap when multi-select mode or modifiers are active', () => {
    expect(shouldOpenOnTap({
      pointerType: 'touch',
      multiSelectMode: true,
      isShift: false,
      isToggle: false,
      selectedPaths: ['/a.jpg'],
      path: '/a.jpg',
    })).toBe(false)

    expect(shouldOpenOnTap({
      pointerType: 'touch',
      multiSelectMode: false,
      isShift: true,
      isToggle: false,
      selectedPaths: ['/a.jpg'],
      path: '/a.jpg',
    })).toBe(false)
  })

  it('toggles path membership while preserving selection order', () => {
    expect(toggleSelectedPath(['/a.jpg', '/b.jpg'], '/c.jpg')).toEqual(['/a.jpg', '/b.jpg', '/c.jpg'])
    expect(toggleSelectedPath(['/a.jpg', '/b.jpg', '/c.jpg'], '/b.jpg')).toEqual(['/a.jpg', '/c.jpg'])
  })
})
