import { describe, expect, it } from 'vitest'
import { formatMetricNumber } from '../util'

describe('formatMetricNumber', () => {
  it('formats metric values with stable threshold precision', () => {
    expect(formatMetricNumber(null)).toBe('–')
    expect(formatMetricNumber(Number.NaN)).toBe('–')
    expect(formatMetricNumber(1234.56)).toBe('1235')
    expect(formatMetricNumber(12.3456)).toBe('12.35')
    expect(formatMetricNumber(1.23456)).toBe('1.235')
  })
})
