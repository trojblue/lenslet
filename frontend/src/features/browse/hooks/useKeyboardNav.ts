import type { BrowseItemPayload } from '../../../lib/types'

// Computes the next index for grid key navigation. Returns a number, 'open' for Enter, or null for unhandled.
export function getNextIndexForKeyNav(items: BrowseItemPayload[], columns: number, activePath: string | null, e: KeyboardEvent): number | 'open' | null {
  if (!items.length) return null
  const idx = activePath ? items.findIndex(i => i.path === activePath) : 0
  const col = Math.max(1, columns)
  let next = idx
  const normalized = e.key.toLowerCase()
  if (e.key === 'ArrowRight' || normalized === 'd') next = Math.min(items.length - 1, idx + 1)
  else if (e.key === 'ArrowLeft' || normalized === 'a') next = Math.max(0, idx - 1)
  else if (e.key === 'ArrowDown' || normalized === 's') next = Math.min(items.length - 1, idx + col)
  else if (e.key === 'ArrowUp' || normalized === 'w') next = Math.max(0, idx - col)
  else if (e.key === 'Enter') return activePath ? 'open' : null
  else return null
  return next
}

