import { describe, expect, it } from 'vitest'
import { shouldShowGridLoading } from '../loadingState'

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
