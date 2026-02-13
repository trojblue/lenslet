import { describe, expect, it } from 'vitest'
import { shouldShowGridHydrationLoading } from '../loadingState'

describe('grid hydration loading visibility', () => {
  it('shows loading when browse hydration is pending with no visible items', () => {
    expect(shouldShowGridHydrationLoading({
      similarityActive: false,
      searching: false,
      itemCount: 0,
      isLoading: false,
      browseHydrationPending: true,
    })).toBe(true)
  })

  it('shows loading while initial folder query is pending with no items', () => {
    expect(shouldShowGridHydrationLoading({
      similarityActive: false,
      searching: false,
      itemCount: 0,
      isLoading: true,
      browseHydrationPending: false,
    })).toBe(true)
  })

  it('hides loading once any item is visible', () => {
    expect(shouldShowGridHydrationLoading({
      similarityActive: false,
      searching: false,
      itemCount: 1,
      isLoading: true,
      browseHydrationPending: true,
    })).toBe(false)
  })

  it('hides loading in similarity and search modes', () => {
    expect(shouldShowGridHydrationLoading({
      similarityActive: true,
      searching: false,
      itemCount: 0,
      isLoading: true,
      browseHydrationPending: true,
    })).toBe(false)

    expect(shouldShowGridHydrationLoading({
      similarityActive: false,
      searching: true,
      itemCount: 0,
      isLoading: true,
      browseHydrationPending: true,
    })).toBe(false)
  })
})
