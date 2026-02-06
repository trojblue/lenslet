import { describe, expect, it } from 'vitest'
import { deriveIndicatorState } from '../presenceUi'

describe('deriveIndicatorState', () => {
  it('prioritizes offline over every other signal', () => {
    expect(deriveIndicatorState({
      isOffline: true,
      isUnstable: true,
      recentEditActive: true,
      editingCount: 4,
    })).toBe('offline')
  })

  it('prioritizes unstable over recent and editing when online', () => {
    expect(deriveIndicatorState({
      isOffline: false,
      isUnstable: true,
      recentEditActive: true,
      editingCount: 2,
    })).toBe('unstable')
  })

  it('prioritizes recent over editing when connection is stable', () => {
    expect(deriveIndicatorState({
      isOffline: false,
      isUnstable: false,
      recentEditActive: true,
      editingCount: 5,
    })).toBe('recent')
  })

  it('returns editing only when server editing count is positive', () => {
    expect(deriveIndicatorState({
      isOffline: false,
      isUnstable: false,
      recentEditActive: false,
      editingCount: 1,
    })).toBe('editing')
    expect(deriveIndicatorState({
      isOffline: false,
      isUnstable: false,
      recentEditActive: false,
      editingCount: 0,
    })).toBe('live')
  })

  it('treats invalid editing counts as not editing', () => {
    expect(deriveIndicatorState({
      isOffline: false,
      isUnstable: false,
      recentEditActive: false,
      editingCount: Number.NaN,
    })).toBe('live')
  })
})
