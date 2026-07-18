import { describe, expect, it } from 'vitest'
import { facetFieldQueryState, resolveFacetFieldState } from '../facetPresentation'

describe('facet field presentation', () => {
  it('keeps unrequested fields pending but preserves explicit settled ownership', () => {
    const states = {
      metrics: { settled_metric: 'settled' as const },
      categoricals: {},
    }
    expect(facetFieldQueryState(states, 'metrics', 'new_metric', 'settled')).toBe('pending')
    expect(facetFieldQueryState(states, 'metrics', 'settled_metric', 'pending')).toBe('settled')
  })

  it('keeps settled same-field data ready during refetch', () => {
    expect(resolveFacetFieldState({
      facetDataState: 'ready',
      localDataState: 'absent',
      queryState: 'pending',
    })).toBe('ready')
    expect(resolveFacetFieldState({
      facetDataState: 'empty',
      localDataState: 'absent',
      queryState: 'pending',
    })).toBe('empty')
  })

  it('treats a field omitted by its settled batch as empty', () => {
    expect(resolveFacetFieldState({
      facetDataState: 'absent',
      localDataState: 'absent',
      queryState: 'settled',
    })).toBe('empty')
  })

  it('reports terminal field errors without discarding complete local data', () => {
    expect(resolveFacetFieldState({
      facetDataState: 'absent',
      localDataState: 'absent',
      queryState: 'error',
    })).toBe('error')
    expect(resolveFacetFieldState({
      facetDataState: 'absent',
      localDataState: 'ready',
      queryState: 'error',
    })).toBe('ready')
    expect(resolveFacetFieldState({
      facetDataState: 'absent',
      localDataState: 'empty',
      queryState: 'pending',
    })).toBe('empty')
  })
})
