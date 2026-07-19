import { finiteMetricValue } from '../../../lib/metrics'
import type { BrowseItemPayload } from '../../../lib/types'

export type MetricRailDomain = {
  min: number
  max: number
}

export type MetricRailHistogram = MetricRailDomain & {
  bins: number[]
  count: number
}

export type MetricRailState = 'pending' | 'ready' | 'empty' | 'error'

export type MetricRailPresentation = {
  state: MetricRailState
  histogram: MetricRailHistogram | null
}

type SortDirection = 'asc' | 'desc'

export function computeMetricRailHistogram(
  values: readonly number[],
  binCount: number,
): MetricRailHistogram | null {
  if (!values.length) return null
  const bins = Math.max(1, Math.trunc(binCount))
  const min = Math.min(...values)
  let max = Math.max(...values)
  if (min === max) max = min + 1

  const counts = new Array(bins).fill(0)
  const scale = bins / (max - min)
  for (const value of values) {
    const idx = Math.max(0, Math.min(bins - 1, Math.floor((value - min) * scale)))
    counts[idx] += 1
  }
  return { bins: counts, min, max, count: values.length }
}

export function resolveMetricRailPresentation({
  active,
  localComplete,
  localHistogram,
  facetHistogram,
  facetState,
}: {
  active: boolean
  localComplete: boolean
  localHistogram: MetricRailHistogram | null
  facetHistogram: MetricRailHistogram | null
  facetState: 'pending' | 'settled' | 'error'
}): MetricRailPresentation {
  if (!active) return { state: 'empty', histogram: null }
  if (facetHistogram) return { state: 'ready', histogram: facetHistogram }
  if (localComplete) {
    return localHistogram
      ? { state: 'ready', histogram: localHistogram }
      : { state: 'empty', histogram: null }
  }
  if (facetState === 'error') return { state: 'error', histogram: null }
  if (facetState === 'settled') return { state: 'empty', histogram: null }
  return { state: 'pending', histogram: null }
}

export function metricRailProgressFromValue(
  value: number,
  domain: MetricRailDomain,
  sortDir: SortDirection,
): number {
  const range = domain.max - domain.min
  if (range <= 0) return 0
  const t = clamp01((value - domain.min) / range)
  return sortDir === 'desc' ? 1 - t : t
}

export function metricValueFromRailProgress(
  progress: number,
  domain: MetricRailDomain,
  sortDir: SortDirection,
): number {
  const t = sortDir === 'desc' ? 1 - clamp01(progress) : clamp01(progress)
  return domain.min + (domain.max - domain.min) * t
}

export function closestMetricPathForValue(
  items: readonly BrowseItemPayload[],
  metricKey: string,
  targetValue: number,
): string | null {
  const target = finiteMetricValue(targetValue)
  if (target == null) return null

  let bestPath: string | null = null
  let bestDistance = Number.POSITIVE_INFINITY
  for (const item of items) {
    const value = finiteMetricValue(item.metrics?.[metricKey])
    if (value == null) continue
    const distance = Math.abs(value - target)
    if (distance >= bestDistance) continue
    bestDistance = distance
    bestPath = item.path
  }
  return bestPath
}

export function metricValueAtProgress(
  values: readonly (number | null)[],
  progress: number,
): number | null {
  if (!values.length) return null
  const idx = Math.round(clamp01(progress) * (values.length - 1))
  const direct = values[idx]
  if (direct != null) return direct
  for (let offset = 1; offset < values.length; offset += 1) {
    const up = idx - offset
    if (up >= 0 && values[up] != null) return values[up] as number
    const down = idx + offset
    if (down < values.length && values[down] != null) return values[down] as number
  }
  return null
}

export function clamp01(value: number): number {
  if (value < 0) return 0
  if (value > 1) return 1
  return value
}
