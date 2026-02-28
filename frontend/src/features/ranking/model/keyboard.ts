export type RankingKeyAction =
  | { type: 'assign-rank'; rankIndex: number }
  | { type: 'select-neighbor'; direction: 'left' | 'right' }
  | { type: 'instance-nav'; direction: 'prev' | 'next' }
  | { type: 'fullscreen-nav'; direction: 'prev' | 'next' }
  | { type: 'fullscreen-open' }
  | { type: 'fullscreen-close' }
  | { type: 'none' }

export type RankingHotkeyTarget = {
  isContentEditable: boolean
  tagName: string | null
  insideInteractiveControl: boolean
}

function parseRankIndex(key: string, maxRanks: number): number | null {
  if (key < '1' || key > '9') return null
  const rankIndex = Number(key) - 1
  if (rankIndex >= maxRanks) return null
  return rankIndex
}

export function shouldIgnoreRankingHotkey(
  key: string,
  target: RankingHotkeyTarget,
): boolean {
  if (target.isContentEditable) return true

  const tag = target.tagName?.toLowerCase() ?? ''
  if (tag === 'input' || tag === 'textarea' || tag === 'select') {
    return true
  }
  if (key === 'Enter' && target.insideInteractiveControl) {
    return true
  }
  return false
}

export function getBoardKeyAction(key: string, maxRanks: number): RankingKeyAction {
  const rankIndex = parseRankIndex(key, maxRanks)
  if (rankIndex != null) {
    return { type: 'assign-rank', rankIndex }
  }

  if (key === 'ArrowLeft') return { type: 'select-neighbor', direction: 'left' }
  if (key === 'ArrowRight') return { type: 'select-neighbor', direction: 'right' }
  if (key === 'Enter') return { type: 'fullscreen-open' }

  const normalized = key.toLowerCase()
  if (normalized === 'q') return { type: 'instance-nav', direction: 'prev' }
  if (normalized === 'e') return { type: 'instance-nav', direction: 'next' }

  return { type: 'none' }
}

export function getFullscreenKeyAction(key: string, maxRanks: number): RankingKeyAction {
  const rankIndex = parseRankIndex(key, maxRanks)
  if (rankIndex != null) {
    return { type: 'assign-rank', rankIndex }
  }

  if (key === 'Escape') return { type: 'fullscreen-close' }

  const normalized = key.toLowerCase()
  if (normalized === 'a') return { type: 'fullscreen-nav', direction: 'prev' }
  if (normalized === 'd') return { type: 'fullscreen-nav', direction: 'next' }

  return { type: 'none' }
}
