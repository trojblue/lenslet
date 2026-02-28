import { describe, expect, it } from 'vitest'
import {
  RANKING_MIN_RANKS_HEIGHT_PX,
  RANKING_MIN_UNRANKED_HEIGHT_PX,
  RANKING_SPLITTER_HEIGHT_PX,
  clampUnrankedHeightPx,
} from '../layout'

describe('ranking splitter layout clamps', () => {
  it('clamps top section to minimum when requested below bounds', () => {
    const clamped = clampUnrankedHeightPx(80, 760)
    expect(clamped).toBe(RANKING_MIN_UNRANKED_HEIGHT_PX)
  })

  it('clamps top section to maximum while preserving minimum ranks section', () => {
    const available = 760 - RANKING_SPLITTER_HEIGHT_PX
    const expectedMax = available - RANKING_MIN_RANKS_HEIGHT_PX
    const clamped = clampUnrankedHeightPx(999, 760)
    expect(clamped).toBe(expectedMax)
  })

  it('returns requested value when it is inside bounds', () => {
    const clamped = clampUnrankedHeightPx(360, 760)
    expect(clamped).toBe(360)
  })

  it('degrades gracefully on small containers', () => {
    const clamped = clampUnrankedHeightPx(240, 360)
    expect(clamped).toBe(170)
  })

  it('normalizes non-finite input values', () => {
    const clamped = clampUnrankedHeightPx(Number.NaN, Number.NaN)
    expect(clamped).toBe(0)
  })
})
