import { describe, expect, it } from 'vitest'
import {
  getHorizontalNavigationDelta,
  hasShortcutModifier,
} from '../keyboard'

describe('keyboard shortcut helpers', () => {
  it('maps only unmodified horizontal navigation keys to directions', () => {
    expect(getHorizontalNavigationDelta({ key: 'ArrowRight' })).toBe(1)
    expect(getHorizontalNavigationDelta({ key: 'd' })).toBe(1)
    expect(getHorizontalNavigationDelta({ key: 'D' })).toBe(1)
    expect(getHorizontalNavigationDelta({ key: 'ArrowLeft' })).toBe(-1)
    expect(getHorizontalNavigationDelta({ key: 'a' })).toBe(-1)
    expect(getHorizontalNavigationDelta({ key: 'A' })).toBe(-1)
    expect(getHorizontalNavigationDelta({ key: 'Tab' })).toBeNull()
  })

  it('treats Ctrl, Meta, and Alt as shortcut modifiers', () => {
    expect(hasShortcutModifier({ key: 'a', altKey: false, ctrlKey: false, metaKey: false })).toBe(false)
    expect(hasShortcutModifier({ key: 'a', altKey: true, ctrlKey: false, metaKey: false })).toBe(true)
    expect(hasShortcutModifier({ key: 'a', altKey: false, ctrlKey: true, metaKey: false })).toBe(true)
    expect(hasShortcutModifier({ key: 'a', altKey: false, ctrlKey: false, metaKey: true })).toBe(true)
  })
})
