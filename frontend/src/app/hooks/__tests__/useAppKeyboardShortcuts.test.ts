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
    targetIsInput: false,
    targetIsKeyboardControl: false,
    activeModalOpen: false,
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
})
