import {
  type KeyboardEvent as ReactKeyboardEvent,
  type RefObject,
  useCallback,
  useEffect,
  useLayoutEffect,
  useRef,
} from 'react'
import { getModalRoots, registerModalScope, registerModalPopup } from './modalFocusScope'

const useBrowserLayoutEffect = typeof window === 'undefined' ? useEffect : useLayoutEffect

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

function isFocusableElementEnabled(element: HTMLElement): boolean {
  const style = window.getComputedStyle(element)
  return isModalFocusTargetEnabled({
    disabled: 'disabled' in element && Boolean(element.disabled),
    tabIndex: element.tabIndex,
    ariaHidden: Boolean(element.closest('[aria-hidden="true"], [inert], [hidden]')),
    rendered: element.getClientRects().length > 0,
    visible: style.display !== 'none' && style.visibility !== 'hidden',
  })
}

function chooseInitialModalElement(
  targets: readonly HTMLElement[],
  fallback: HTMLElement,
): HTMLElement {
  return targets.find(isFocusableElementEnabled) ?? fallback
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
    .filter(isFocusableElementEnabled)
}

function focusElement(element: HTMLElement | null): void {
  try {
    element?.focus({ preventScroll: true })
  } catch {
    element?.focus()
  }
}

function focusModalEntry(container: HTMLElement): void {
  const target = chooseInitialModalElement(getFocusableElements(container), container)
  focusElement(target)
}

function restoreModalFocus(target: HTMLElement | null, fallback: HTMLElement | null): void {
  focusElement(chooseRestoreFocusTarget(target, fallback))
}

export function useModalFocusTrap<T extends HTMLElement>(
  dialogRef: RefObject<T>,
  options: { enabled?: boolean; onEscape: () => void },
): (event: ReactKeyboardEvent<T>) => void {
  const { enabled = true, onEscape } = options
  const escapeRef = useRef(onEscape)
  escapeRef.current = onEscape
  const handleRef = useRef<(event: KeyboardEvent | ReactKeyboardEvent<T>) => void>(() => {})

  useBrowserLayoutEffect(() => {
    const dialog = dialogRef.current
    if (!enabled || !dialog) return
    const previous = document.activeElement instanceof HTMLElement ? document.activeElement : null
    const scope = registerModalScope(dialog)
    const roots = () => getModalRoots(dialog)
    const contains = (target: Node) => roots().some((root) => root.contains(target))
    const enter = () => focusModalEntry(dialog)
    enter()

    const onFocusIn = (event: FocusEvent) => {
      if (scope.isTop() && event.target instanceof Node && !contains(event.target)) enter()
    }
    const onKeyDown = (event: KeyboardEvent | ReactKeyboardEvent<T>) => {
      if (!scope.isTop() || event.defaultPrevented) return
      if (event.key === 'Escape') {
        // The innermost Dropdown receives Escape first, including its body portal.
        if (roots().length > 1) return
        event.preventDefault()
        event.stopPropagation()
        escapeRef.current()
      } else if (event.key === 'Tab') {
        const targets = roots().flatMap(getFocusableElements)
        const target = resolveModalTabTarget(targets, document.activeElement as HTMLElement, event.shiftKey)
        if (target || targets.length === 0) {
          event.preventDefault()
          focusElement(target ?? dialog)
        }
      }
    }
    handleRef.current = onKeyDown
    document.addEventListener('focusin', onFocusIn)
    document.addEventListener('keydown', onKeyDown)
    return () => {
      const restore = scope.isTop()
      document.removeEventListener('focusin', onFocusIn)
      document.removeEventListener('keydown', onKeyDown)
      handleRef.current = () => {}
      scope.release()
      if (restore) restoreModalFocus(previous, document.querySelector<HTMLElement>('main, [role="main"]'))
    }
  }, [dialogRef, enabled])

  return useCallback((event: ReactKeyboardEvent<T>) => handleRef.current(event), [])
}

/** Attach an explicitly opened context menu to the active sheet/modal lifetime. */
export function useModalOwnedPopup<T extends HTMLElement>(popupRef: RefObject<T>): void {
  useBrowserLayoutEffect(() => {
    const popup = popupRef.current
    if (popup) return registerModalPopup(popup)
  }, [popupRef])
}
