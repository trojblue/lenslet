import {
  type KeyboardEvent as ReactKeyboardEvent,
  type RefObject,
  useCallback,
  useEffect,
  useRef,
} from 'react'

const FOCUSABLE_SELECTOR = [
  'a[href]',
  'button',
  'input',
  'select',
  'textarea',
  '[tabindex]',
].join(',')

export type ModalFocusTarget = {
  disabled?: boolean
  tabIndex?: number
  ariaHidden?: boolean
  rendered?: boolean
  visible?: boolean
}

type RestorableFocusTarget = {
  isConnected?: boolean
}

export function isModalFocusTargetEnabled(target: ModalFocusTarget): boolean {
  if (target.disabled) return false
  if (target.ariaHidden) return false
  if (target.rendered === false) return false
  if (target.visible === false) return false
  return (target.tabIndex ?? 0) >= 0
}

export function chooseInitialModalFocusTarget<T extends ModalFocusTarget>(
  targets: readonly T[],
  fallback: T,
): T {
  return targets.find(isModalFocusTargetEnabled) ?? fallback
}

export function resolveModalTabTarget<T>(
  focusableTargets: readonly T[],
  activeTarget: T | null,
  shiftKey: boolean,
): T | null {
  if (focusableTargets.length === 0) return null
  const activeIndex = activeTarget == null ? -1 : focusableTargets.indexOf(activeTarget)
  if (activeIndex === -1) return shiftKey ? focusableTargets[focusableTargets.length - 1] : focusableTargets[0]
  if (shiftKey && activeIndex === 0) return focusableTargets[focusableTargets.length - 1]
  if (!shiftKey && activeIndex === focusableTargets.length - 1) return focusableTargets[0]
  return null
}

export function isModalEscapeKey(key: string): boolean {
  return key === 'Escape'
}

export function chooseRestoreFocusTarget<T extends RestorableFocusTarget>(
  target: T | null,
  fallback: T | null,
): T | null {
  if (target && target.isConnected !== false) return target
  if (fallback && fallback.isConnected !== false) return fallback
  return null
}

function getFocusableElements(container: HTMLElement): HTMLElement[] {
  return Array.from(container.querySelectorAll<HTMLElement>(FOCUSABLE_SELECTOR))
    .filter((element) => {
      const style = window.getComputedStyle(element)
      return isModalFocusTargetEnabled({
        disabled: 'disabled' in element && Boolean(element.disabled),
        tabIndex: element.tabIndex,
        ariaHidden: element.getAttribute('aria-hidden') === 'true',
        rendered: element.getClientRects().length > 0,
        visible: style.display !== 'none' && style.visibility !== 'hidden',
      })
    })
}

function focusElement(element: HTMLElement | null): void {
  try {
    element?.focus({ preventScroll: true })
  } catch {
    element?.focus()
  }
}

function focusModalEntry(container: HTMLElement): void {
  const target = chooseInitialModalFocusTarget(getFocusableElements(container), container)
  focusElement(target)
}

function restoreModalFocus(target: HTMLElement | null, fallback: HTMLElement | null): void {
  focusElement(chooseRestoreFocusTarget(target, fallback))
}

type ModalKeyboardEvent = {
  key: string
  shiftKey: boolean
  preventDefault: () => void
  stopPropagation: () => void
}

function handleModalKeyboardEvent(
  event: ModalKeyboardEvent,
  dialog: HTMLElement | null,
  onEscape: () => void,
): void {
  if (isModalEscapeKey(event.key)) {
    event.preventDefault()
    event.stopPropagation()
    onEscape()
    return
  }
  if (event.key !== 'Tab' || !dialog || typeof document === 'undefined') return

  const target = resolveModalTabTarget(
    getFocusableElements(dialog),
    document.activeElement instanceof HTMLElement ? document.activeElement : null,
    event.shiftKey,
  )
  if (!target) return
  event.preventDefault()
  event.stopPropagation()
  focusElement(target)
}

export function useModalFocusTrap<T extends HTMLElement>(
  dialogRef: RefObject<T>,
  options: {
    enabled?: boolean
    onEscape: () => void
  },
): (event: ReactKeyboardEvent<T>) => void {
  const { enabled = true, onEscape } = options
  const previousFocusRef = useRef<HTMLElement | null>(null)

  useEffect(() => {
    if (!enabled || typeof document === 'undefined') return undefined
    previousFocusRef.current = document.activeElement instanceof HTMLElement
      ? document.activeElement
      : null

    let frameId = 0
    let focusOutTimer = 0
    const focusEntry = () => {
      const dialog = dialogRef.current
      if (dialog) focusModalEntry(dialog)
    }
    try {
      frameId = window.requestAnimationFrame(focusEntry)
    } catch {
      focusEntry()
    }

    const onFocusIn = (event: FocusEvent) => {
      const dialog = dialogRef.current
      const target = event.target
      if (!dialog || !(target instanceof Node) || dialog.contains(target)) return
      focusEntry()
    }
    const scheduleFocusReturn = () => {
      if (focusOutTimer) window.clearTimeout(focusOutTimer)
      focusOutTimer = window.setTimeout(() => {
        const dialog = dialogRef.current
        const active = document.activeElement
        if (!dialog || (active instanceof Node && dialog.contains(active))) return
        focusEntry()
      }, 0)
    }
    const onDocumentKeyDown = (event: KeyboardEvent) => {
      handleModalKeyboardEvent(event, dialogRef.current, onEscape)
    }
    document.addEventListener('focusin', onFocusIn)
    document.addEventListener('focusout', scheduleFocusReturn, true)
    document.addEventListener('keydown', onDocumentKeyDown, true)

    return () => {
      if (focusOutTimer) window.clearTimeout(focusOutTimer)
      if (frameId) {
        try {
          window.cancelAnimationFrame(frameId)
        } catch {
          // Ignore environments without cancellable animation frames.
        }
      }
      document.removeEventListener('focusin', onFocusIn)
      document.removeEventListener('focusout', scheduleFocusReturn, true)
      document.removeEventListener('keydown', onDocumentKeyDown, true)
      const fallback = document.body instanceof HTMLElement ? document.body : null
      restoreModalFocus(previousFocusRef.current, fallback)
    }
  }, [dialogRef, enabled, onEscape])

  return useCallback((event: ReactKeyboardEvent<T>) => {
    if (!enabled) return
    handleModalKeyboardEvent(event, dialogRef.current, onEscape)
  }, [dialogRef, enabled, onEscape])
}
