export type FacetQueryState = 'pending' | 'error' | 'settled'

export type FacetFieldQueryStates = {
  metrics: Readonly<Record<string, FacetQueryState>>
  categoricals: Readonly<Record<string, FacetQueryState>>
}

export type FacetFieldState = 'pending' | 'error' | 'empty' | 'ready'
export type FacetDataState = 'absent' | 'empty' | 'ready'

export function facetFieldQueryState(
  fieldStates: FacetFieldQueryStates | undefined,
  kind: keyof FacetFieldQueryStates,
  key: string,
  fallback: FacetQueryState,
): FacetQueryState {
  if (!fieldStates) return fallback
  return fieldStates[kind][key] ?? 'pending'
}

export function resolveFacetFieldState({
  facetDataState,
  localDataState,
  queryState,
}: {
  facetDataState: FacetDataState
  localDataState: FacetDataState
  queryState: FacetQueryState
}): FacetFieldState {
  if (facetDataState !== 'absent') return facetDataState
  if (localDataState !== 'absent') return localDataState
  if (queryState === 'pending') return 'pending'
  if (queryState === 'error') return 'error'
  return 'empty'
}
