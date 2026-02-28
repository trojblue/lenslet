export const RANKING_SPLITTER_HEIGHT_PX = 10
export const RANKING_DEFAULT_UNRANKED_HEIGHT_PX = 200
export const RANKING_MIN_UNRANKED_HEIGHT_PX = 120
export const RANKING_MIN_RANKS_HEIGHT_PX = 180

function toFiniteNumber(value: number, fallback: number): number {
  return Number.isFinite(value) ? value : fallback
}

export function clampUnrankedHeightPx(
  requestedTopPx: number,
  totalHeightPx: number,
  options?: {
    minTopPx?: number
    minBottomPx?: number
    splitterPx?: number
  },
): number {
  const splitterPx = Math.max(
    0,
    Math.trunc(toFiniteNumber(options?.splitterPx ?? RANKING_SPLITTER_HEIGHT_PX, 0)),
  )
  const minTopPx = Math.max(
    0,
    Math.trunc(toFiniteNumber(options?.minTopPx ?? RANKING_MIN_UNRANKED_HEIGHT_PX, 0)),
  )
  const minBottomPx = Math.max(
    0,
    Math.trunc(toFiniteNumber(options?.minBottomPx ?? RANKING_MIN_RANKS_HEIGHT_PX, 0)),
  )

  const total = Math.max(0, Math.trunc(toFiniteNumber(totalHeightPx, 0)))
  const available = Math.max(0, total - splitterPx)
  if (available === 0) return 0

  const maxTop = Math.max(0, available - minBottomPx)
  const minTop = Math.min(minTopPx, maxTop)
  const requested = Math.trunc(toFiniteNumber(requestedTopPx, minTop))
  return Math.min(maxTop, Math.max(minTop, requested))
}
