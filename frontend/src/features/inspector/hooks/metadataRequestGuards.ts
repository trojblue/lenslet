type ShouldApplyMetadataResponseParams = {
  activeRequestId: number
  responseRequestId: number
  activeContextKey: string | null
  responseContextKey: string | null
}

export const MAX_INSPECTOR_COMPARE_PATHS = 6

export interface CompareMetadataTargets {
  paths: string[]
  truncatedCount: number
}

export function buildSingleMetadataContextKey(
  path: string | null,
  sidecarUpdatedAt: string | undefined,
): string | null {
  if (!path) return null
  return `${path}::${sidecarUpdatedAt ?? ''}`
}

function normalizedComparePaths(comparePaths: readonly string[]): string[] {
  const normalized: string[] = []
  for (const path of comparePaths) {
    if (path === '') continue
    normalized.push(path)
  }
  return normalized
}

export function resolveCompareMetadataTargets(
  compareReady: boolean,
  comparePaths: readonly string[],
): CompareMetadataTargets {
  if (!compareReady) return { paths: [], truncatedCount: 0 }
  const normalizedPaths = normalizedComparePaths(comparePaths)
  const paths = normalizedPaths.slice(0, MAX_INSPECTOR_COMPARE_PATHS)
  const truncatedCount = Math.max(0, normalizedPaths.length - paths.length)
  return { paths, truncatedCount }
}

export function buildCompareMetadataContextKey(
  compareReady: boolean,
  comparePaths: readonly string[],
): string | null {
  const targets = resolveCompareMetadataTargets(compareReady, comparePaths)
  if (targets.paths.length < 2) return null
  return targets.paths.join('::')
}

export function shouldApplyMetadataResponse({
  activeRequestId,
  responseRequestId,
  activeContextKey,
  responseContextKey,
}: ShouldApplyMetadataResponseParams): boolean {
  return activeRequestId === responseRequestId && activeContextKey === responseContextKey
}
