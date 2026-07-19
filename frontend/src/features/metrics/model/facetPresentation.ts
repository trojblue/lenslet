import { useEffect, useLayoutEffect, useRef } from 'react'

export type FacetQueryState = 'pending' | 'error' | 'settled'

export type FacetFieldQueryStates = {
  metrics: Readonly<Record<string, FacetQueryState>>
  categoricals: Readonly<Record<string, FacetQueryState>>
}

export type FacetFieldState = 'pending' | 'error' | 'empty' | 'ready'
export type FacetDataState = 'absent' | 'empty' | 'ready'

export type FacetFieldPresentation<T> = {
  key: string
  state: FacetFieldState
  value: T
}

export type FacetFieldPresentationResult<T> = {
  presentation: FacetFieldPresentation<T>
  retained: boolean
}

export const usePrepaintEffect = typeof window === 'undefined' ? useEffect : useLayoutEffect

export function resolveFacetFieldPresentation<T>(
  previous: FacetFieldPresentation<T> | null,
  candidate: FacetFieldPresentation<T>,
  compatible = true,
): FacetFieldPresentation<T> {
  return compatible && candidate.state === 'pending' && previous ? previous : candidate
}

export function useFacetFieldPresentation<T>(
  candidate: FacetFieldPresentation<T>,
  resetKey = 'default',
): {
  presentation: FacetFieldPresentation<T>
  retained: boolean
} {
  const ownerRef = useRef({
    resetKey,
    terminal: candidate.state === 'pending' ? null : candidate,
  })
  const compatible = ownerRef.current.resetKey === resetKey
  const terminal = compatible ? ownerRef.current.terminal : null
  const presentation = resolveFacetFieldPresentation(terminal, candidate, compatible)

  usePrepaintEffect(() => {
    if (ownerRef.current.resetKey !== resetKey) {
      ownerRef.current = {
        resetKey,
        terminal: candidate.state === 'pending' ? null : candidate,
      }
    } else if (candidate.state !== 'pending') {
      ownerRef.current.terminal = candidate
    }
  }, [candidate, resetKey])

  return {
    presentation,
    retained: compatible && candidate.state === 'pending' && terminal !== null,
  }
}

export function resolveFacetFieldPresentations<T>(
  previous: ReadonlyMap<string, FacetFieldPresentation<T>>,
  candidates: readonly FacetFieldPresentation<T>[],
  compatible = true,
): Map<string, FacetFieldPresentationResult<T>> {
  return new Map(candidates.map((candidate) => {
    const terminal = compatible ? previous.get(candidate.key) ?? null : null
    return [candidate.key, {
      presentation: resolveFacetFieldPresentation(terminal, candidate, compatible),
      retained: compatible && candidate.state === 'pending' && terminal !== null,
    }]
  }))
}

export function useFacetFieldPresentations<T>(
  candidates: readonly FacetFieldPresentation<T>[],
  validKeys: readonly string[],
  resetKey = 'default',
): Map<string, FacetFieldPresentationResult<T>> {
  const ownerRef = useRef<{
    resetKey: string
    terminal: Map<string, FacetFieldPresentation<T>>
  }>({ resetKey, terminal: new Map() })
  const compatible = ownerRef.current.resetKey === resetKey
  const presentations = resolveFacetFieldPresentations(
    ownerRef.current.terminal,
    candidates,
    compatible,
  )

  usePrepaintEffect(() => {
    if (ownerRef.current.resetKey !== resetKey) {
      ownerRef.current = { resetKey, terminal: new Map() }
    }
    const valid = new Set(validKeys)
    for (const key of ownerRef.current.terminal.keys()) {
      if (!valid.has(key)) ownerRef.current.terminal.delete(key)
    }
    for (const candidate of candidates) {
      if (candidate.state !== 'pending') {
        ownerRef.current.terminal.set(candidate.key, candidate)
      }
    }
  }, [candidates, resetKey, validKeys])

  return presentations
}

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
