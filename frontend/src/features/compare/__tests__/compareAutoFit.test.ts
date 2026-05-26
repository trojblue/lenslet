import { describe, expect, it } from 'vitest'
import { buildComparePairKey, shouldAutoFitComparePair } from '../compareAutoFit'

describe('compare auto-fit guards', () => {
  it('builds no pair key until both paths are present', () => {
    expect(buildComparePairKey('/a.png', null)).toBeNull()
    expect(buildComparePairKey(null, '/b.png')).toBeNull()
    expect(buildComparePairKey('/a.png', '/b.png')).toBe('/a.png\u0000/b.png')
  })

  it('allows the initial fit only after both current images have loaded', () => {
    expect(shouldAutoFitComparePair({
      aPath: '/a.png',
      bPath: '/b.png',
      loadedAPath: '/a.png',
      loadedBPath: null,
      fittedPairKey: null,
      userInteracted: false,
    })).toBe(false)
    expect(shouldAutoFitComparePair({
      aPath: '/a.png',
      bPath: '/b.png',
      loadedAPath: '/a.png',
      loadedBPath: '/b.png',
      fittedPairKey: null,
      userInteracted: false,
    })).toBe(true)
  })

  it('blocks late-load fitting after user interaction or a prior pair fit', () => {
    const pairKey = buildComparePairKey('/a.png', '/b.png')
    expect(shouldAutoFitComparePair({
      aPath: '/a.png',
      bPath: '/b.png',
      loadedAPath: '/a.png',
      loadedBPath: '/b.png',
      fittedPairKey: null,
      userInteracted: true,
    })).toBe(false)
    expect(shouldAutoFitComparePair({
      aPath: '/a.png',
      bPath: '/b.png',
      loadedAPath: '/a.png',
      loadedBPath: '/b.png',
      fittedPairKey: pairKey,
      userInteracted: false,
    })).toBe(false)
  })
})
