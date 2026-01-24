export type KeyHandler = (e: KeyboardEvent) => void

export interface KeyBinding {
  key: string
  handler: KeyHandler
  /** If true, also match when Ctrl/Cmd is held */
  withMod?: boolean
  /** If true, don't trigger when inside text inputs */
  ignoreInputs?: boolean
}

/**
 * Check if the event target is an input element.
 */
export function isInputElement(target: EventTarget | null): boolean {
  if (!target || !(target instanceof HTMLElement)) return false
  return target.closest('input, textarea, [contenteditable="true"]') !== null
}

/**
 * Check if an event has the platform-appropriate modifier key (Ctrl on Windows/Linux, Cmd on Mac).
 */
export function hasPlatformMod(e: KeyboardEvent | MouseEvent): boolean {
  const isMac = typeof navigator !== 'undefined' && /Mac|iPhone|iPad/.test(navigator.platform)
  return isMac ? e.metaKey : e.ctrlKey
}

/**
 * Register a single key handler. Returns cleanup function.
 * @param key - The key to listen for
 * @param handler - The handler function
 * @param options - Additional options
 */
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

/**
 * Register multiple key bindings at once. Returns cleanup function.
 */
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

/** Common key codes for reference */
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
