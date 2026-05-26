export type CompareAutoFitState = {
  aPath: string | null
  bPath: string | null
  loadedAPath: string | null
  loadedBPath: string | null
  fittedPairKey: string | null
  userInteracted: boolean
}

export function buildComparePairKey(aPath: string | null, bPath: string | null): string | null {
  if (!aPath || !bPath) return null
  return `${aPath}\u0000${bPath}`
}

export function shouldAutoFitComparePair(state: CompareAutoFitState): boolean {
  const pairKey = buildComparePairKey(state.aPath, state.bPath)
  return pairKey !== null
    && state.fittedPairKey !== pairKey
    && !state.userInteracted
    && state.loadedAPath === state.aPath
    && state.loadedBPath === state.bPath
}
