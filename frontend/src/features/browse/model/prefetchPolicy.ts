export const VIEWER_FILE_PREFETCH_OFFSETS = [-2, -1, 1, 2] as const
export const COMPARE_FILE_PREFETCH_OFFSETS = [-2, -1, 0, 1, 2, 3] as const

export const MAX_VIEWER_FILE_PREFETCH = VIEWER_FILE_PREFETCH_OFFSETS.length
export const MAX_COMPARE_FILE_PREFETCH = COMPARE_FILE_PREFETCH_OFFSETS.length

function clamp(value: number, min: number, max: number): number {
  return Math.min(Math.max(value, min), max)
}

function collectPrefetchPaths(
  paths: readonly string[],
  centerIndex: number,
  offsets: readonly number[],
): string[] {
  const seen = new Set<string>()
  const result: string[] = []
  for (const offset of offsets) {
    const idx = centerIndex + offset
    if (idx < 0 || idx >= paths.length) continue
    const path = paths[idx]
    if (!path || seen.has(path)) continue
    seen.add(path)
    result.push(path)
  }
  return result
}

export function getViewerFilePrefetchPaths(
  itemPaths: readonly string[],
  viewerPath: string | null,
): string[] {
  if (!viewerPath) return []
  const idx = itemPaths.indexOf(viewerPath)
  if (idx < 0) return []
  return collectPrefetchPaths(itemPaths, idx, VIEWER_FILE_PREFETCH_OFFSETS)
}

export function getCompareFilePrefetchPaths(
  comparePaths: readonly string[],
  compareIndex: number,
): string[] {
  if (comparePaths.length < 2) return []
  const maxPairIndex = Math.max(0, comparePaths.length - 2)
  const clampedIndex = clamp(compareIndex, 0, maxPairIndex)
  return collectPrefetchPaths(comparePaths, clampedIndex, COMPARE_FILE_PREFETCH_OFFSETS)
}
