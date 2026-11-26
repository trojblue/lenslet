import { useEffect } from 'react'
import type { BrowseItemPayload, StarRating } from '../../lib/types'
import {
  getTopmostModalDialog,
  isInputElement,
  isKeyboardControlTarget,
} from '../../lib/keyboard'
import { getParentPath } from '../routing/hash'
import { resolveSidebarHotkeyToggle } from '../layout/sidebarLayout'
import { LAYOUT_BREAKPOINTS } from '../../lib/breakpoints'
import { useLatestRef } from '../../shared/hooks/useLatestRef'

export type AppKeyboardShortcutEvent = {
  key: string
  altKey: boolean
  ctrlKey: boolean
  metaKey: boolean
  shiftKey: boolean
  targetIsInput: boolean
  targetIsKeyboardControl: boolean
  activeModalOpen: boolean
  /** The only modal is the narrow-layout Inspector sheet, which still rates the selection. */
  modalIsInspectorSheet: boolean
}

export type AppKeyboardShortcutContext = {
  viewerOpen: boolean
  compareOpen: boolean
  selectedCount: number
  mobileSelectMode: boolean
  leftOpen: boolean
  rightOpen: boolean
  isNarrowViewport: boolean
}

export type AppKeyboardShortcutResolution =
  | { kind: 'none' }
  | { kind: 'toggleSidebars'; leftOpen: boolean; rightOpen: boolean }
  | { kind: 'selectAll' }
  | { kind: 'openParentFolder' }
  | { kind: 'clearSelection' }
  | { kind: 'exitMobileSelectMode' }
  | { kind: 'openMobileSearch' }
  | { kind: 'focusDesktopSearch' }
  | { kind: 'setStar'; star: StarRating }

export type UseAppKeyboardShortcutsParams = {
  current: string
  items: readonly BrowseItemPayload[]
  selectedPaths: readonly string[]
  viewerOpen: boolean
  compareOpen: boolean
  mobileSelectMode: boolean
  leftOpen: boolean
  rightOpen: boolean
  viewportWidth: number
  openFolder: (path: string) => void
  setSelectedPaths: (paths: string[]) => void
  setLeftOpen: (open: boolean) => void
  setRightOpen: (open: boolean) => void
  setMobileSelectMode: (open: boolean) => void
  setMobileSearchOpen: (open: boolean) => void
  focusDesktopSearch: () => void
  /** Rate the requested selection; must not depend on what the Inspector presents. */
  setStar: (paths: readonly string[], star: StarRating) => void
}

const NO_SHORTCUT: AppKeyboardShortcutResolution = { kind: 'none' }

function resolveStarShortcut(
  event: AppKeyboardShortcutEvent,
  context: AppKeyboardShortcutContext,
): AppKeyboardShortcutResolution | null {
  if (!/^[0-5]$/.test(event.key)) return null
  const modalBlocks = event.activeModalOpen && !event.modalIsInspectorSheet
  if (
    event.altKey || event.ctrlKey || event.metaKey
    || event.targetIsInput || modalBlocks || context.compareOpen || !context.selectedCount
  ) {
    return NO_SHORTCUT
  }
  return { kind: 'setStar', star: event.key === '0' ? null : (Number(event.key) as 1 | 2 | 3 | 4 | 5) }
}

export function resolveAppKeyboardShortcut(
  event: AppKeyboardShortcutEvent,
  context: AppKeyboardShortcutContext,
): AppKeyboardShortcutResolution {
  // Ratings target the selection, so they also apply in the viewer and over focused buttons.
  const star = resolveStarShortcut(event, context)
  if (star) return star
  if (context.viewerOpen || context.compareOpen || event.activeModalOpen) {
    return NO_SHORTCUT
  }

  const normalizedKey = event.key.toLowerCase()
  const hasPlatformShortcutModifier = event.ctrlKey || event.metaKey
  const hasPlainPlatformShortcut = hasPlatformShortcutModifier && !event.altKey

  if (
    hasPlatformShortcutModifier
    && !event.shiftKey
    && normalizedKey === 'b'
    && !event.targetIsInput
  ) {
    const next = resolveSidebarHotkeyToggle({
      leftContentOpen: context.leftOpen,
      rightOpen: context.rightOpen,
      altKey: event.altKey,
    })
    return {
      kind: 'toggleSidebars',
      leftOpen: next.leftContentOpen,
      rightOpen: next.rightOpen,
    }
  }

  if (event.targetIsKeyboardControl) return NO_SHORTCUT

  if (hasPlainPlatformShortcut && normalizedKey === 'a') {
    return { kind: 'selectAll' }
  }

  if (event.altKey || event.ctrlKey || event.metaKey) return NO_SHORTCUT

  if (event.key === 'Backspace' || event.key === 'Delete') {
    return { kind: 'openParentFolder' }
  }
  if (event.key === 'Escape') {
    if (context.selectedCount) return { kind: 'clearSelection' }
    if (context.mobileSelectMode) return { kind: 'exitMobileSelectMode' }
    return NO_SHORTCUT
  }
  if (event.key === '/') {
    return context.isNarrowViewport
      ? { kind: 'openMobileSearch' }
      : { kind: 'focusDesktopSearch' }
  }

  return NO_SHORTCUT
}

function keyboardEventSnapshot(event: KeyboardEvent): AppKeyboardShortcutEvent {
  const modal = getTopmostModalDialog()
  return {
    key: event.key,
    altKey: event.altKey,
    ctrlKey: event.ctrlKey,
    metaKey: event.metaKey,
    shiftKey: event.shiftKey,
    targetIsInput: isInputElement(event.target),
    targetIsKeyboardControl: isKeyboardControlTarget(event.target),
    activeModalOpen: modal !== null,
    modalIsInspectorSheet: modal?.matches('.responsive-panel[data-panel-side="right"]') ?? false,
  }
}

function shortcutContextSnapshot(
  params: UseAppKeyboardShortcutsParams,
): AppKeyboardShortcutContext {
  return {
    viewerOpen: params.viewerOpen,
    compareOpen: params.compareOpen,
    selectedCount: params.selectedPaths.length,
    mobileSelectMode: params.mobileSelectMode,
    leftOpen: params.leftOpen,
    rightOpen: params.rightOpen,
    isNarrowViewport: params.viewportWidth <= LAYOUT_BREAKPOINTS.narrowMax,
  }
}

export function useAppKeyboardShortcuts(params: UseAppKeyboardShortcutsParams): void {
  const paramsRef = useLatestRef(params)

  useEffect(() => {
    const onKey = (event: KeyboardEvent) => {
      const state = paramsRef.current
      const resolution = resolveAppKeyboardShortcut(
        keyboardEventSnapshot(event),
        shortcutContextSnapshot(state),
      )

      if (resolution.kind === 'none') return
      event.preventDefault()

      if (resolution.kind === 'toggleSidebars') {
        state.setLeftOpen(resolution.leftOpen)
        state.setRightOpen(resolution.rightOpen)
      } else if (resolution.kind === 'selectAll') {
        state.setSelectedPaths(state.items.map((item) => item.path))
      } else if (resolution.kind === 'openParentFolder') {
        state.openFolder(getParentPath(state.current))
      } else if (resolution.kind === 'clearSelection') {
        state.setSelectedPaths([])
      } else if (resolution.kind === 'exitMobileSelectMode') {
        state.setMobileSelectMode(false)
      } else if (resolution.kind === 'setStar') {
        state.setStar(state.selectedPaths, resolution.star)
      } else if (resolution.kind === 'openMobileSearch') {
        state.setMobileSearchOpen(true)
      } else {
        state.focusDesktopSearch()
      }
    }

    window.addEventListener('keydown', onKey)
    return () => window.removeEventListener('keydown', onKey)
  }, [paramsRef])
}
