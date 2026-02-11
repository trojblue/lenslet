import { describe, expect, it } from 'vitest'
import type { Range } from '../../model/histogram'
import {
  didPointerDrag,
  histogramValueFromClientX,
  rangeFromDrag,
  resolvePointerUpOutcome,
} from '../useMetricHistogramInteraction'

describe('metrics histogram interaction helpers', () => {
  it('maps client x to histogram values with clamping', () => {
    const domain = { min: 0, max: 100 }
    const rect = { left: 10, width: 200 }

    expect(histogramValueFromClientX(-20, rect, domain)).toBe(0)
    expect(histogramValueFromClientX(110, rect, domain)).toBe(50)
    expect(histogramValueFromClientX(260, rect, domain)).toBe(100)
  })

  it('keeps drag threshold behavior and null-safe starts', () => {
    expect(didPointerDrag(null, 20)).toBe(false)
    expect(didPointerDrag(10, 13)).toBe(false)
    expect(didPointerDrag(10, 14)).toBe(true)
  })

  it('normalizes drag ranges regardless of pointer direction', () => {
    expect(rangeFromDrag(8, 2)).toEqual({ min: 2, max: 8 })
    expect(rangeFromDrag(2, 8)).toEqual({ min: 2, max: 8 })
    expect(rangeFromDrag(null, 4)).toEqual({ min: 4, max: 4 })
  })

  it('resolves pointer-up outcomes for drag commit and click-clear flows', () => {
    const activeRange: Range = { min: 1, max: 9 }

    expect(resolvePointerUpOutcome(true, 3, 8, activeRange)).toEqual({
      commitRange: { min: 3, max: 8 },
      shouldClear: false,
    })
    expect(resolvePointerUpOutcome(false, 3, 8, activeRange)).toEqual({
      commitRange: null,
      shouldClear: true,
    })
    expect(resolvePointerUpOutcome(false, 3, 8, null)).toEqual({
      commitRange: null,
      shouldClear: false,
    })
  })
})
