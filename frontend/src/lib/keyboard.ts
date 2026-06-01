export type KeyHandler = (e: KeyboardEvent) => void

export interface KeyBinding {
  key: string
  handler: KeyHandler
  /** If true, also match when Ctrl/Cmd is held */
  withMod?: boolean
  /** If true, don't trigger when inside text inputs */
  ignoreInputs?: boolean
}

const KEYBOARD_CONTROL_SELECTOR = [
  'button',
  'a[href]',
  'input',
  'select',
  'textarea',
  '[contenteditable]:not([contenteditable="false"])',
  '[role="button"]',
  '[role="checkbox"]',
  '[role="combobox"]',
  '[role="menuitem"]',
  '[role="menuitemcheckbox"]',
  '[role="menuitemradio"]',
  '[role="option"]',
  '[role="radio"]',
  '[role="searchbox"]',
  '[role="slider"]',
  '[role="spinbutton"]',
  '[role="switch"]',
  '[role="textbox"]',
].join(',')

type KeyboardLikeEvent = Pick<KeyboardEvent, 'altKey' | 'ctrlKey' | 'key' | 'metaKey'>
type KeyboardTargetEvent = KeyboardLikeEvent & Pick<KeyboardEvent, 'target'>

/** Check if the event target is an editable text-style control. */
export function isInputElement(target: EventTarget | null): boolean {
  if (!target || typeof HTMLElement === 'undefined' || !(target instanceof HTMLElement)) return false
  return target.closest(
    'input, textarea, select, [contenteditable]:not([contenteditable="false"]), [role="textbox"], [role="searchbox"], [role="combobox"]',
  ) !== null
}

/**
 * Check if an event has the platform-appropriate modifier key (Ctrl on Windows/Linux, Cmd on Mac).
 */
export function hasPlatformMod(e: KeyboardEvent | MouseEvent): boolean {
  const isMac = typeof navigator !== 'undefined' && /Mac|iPhone|iPad/.test(navigator.platform)
  return isMac ? e.metaKey : e.ctrlKey
}

export function hasShortcutModifier(e: KeyboardLikeEvent): boolean {
  return e.altKey || e.ctrlKey || e.metaKey
}

export function isKeyboardControlTarget(target: EventTarget | null): boolean {
  if (!target || typeof HTMLElement === 'undefined' || !(target instanceof HTMLElement)) return false
  return target.closest(KEYBOARD_CONTROL_SELECTOR) !== null
}

export function getHorizontalNavigationDelta(e: Pick<KeyboardEvent, 'key'>): -1 | 1 | null {
  const normalized = e.key.toLowerCase()
  if (e.key === 'ArrowRight' || normalized === 'd') return 1
  if (e.key === 'ArrowLeft' || normalized === 'a') return -1
  return null
}

function isVisibleElement(element: HTMLElement): boolean {
  if (!element.isConnected) return false
  const rect = element.getBoundingClientRect()
  if (rect.width <= 0 || rect.height <= 0) return false
  const style = window.getComputedStyle(element)
  return style.display !== 'none' && style.visibility !== 'hidden'
}

export function getTopmostModalDialog(): HTMLElement | null {
  if (typeof document === 'undefined' || typeof window === 'undefined') return null
  const dialogs = Array.from(
    document.querySelectorAll<HTMLElement>('[role="dialog"][aria-modal="true"]'),
  ).filter(isVisibleElement)
  return dialogs[dialogs.length - 1] ?? null
}

export function hasActiveModalDialog(): boolean {
  return getTopmostModalDialog() !== null
}

export function isTopmostModalDialog(dialog: HTMLElement | null): boolean {
  if (!dialog || typeof document === 'undefined') return false
  const topmost = getTopmostModalDialog()
  return topmost === null ? document.contains(dialog) : topmost === dialog
}

export function shouldHandleDialogNavigationKey(
  e: KeyboardTargetEvent,
  dialog: HTMLElement | null,
): boolean {
  return getHorizontalNavigationDelta(e) !== null
    && !hasShortcutModifier(e)
    && !isKeyboardControlTarget(e.target)
    && isTopmostModalDialog(dialog)
}

export function shouldHandleViewerNavigationKey(e: KeyboardTargetEvent): boolean {
  return getHorizontalNavigationDelta(e) !== null
    && !hasShortcutModifier(e)
    && !isInputElement(e.target)
}

export function onKey(
  key: string,
  handler: KeyHandler,
  options: { ignoreInputs?: boolean; withMod?: boolean } = {}
): () => void {
  const { ignoreInputs = true, withMod = false } = options
  
  const h = (e: KeyboardEvent) => {
    if (e.key !== key) return
    if (ignoreInputs && isInputElement(e.target)) return
    if (withMod && !hasPlatformMod(e)) return
    handler(e)
  }
  
  window.addEventListener('keydown', h)
  return () => window.removeEventListener('keydown', h)
}

export function onKeys(bindings: KeyBinding[]): () => void {
  const handlers: (() => void)[] = []
  
  for (const binding of bindings) {
    handlers.push(
      onKey(binding.key, binding.handler, {
        ignoreInputs: binding.ignoreInputs ?? true,
        withMod: binding.withMod ?? false,
      })
    )
  }
  
  return () => {
    for (const cleanup of handlers) {
      cleanup()
    }
  }
}

export const Keys = {
  Enter: 'Enter',
  Escape: 'Escape',
  Space: ' ',
  Tab: 'Tab',
  Backspace: 'Backspace',
  Delete: 'Delete',
  ArrowUp: 'ArrowUp',
  ArrowDown: 'ArrowDown',
  ArrowLeft: 'ArrowLeft',
  ArrowRight: 'ArrowRight',
  Home: 'Home',
  End: 'End',
  PageUp: 'PageUp',
  PageDown: 'PageDown',
} as const
