import { describe, expect, it } from 'vitest'
import {
  clamp,
  clamp01,
  computeHistogramFromValues,
  formatInputValue,
  formatNumber,
  histogramBarHeights,
  isApprox,
  normalizeRange,
  parseNumberInput,
} from '../histogram'

describe('metrics histogram model utilities', () => {
  it('returns null histogram for empty values', () => {
    expect(computeHistogramFromValues([], 40)).toBeNull()
  })

  it('expands degenerate domains where min equals max', () => {
    const histogram = computeHistogramFromValues([7, 7, 7], 4)

    expect(histogram).not.toBeNull()
    expect(histogram?.min).toBe(7)
    expect(histogram?.max).toBe(8)
    expect(histogram?.count).toBe(3)
    expect(histogram?.bins).toEqual([3, 0, 0, 0])
  })

  it('bins large metric populations without exceeding the argument limit', () => {
    const values = Array.from({ length: 250_000 }, (_, index) => index % 1000 - 500)
    const originalFirst = values[0]
    const originalLast = values[values.length - 1]
    const histogram = computeHistogramFromValues(values, 10)

    expect(histogram).toEqual({
      bins: Array(10).fill(25_000),
      min: -500,
      max: 499,
      count: 250_000,
    })
    expect(values[0]).toBe(originalFirst)
    expect(values[values.length - 1]).toBe(originalLast)
  })

  it('clamps large filtered populations to the unchanged base domain', () => {
    const values = Array.from({ length: 250_000 }, (_, index) => index % 2 ? 20 : -10)
    const base = { bins: [1, 1], min: 0, max: 10, count: 2 }

    expect(computeHistogramFromValues(values, 2, base)).toEqual({
      bins: [125_000, 125_000], min: 0, max: 10, count: 250_000,
    })
    expect(base).toEqual({ bins: [1, 1], min: 0, max: 10, count: 2 })
  })

  it('preserves signed-zero extrema when expanding a constant domain', () => {
    expect(computeHistogramFromValues([0, -0], 2)).toEqual({
      bins: [2, 0], min: -0, max: 1, count: 2,
    })
  })

  it('reuses base histogram domain for secondary histograms', () => {
    const population = computeHistogramFromValues([0, 10], 5)
    const filtered = computeHistogramFromValues([10], 5, population ?? undefined)

    expect(population?.bins).toEqual([1, 0, 0, 0, 1])
    expect(filtered).not.toBeNull()
    expect(filtered?.min).toBe(0)
    expect(filtered?.max).toBe(10)
    expect(filtered?.bins).toEqual([0, 0, 0, 0, 1])
  })

  it('keeps secondary histogram bars on the population vertical scale', () => {
    expect(histogramBarHeights([0, 5, 10], 20)).toEqual([0, 25, 50])
  })

  it('normalizes ranges regardless of drag direction', () => {
    expect(normalizeRange(8, 2)).toEqual({ min: 2, max: 8 })
    expect(normalizeRange(-4, 3)).toEqual({ min: -4, max: 3 })
  })

  it('formats numbers with stable threshold precision', () => {
    expect(formatNumber(null)).toBe('–')
    expect(formatNumber(1234.56)).toBe('1235')
    expect(formatNumber(12.3456)).toBe('12.35')
    expect(formatNumber(1.23456)).toBe('1.235')
  })

  it('formats and parses numeric input fields', () => {
    expect(formatInputValue(1e-6)).toBe('0.000001')
    expect(formatInputValue(12.5)).toBe('12.5')
    expect(parseNumberInput('')).toEqual({ value: null, valid: true })
    expect(parseNumberInput('  9.5 ')).toEqual({ value: 9.5, valid: true })
    expect(parseNumberInput('not-a-number')).toEqual({ value: null, valid: false })
    expect(parseNumberInput('Infinity')).toEqual({ value: null, valid: false })
  })

  it('clamps values and approximates floating-point comparisons', () => {
    expect(clamp(-3, 0, 5)).toBe(0)
    expect(clamp(7, 0, 5)).toBe(5)
    expect(clamp(3, 0, 5)).toBe(3)
    expect(clamp01(-0.2)).toBe(0)
    expect(clamp01(0.6)).toBe(0.6)
    expect(clamp01(1.2)).toBe(1)
    expect(isApprox(1_000_000, 1_000_000.5)).toBe(true)
    expect(isApprox(1, 1.01)).toBe(false)
  })
})
