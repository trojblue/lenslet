/** The active modal owns background inertness and any popup its controls expose. */
type ModalScope = { element: HTMLElement; popups: Set<HTMLElement> }
const scopes: ModalScope[] = []
const inertBefore = new Map<HTMLElement, boolean>()

export function getModalRoots(element: HTMLElement): HTMLElement[] {
  const scope = scopes.find((item) => item.element === element)
  const roots = [element, ...(scope?.popups ?? [])]
  for (let index = 0; index < roots.length; index += 1) {
    for (const trigger of roots[index].querySelectorAll('[aria-controls][aria-expanded="true"]')) {
      for (const id of (trigger.getAttribute('aria-controls') ?? '').split(/\s+/)) {
        const panel = document.getElementById(id)
        if (panel && !roots.some((root) => root.contains(panel))) roots.push(panel)
      }
    }
  }
  return roots
}

function restoreInert(): void {
  for (const [element, wasInert] of inertBefore) element.toggleAttribute('inert', wasInert)
  inertBefore.clear()
}

function refreshInert(): void {
  restoreInert()
  const scope = scopes[scopes.length - 1]
  if (!scope) return
  const roots = getModalRoots(scope.element)
  const visit = (parent: HTMLElement) => {
    for (const child of parent.children) {
      if (!(child instanceof HTMLElement) || ['SCRIPT', 'STYLE', 'LINK'].includes(child.tagName)) continue
      if (roots.includes(child)) continue
      if (roots.some((root) => child.contains(root))) {
        visit(child)
      } else {
        inertBefore.set(child, child.hasAttribute('inert'))
        child.setAttribute('inert', '')
      }
    }
  }
  visit(document.body)
}

export function registerModalScope(element: HTMLElement): {
  isTop: () => boolean
  release: () => void
} {
  const scope: ModalScope = { element, popups: new Set() }
  scopes.push(scope)
  refreshInert()
  // Dropdowns portal to body. Their aria-controls relationship defines ownership.
  const observer = new MutationObserver(refreshInert)
  observer.observe(document.body, {
    childList: true,
    subtree: true,
    attributes: true,
    attributeFilter: ['aria-controls', 'aria-expanded'],
  })
  return {
    isTop: () => scopes[scopes.length - 1] === scope,
    release: () => {
      observer.disconnect()
      const index = scopes.indexOf(scope)
      if (index !== -1) scopes.splice(index, 1)
      refreshInert()
    },
  }
}

/** Context menus have no persistent trigger. Register that specific surface only. */
export function registerModalPopup(element: HTMLElement): () => void {
  const scope = scopes[scopes.length - 1]
  if (!scope) return () => {}
  scope.popups.add(element)
  refreshInert()
  return () => {
    scope.popups.delete(element)
    refreshInert()
  }
}
