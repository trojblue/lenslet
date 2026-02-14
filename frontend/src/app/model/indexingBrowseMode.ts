type IndexingSignal = {
  state: 'idle' | 'running' | 'ready' | 'error'
  generation?: string
} | null

export type IndexingBrowseModeState = {
  scanGeneration: string | null
  recentGeneration: string | null
}

export type IndexingBrowseMode = {
  scanStableActive: boolean
  sortLocked: boolean
  showSwitchToMostRecentBanner: boolean
}

export function normalizeIndexingGeneration(value: unknown): string | null {
  if (typeof value !== 'string') return null
  const trimmed = value.trim()
  return trimmed.length ? trimmed : null
}

export function captureScanGeneration(
  currentScanGeneration: string | null,
  indexing: IndexingSignal,
): string | null {
  const generation = normalizeIndexingGeneration(indexing?.generation)
  if (!generation) return currentScanGeneration
  if (currentScanGeneration === null) {
    return generation
  }
  if (indexing?.state === 'idle' || indexing?.state === 'running') {
    return generation
  }
  return currentScanGeneration
}

export function deriveIndexingBrowseMode(
  indexing: IndexingSignal,
  state: IndexingBrowseModeState,
): IndexingBrowseMode {
  const indexedGeneration = normalizeIndexingGeneration(indexing?.generation)
  const generation = indexedGeneration ?? (indexing?.state === 'ready' ? state.scanGeneration : null)
  const scanStableActive = (
    generation !== null
    && state.scanGeneration === generation
    && state.recentGeneration !== generation
  )
  const showSwitchToMostRecentBanner = scanStableActive && indexing?.state === 'ready'
  return {
    scanStableActive,
    sortLocked: scanStableActive,
    showSwitchToMostRecentBanner,
  }
}
