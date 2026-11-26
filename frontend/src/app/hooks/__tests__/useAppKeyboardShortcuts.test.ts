import { describe, expect, it } from 'vitest'
import {
  resolveAppKeyboardShortcut,
  type AppKeyboardShortcutContext,
  type AppKeyboardShortcutEvent,
} from '../useAppKeyboardShortcuts'

function shortcutEvent(overrides: Partial<AppKeyboardShortcutEvent> = {}): AppKeyboardShortcutEvent {
  return {
    key: 'x',
    altKey: false,
    ctrlKey: false,
    metaKey: false,
    shiftKey: false,
    targetIsInput: false,
    targetIsKeyboardControl: false,
    activeModalOpen: false,
    modalIsInspectorSheet: false,
    ...overrides,
  }
}

function shortcutContext(overrides: Partial<AppKeyboardShortcutContext> = {}): AppKeyboardShortcutContext {
  return {
    viewerOpen: false,
    compareOpen: false,
    selectedCount: 0,
    mobileSelectMode: false,
    leftOpen: true,
    rightOpen: true,
    isNarrowViewport: false,
    ...overrides,
  }
}

describe('app keyboard shortcut policy', () => {
  it('lets modal surfaces own global shortcuts', () => {
    expect(resolveAppKeyboardShortcut(
      shortcutEvent({ key: 'a', ctrlKey: true }),
      shortcutContext({ viewerOpen: true }),
    )).toEqual({ kind: 'none' })

    expect(resolveAppKeyboardShortcut(
      shortcutEvent({ key: 'Backspace' }),
      shortcutContext({ compareOpen: true }),
    )).toEqual({ kind: 'none' })

    expect(resolveAppKeyboardShortcut(
      shortcutEvent({ key: '/', activeModalOpen: true }),
      shortcutContext(),
    )).toEqual({ kind: 'none' })
  })

  it('routes platform-B to the sidebar toggle before generic control suppression', () => {
    expect(resolveAppKeyboardShortcut(
      shortcutEvent({ key: 'b', ctrlKey: true, targetIsKeyboardControl: true }),
      shortcutContext({ leftOpen: true, rightOpen: true }),
    )).toEqual({
      kind: 'toggleSidebars',
      leftOpen: false,
      rightOpen: true,
    })

    expect(resolveAppKeyboardShortcut(
      shortcutEvent({ key: 'b', metaKey: true, altKey: true }),
      shortcutContext({ leftOpen: true, rightOpen: true }),
    )).toEqual({
      kind: 'toggleSidebars',
      leftOpen: true,
      rightOpen: false,
    })
  })

  it('leaves platform-Shift-B to the browser', () => {
    expect(resolveAppKeyboardShortcut(
      shortcutEvent({ key: 'B', ctrlKey: true, shiftKey: true }),
      shortcutContext({ leftOpen: true, rightOpen: true }),
    )).toEqual({ kind: 'none' })

    expect(resolveAppKeyboardShortcut(
      shortcutEvent({ key: 'B', metaKey: true, shiftKey: true }),
      shortcutContext({ leftOpen: true, rightOpen: true }),
    )).toEqual({ kind: 'none' })
  })

  it('keeps text input shortcuts with the focused input', () => {
    expect(resolveAppKeyboardShortcut(
      shortcutEvent({
        key: 'a',
        ctrlKey: true,
        targetIsInput: true,
        targetIsKeyboardControl: true,
      }),
      shortcutContext(),
    )).toEqual({ kind: 'none' })

    expect(resolveAppKeyboardShortcut(
      shortcutEvent({ key: 'b', ctrlKey: true, targetIsInput: true }),
      shortcutContext(),
    )).toEqual({ kind: 'none' })
  })

  it('maps selection and folder navigation shortcuts by current state', () => {
    expect(resolveAppKeyboardShortcut(
      shortcutEvent({ key: 'a', ctrlKey: true }),
      shortcutContext(),
    )).toEqual({ kind: 'selectAll' })

    expect(resolveAppKeyboardShortcut(
      shortcutEvent({ key: 'Backspace' }),
      shortcutContext(),
    )).toEqual({ kind: 'openParentFolder' })

    expect(resolveAppKeyboardShortcut(
      shortcutEvent({ key: 'Escape' }),
      shortcutContext({ selectedCount: 2, mobileSelectMode: true }),
    )).toEqual({ kind: 'clearSelection' })

    expect(resolveAppKeyboardShortcut(
      shortcutEvent({ key: 'Escape' }),
      shortcutContext({ mobileSelectMode: true }),
    )).toEqual({ kind: 'exitMobileSelectMode' })
  })

  it('routes slash search by viewport mode', () => {
    expect(resolveAppKeyboardShortcut(
      shortcutEvent({ key: '/' }),
      shortcutContext({ isNarrowViewport: false }),
    )).toEqual({ kind: 'focusDesktopSearch' })

    expect(resolveAppKeyboardShortcut(
      shortcutEvent({ key: '/' }),
      shortcutContext({ isNarrowViewport: true }),
    )).toEqual({ kind: 'openMobileSearch' })
  })

  describe('star ratings', () => {
    const selected = shortcutContext({ selectedCount: 1 })

    it('rates the selection without waiting on the Inspector', () => {
      expect(resolveAppKeyboardShortcut(shortcutEvent({ key: '1' }), selected))
        .toEqual({ kind: 'setStar', star: 1 })
      expect(resolveAppKeyboardShortcut(shortcutEvent({ key: '0' }), selected))
        .toEqual({ kind: 'setStar', star: null })
      // The Inspector being closed is irrelevant to the selection being rated.
      expect(resolveAppKeyboardShortcut(shortcutEvent({ key: '5' }), shortcutContext({ selectedCount: 3, rightOpen: false })))
        .toEqual({ kind: 'setStar', star: 5 })
    })

    it('rates in the viewer, over focused buttons and from the Inspector sheet', () => {
      expect(resolveAppKeyboardShortcut(shortcutEvent({ key: '2' }), shortcutContext({ selectedCount: 1, viewerOpen: true })))
        .toEqual({ kind: 'setStar', star: 2 })
      expect(resolveAppKeyboardShortcut(shortcutEvent({ key: '3', targetIsKeyboardControl: true }), selected))
        .toEqual({ kind: 'setStar', star: 3 })
      expect(resolveAppKeyboardShortcut(
        shortcutEvent({ key: '4', activeModalOpen: true, modalIsInspectorSheet: true }),
        selected,
      )).toEqual({ kind: 'setStar', star: 4 })
    })

    it.each([
      ['typing', shortcutEvent({ key: '1', targetIsInput: true }), selected],
      ['ctrl', shortcutEvent({ key: '1', ctrlKey: true }), selected],
      ['alt', shortcutEvent({ key: '1', altKey: true }), selected],
      ['meta', shortcutEvent({ key: '1', metaKey: true }), selected],
      ['other modal', shortcutEvent({ key: '1', activeModalOpen: true }), selected],
      ['compare', shortcutEvent({ key: '1' }), shortcutContext({ selectedCount: 2, compareOpen: true })],
      ['no selection', shortcutEvent({ key: '1' }), shortcutContext()],
    ])('ignores rating keys when %s', (_label, event, context) => {
      expect(resolveAppKeyboardShortcut(event, context)).toEqual({ kind: 'none' })
    })
  })
})
