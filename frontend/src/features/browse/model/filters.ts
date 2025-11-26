import type { Item } from '../../../lib/types'

export function byStars(active: number[] | null) {
  return (it: Item) => {
    if (!active || !active.length) return true
    const val = it.star ?? 0
    return active.includes(val)
  }
}


