import { describe, expect, it } from 'vitest'
import {
  chooseInitialModalFocusTarget,
  chooseRestoreFocusTarget,
  isModalEscapeKey,
  resolveModalTabTarget,
} from '../useModalFocusTrap'

describe('modal focus trap helpers', () => {
  it('chooses the first enabled focus target and falls back to the dialog', () => {
    const disabled = { id: 'disabled', disabled: true, tabIndex: 0 }
    const hidden = { id: 'hidden', ariaHidden: true, tabIndex: 0 }
    const notRendered = { id: 'not-rendered', rendered: false, tabIndex: 0 }
    const enabled = { id: 'enabled', tabIndex: 0 }
    const fallback = { id: 'dialog', tabIndex: -1 }

    expect(chooseInitialModalFocusTarget([disabled, hidden, notRendered, enabled], fallback)).toBe(enabled)
    expect(chooseInitialModalFocusTarget([disabled, hidden, notRendered], fallback)).toBe(fallback)
  })

  it('wraps Tab at the end and Shift+Tab at the beginning', () => {
    const first = { id: 'first' }
    const second = { id: 'second' }
    const third = { id: 'third' }
    const targets = [first, second, third]

    expect(resolveModalTabTarget(targets, third, false)).toBe(first)
    expect(resolveModalTabTarget(targets, first, true)).toBe(third)
    expect(resolveModalTabTarget(targets, second, false)).toBeNull()
    expect(resolveModalTabTarget(targets, second, true)).toBeNull()
  })

  it('pulls unknown focus back inside the modal on Tab', () => {
    const first = { id: 'first' }
    const second = { id: 'second' }
    const outside = { id: 'outside' }
    const targets = [first, second]

    expect(resolveModalTabTarget(targets, outside, false)).toBe(first)
    expect(resolveModalTabTarget(targets, outside, true)).toBe(second)
  })

  it('detects Escape and resolves focus restore fallback', () => {
    const previous = { id: 'previous', isConnected: true }
    const removed = { id: 'removed', isConnected: false }
    const fallback = { id: 'fallback', isConnected: true }

    expect(isModalEscapeKey('Escape')).toBe(true)
    expect(isModalEscapeKey('Esc')).toBe(false)
    expect(chooseRestoreFocusTarget(previous, fallback)).toBe(previous)
    expect(chooseRestoreFocusTarget(removed, fallback)).toBe(fallback)
    expect(chooseRestoreFocusTarget(removed, { id: 'gone', isConnected: false })).toBeNull()
  })
})
