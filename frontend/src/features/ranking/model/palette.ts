export const RANKING_DOT_COLORS = [
  '#f97316',
  '#eab308',
  '#22c55e',
  '#14b8a6',
  '#3b82f6',
  '#6366f1',
  '#ec4899',
  '#ef4444',
] as const

export function buildDotColorByImageId(initialOrder: string[]): Record<string, string> {
  const dotColorByImageId: Record<string, string> = {}
  const seen = new Set<string>()
  let colorIndex = 0

  for (const imageId of initialOrder) {
    if (seen.has(imageId)) continue
    seen.add(imageId)
    dotColorByImageId[imageId] = RANKING_DOT_COLORS[colorIndex % RANKING_DOT_COLORS.length]
    colorIndex += 1
  }

  return dotColorByImageId
}
