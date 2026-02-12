type ShouldApplyMetadataResponseParams = {
  activeRequestId: number
  responseRequestId: number
  activeContextKey: string | null
  responseContextKey: string | null
}

export function buildSingleMetadataContextKey(
  path: string | null,
  sidecarUpdatedAt: string | undefined,
): string | null {
  if (!path) return null
  return `${path}::${sidecarUpdatedAt ?? ''}`
}

export function buildCompareMetadataContextKey(
  compareReady: boolean,
  comparePathA: string | null,
  comparePathB: string | null,
): string | null {
  if (!compareReady || !comparePathA || !comparePathB) return null
  return `${comparePathA}::${comparePathB}`
}

export function shouldApplyMetadataResponse({
  activeRequestId,
  responseRequestId,
  activeContextKey,
  responseContextKey,
}: ShouldApplyMetadataResponseParams): boolean {
  return activeRequestId === responseRequestId && activeContextKey === responseContextKey
}
