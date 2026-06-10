import { describe, expect, it } from 'vitest'
import { resolveGridStatus, shouldShowGridLoading } from '../loadingState'

describe('grid loading visibility', () => {
  it('shows loading while initial folder query is pending with no items', () => {
    expect(shouldShowGridLoading({
      similarityActive: false,
      searching: false,
      itemCount: 0,
      isLoading: true,
    })).toBe(true)
  })

  it('hides loading once any item is visible', () => {
    expect(shouldShowGridLoading({
      similarityActive: false,
      searching: false,
      itemCount: 1,
      isLoading: true,
    })).toBe(false)
  })

  it('hides loading in similarity and search modes', () => {
    expect(shouldShowGridLoading({
      similarityActive: true,
      searching: false,
      itemCount: 0,
      isLoading: true,
    })).toBe(false)

    expect(shouldShowGridLoading({
      similarityActive: false,
      searching: true,
      itemCount: 0,
      isLoading: true,
    })).toBe(false)
  })
})

describe('grid status state', () => {
  it('keeps old rows visible while a committed query is updating', () => {
    expect(resolveGridStatus({
      similarityActive: false,
      searching: false,
      itemCount: 24,
      isLoading: false,
      isFetching: true,
    })).toMatchObject({
      kind: 'updating',
      showCentered: false,
    })
  })

  it('reports unsupported and failed queries separately from empty results', () => {
    expect(resolveGridStatus({
      similarityActive: false,
      searching: false,
      itemCount: 0,
      isLoading: false,
      unavailableReason: 'Derived metric inputs are missing.',
    })).toMatchObject({
      kind: 'unsupported',
      title: 'Query unavailable',
      showCentered: true,
    })

    expect(resolveGridStatus({
      similarityActive: false,
      searching: false,
      itemCount: 0,
      isLoading: false,
      isError: true,
    })).toMatchObject({
      kind: 'failed',
      title: 'Query failed',
      showCentered: true,
    })
  })

  it('distinguishes empty search results from initial loading', () => {
    expect(resolveGridStatus({
      similarityActive: false,
      searching: true,
      itemCount: 0,
      isLoading: false,
      filteredCount: 0,
    })).toMatchObject({
      kind: 'empty',
      message: 'No filenames, tags, or notes match this search.',
    })
  })

  it('shows pending searches as loading instead of false empty', () => {
    expect(resolveGridStatus({
      similarityActive: false,
      searching: true,
      itemCount: 0,
      isLoading: true,
    })).toMatchObject({
      kind: 'loading',
      title: 'Loading gallery...',
    })
  })
})
