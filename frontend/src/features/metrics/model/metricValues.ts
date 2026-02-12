import type { Item } from '../../../lib/types'

export type MetricValuesByKey = Map<string, number[]>

const EMPTY_VALUES: number[] = []

export function collectMetricValuesByKey(items: Item[], metricKeys?: readonly string[]): MetricValuesByKey {
  if (metricKeys?.length) {
    return collectMetricValuesForKeys(items, metricKeys)
  }

  const valuesByKey: MetricValuesByKey = new Map()

  for (const it of items) {
    const metrics = it.metrics
    if (!metrics) continue
    for (const [key, raw] of Object.entries(metrics)) {
      if (raw == null || Number.isNaN(raw)) continue
      const existing = valuesByKey.get(key)
      if (existing) existing.push(raw)
      else valuesByKey.set(key, [raw])
    }
  }

  return valuesByKey
}

function collectMetricValuesForKeys(items: Item[], metricKeys: readonly string[]): MetricValuesByKey {
  const buckets = metricKeys.map((key) => ({ key, values: [] as number[] }))

  for (const it of items) {
    const metrics = it.metrics
    if (!metrics) continue
    for (const bucket of buckets) {
      const raw = metrics[bucket.key]
      if (raw == null || Number.isNaN(raw)) continue
      bucket.values.push(raw)
    }
  }

  const valuesByKey: MetricValuesByKey = new Map()
  for (const bucket of buckets) {
    if (bucket.values.length) valuesByKey.set(bucket.key, bucket.values)
  }
  return valuesByKey
}

export function getMetricValues(valuesByKey: MetricValuesByKey, key: string): number[] {
  return valuesByKey.get(key) ?? EMPTY_VALUES
}
