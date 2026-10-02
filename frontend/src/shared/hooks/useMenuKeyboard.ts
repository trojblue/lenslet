import { useCallback, useEffect, useLayoutEffect, useRef, type KeyboardEvent, type RefObject } from 'react'

const useBrowserLayoutEffect = typeof window === 'undefined' ? useEffect : useLayoutEffect

function menuItems(menu: HTMLElement): HTMLElement[] {
  return Array.from(menu.querySelectorAll<HTMLElement>('button, [role="menuitem"], [role="combobox"]'))
    .filter((item) => !item.matches(':disabled, [aria-disabled="true"]')
      && item.closest('[role="menu"]') === menu
      && !item.closest('[role="listbox"]')
      && item.getClientRects().length > 0)
}

function adjacentTabTarget(trigger: HTMLElement, menu: HTMLElement, backwards: boolean): HTMLElement {
  const dialog = trigger.closest<HTMLElement>('[role="dialog"][aria-modal="true"]')
  const scope = dialog ?? document.body
  const candidates = Array.from(scope.querySelectorAll<HTMLElement>('button, a[href], input, select, textarea, [tabindex]'))
    .filter((item) => item.tabIndex >= 0 && !menu.contains(item)
      && !item.matches(':disabled') && !item.closest('[inert], [hidden], [aria-hidden="true"]')
      && item.getClientRects().length > 0 && getComputedStyle(item).visibility !== 'hidden')
  const index = candidates.indexOf(trigger)
  const nextIndex = index + (backwards ? -1 : 1)
  if (index < 0 || !candidates.length) return trigger
  return candidates[nextIndex] ?? (dialog ? candidates[backwards ? candidates.length - 1 : 0] : trigger)
}

/** App-owned action menus share one keyboard model; nested fields keep theirs. */
export function useMenuKeyboard<T extends HTMLElement>(
  menuRef: RefObject<T>,
  { enabled, onClose, initialFocus = 'first' }: { enabled: boolean; onClose: () => void; initialFocus?: 'first' | 'last' },
): (event: KeyboardEvent<T>) => void {
  const closeRef = useRef(onClose)
  closeRef.current = onClose
  const typeahead = useRef({ text: '', time: 0 })
  const triggerRef = useRef<HTMLElement | null>(null)
  const exitFocusRef = useRef<HTMLElement | null>(null)

  const focusItem = useCallback((item: HTMLElement | undefined) => {
    const menu = menuRef.current
    if (!menu || !item) return
    for (const candidate of menuItems(menu)) candidate.tabIndex = candidate === item ? 0 : -1
    item.focus({ preventScroll: true })
    item.scrollIntoView({ block: 'nearest' })
  }, [menuRef])

  useBrowserLayoutEffect(() => {
    const menu = menuRef.current
    if (!enabled || !menu) return
    const previous = document.activeElement instanceof HTMLElement ? document.activeElement : null
    triggerRef.current = previous
    exitFocusRef.current = null
    typeahead.current = { text: '', time: 0 }
    const items = menuItems(menu)
    focusItem(initialFocus === 'last' ? items[items.length - 1] : items[0])
    return () => {
      const active = document.activeElement
      const restore = exitFocusRef.current ?? previous
      if (restore?.isConnected && !restore.closest('[hidden], [inert]')
        && (active === document.body || active instanceof Node && menu.contains(active))) {
        restore.focus({ preventScroll: true })
      }
    }
  }, [enabled, focusItem, initialFocus, menuRef])

  return useCallback((event: KeyboardEvent<T>) => {
    if (!enabled || event.defaultPrevented) return
    const menu = menuRef.current
    const target = event.target as HTMLElement
    if (!menu || target.closest('[role="listbox"]')) return
    if (event.key === 'Escape' || event.key === 'Tab') {
      event.preventDefault()
      if (event.key === 'Tab' && triggerRef.current) {
        exitFocusRef.current = adjacentTabTarget(triggerRef.current, menu, event.shiftKey)
      }
      event.stopPropagation()
      closeRef.current()
      return
    }
    if (target.matches('input, textarea, [contenteditable="true"]')) return
    const items = menuItems(menu)
    if (!items.length) return
    const index = items.indexOf(target)
    let next: HTMLElement | undefined
    if (event.key === 'ArrowDown') next = items[(index + 1) % items.length]
    else if (event.key === 'ArrowUp') next = items[(index - 1 + items.length) % items.length]
    else if (event.key === 'Home') next = items[0]
    else if (event.key === 'End') next = items[items.length - 1]
    else if (event.key.length === 1 && event.key !== ' ' && !event.ctrlKey && !event.metaKey && !event.altKey) {
      const now = Date.now()
      const prior = now - typeahead.current.time < 500 ? typeahead.current.text : ''
      const text = `${prior}${event.key}`.toLocaleLowerCase()
      typeahead.current = { text, time: now }
      const query = [...text].every((char) => char === text[0]) ? text[0] : text
      const ordered = [...items.slice(index + 1), ...items.slice(0, index + 1)]
      next = ordered.find((item) => (item.getAttribute('aria-label') ?? item.textContent ?? '').trim().toLocaleLowerCase().startsWith(query))
    } else return
    event.preventDefault()
    event.stopPropagation()
    focusItem(next)
  }, [enabled, focusItem, menuRef])
}
