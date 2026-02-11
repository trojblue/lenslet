import type { Item } from '../../../lib/types'

export type Range = { min: number; max: number }

export interface Histogram {
  bins: number[]
  min: number
  max: number
  count: number
}

export function collectMetricValues(items: Item[], key: string): number[] {
  const values: number[] = []
  for (const it of items) {
    const val = it.metrics?.[key]
    if (val == null || Number.isNaN(val)) continue
    values.push(val)
  }
  return values
}

export function computeHistogramFromValues(values: number[], bins: number, base?: Histogram): Histogram | null {
  if (!values.length) return null
  const min = base ? base.min : Math.min(...values)
  let max = base ? base.max : Math.max(...values)
  if (min === max) max = min + 1

  const counts = new Array(bins).fill(0)
  const scale = bins / (max - min)
  for (const v of values) {
    const idx = Math.max(0, Math.min(bins - 1, Math.floor((v - min) * scale)))
    counts[idx] += 1
  }
  return { bins: counts, min, max, count: values.length }
}

export function normalizeRange(a: number, b: number): Range {
  return a < b ? { min: a, max: b } : { min: b, max: a }
}

export function formatNumber(value?: number | null): string {
  if (value == null || Number.isNaN(value)) return '–'
  const abs = Math.abs(value)
  if (abs >= 1000) return value.toFixed(0)
  if (abs >= 10) return value.toFixed(2)
  return value.toFixed(3)
}

export function formatInputValue(value: number): string {
  if (!Number.isFinite(value)) return ''
  const trimmed = value.toString()
  return trimmed.includes('e') ? value.toFixed(6) : trimmed
}

export function parseNumberInput(raw: string): { value: number | null; valid: boolean } {
  const trimmed = raw.trim()
  if (!trimmed) return { value: null, valid: true }
  const parsed = Number(trimmed)
  if (!Number.isFinite(parsed)) return { value: null, valid: false }
  return { value: parsed, valid: true }
}

export function clamp(value: number, min: number, max: number): number {
  if (value < min) return min
  if (value > max) return max
  return value
}

export function clamp01(v: number): number {
  if (v < 0) return 0
  if (v > 1) return 1
  return v
}

export function isApprox(a: number, b: number): boolean {
  const scale = Math.max(1, Math.abs(a), Math.abs(b))
  return Math.abs(a - b) <= 1e-6 * scale
}
