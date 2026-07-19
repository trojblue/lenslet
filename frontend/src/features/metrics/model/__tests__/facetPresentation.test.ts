import { describe, expect, it } from 'vitest'
import {
  facetFieldQueryState,
  resolveFacetFieldPresentation,
  resolveFacetFieldPresentations,
  resolveFacetFieldState,
} from '../facetPresentation'

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

  it('retains one complete terminal field until the requested field settles', () => {
    const previous = {
      key: 'dataset_from',
      state: 'ready' as const,
      value: ['gt', 'synthetic'],
    }
    const pending = {
      key: 'review_group',
      state: 'pending' as const,
      value: [] as string[],
    }
    const ready = {
      key: 'review_group',
      state: 'ready' as const,
      value: ['review-0'],
    }

    expect(resolveFacetFieldPresentation(previous, pending)).toBe(previous)
    expect(resolveFacetFieldPresentation(previous, ready)).toBe(ready)
  })

  it('uses a neutral pending candidate when no terminal field exists yet', () => {
    const pending = {
      key: 'quality_score',
      state: 'pending' as const,
      value: [] as number[],
    }
    expect(resolveFacetFieldPresentation(null, pending)).toBe(pending)
  })

  it('does not retain a terminal field across an incompatible hard reset', () => {
    const previous = { key: 'source_a', state: 'ready' as const, value: ['a'] }
    const pending = { key: 'source_b', state: 'pending' as const, value: [] as string[] }

    expect(resolveFacetFieldPresentation(previous, pending, false)).toBe(pending)
  })

  it('keeps A through pending B and C, then promotes only terminal C', () => {
    const settledA = { key: 'a', state: 'ready' as const, value: ['a'] }
    const pendingB = { key: 'b', state: 'pending' as const, value: [] as string[] }
    const pendingC = { key: 'c', state: 'pending' as const, value: [] as string[] }
    const settledC = { key: 'c', state: 'ready' as const, value: ['c'] }

    expect(resolveFacetFieldPresentation(settledA, pendingB)).toBe(settledA)
    expect(resolveFacetFieldPresentation(settledA, pendingC)).toBe(settledA)
    expect(resolveFacetFieldPresentation(settledA, settledC)).toBe(settledC)
  })

  it('retains settled Show-all fields independently while first-ever fields stay neutral', () => {
    const settledA = { key: 'a', state: 'ready' as const, value: ['settled-a'] }
    const pendingA = { key: 'a', state: 'pending' as const, value: [] as string[] }
    const pendingB = { key: 'b', state: 'pending' as const, value: [] as string[] }

    const presentations = resolveFacetFieldPresentations(
      new Map([['a', settledA]]),
      [pendingA, pendingB],
    )

    expect(presentations.get('a')).toEqual({ presentation: settledA, retained: true })
    expect(presentations.get('b')).toEqual({ presentation: pendingB, retained: false })
  })

  it('clears every retained Show-all field at an incompatible hard reset', () => {
    const settledA = { key: 'a', state: 'ready' as const, value: ['settled-a'] }
    const pendingA = { key: 'a', state: 'pending' as const, value: [] as string[] }

    const presentations = resolveFacetFieldPresentations(
      new Map([['a', settledA]]),
      [pendingA],
      false,
    )

    expect(presentations.get('a')).toEqual({ presentation: pendingA, retained: false })
  })
})
