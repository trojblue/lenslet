# S6 T23 Metrics Computation Reuse

## Scope

Ticket `T23` optimizes metrics-panel recomputation by moving metric-value collection into shared keyed caches and scoping cache work to the currently visible metric set (`show all` vs `show one`).

Files:

- `frontend/src/features/metrics/model/metricValues.ts`
- `frontend/src/features/metrics/components/MetricRangePanel.tsx`
- `frontend/src/features/metrics/components/MetricHistogramCard.tsx`
- `frontend/src/features/metrics/MetricsPanel.tsx`

## Benchmark

Command run from `frontend/`:

```bash
node <<'JS'
const { performance } = require('node:perf_hooks')
const ITEM_COUNT = 12000
const FILTERED_COUNT = 8000
const SELECTED_COUNT = 1800
const METRIC_COUNT = 24
const ACTIVE_KEY = 'metric_7'
const ROUNDS = 40
const WARMUP = 8
const metricKeys = Array.from({ length: METRIC_COUNT }, (_, i) => `metric_${i}`)
function makeItems(count, seedOffset = 0) {
  const items = []
  for (let i = 0; i < count; i += 1) {
    const metrics = {}
    for (let k = 0; k < metricKeys.length; k += 1) {
      const skip = (i + k + seedOffset) % 9 === 0
      if (skip) continue
      metrics[metricKeys[k]] = ((i * 17 + k * 31 + seedOffset) % 1000) / 10
    }
    items.push({ metrics })
  }
  return items
}
function collectMetricValues(items, key) {
  const values = []
  for (const it of items) {
    const raw = it.metrics?.[key]
    if (raw == null || Number.isNaN(raw)) continue
    values.push(raw)
  }
  return values
}
function collectMetricValuesByKey(items, keys) {
  const buckets = keys.map((key) => ({ key, values: [] }))
  for (const it of items) {
    const metrics = it.metrics
    if (!metrics) continue
    for (const bucket of buckets) {
      const raw = metrics[bucket.key]
      if (raw == null || Number.isNaN(raw)) continue
      bucket.values.push(raw)
    }
  }
  const out = new Map()
  for (const bucket of buckets) {
    if (bucket.values.length) out.set(bucket.key, bucket.values)
  }
  return out
}
function runLegacyShowAll(items, filteredItems, selectedItems, keys) {
  let checksum = 0
  for (const key of keys) {
    checksum += collectMetricValues(items, key).length
    checksum += collectMetricValues(filteredItems, key).length
    checksum += collectMetricValues(selectedItems, key).length
  }
  return checksum
}
function runCachedShowAll(items, filteredItems, selectedItems, keys) {
  const population = collectMetricValuesByKey(items, keys)
  const filtered = collectMetricValuesByKey(filteredItems, keys)
  const selected = collectMetricValuesByKey(selectedItems, keys)
  let checksum = 0
  for (const key of keys) {
    checksum += (population.get(key) || []).length
    checksum += (filtered.get(key) || []).length
    checksum += (selected.get(key) || []).length
  }
  return checksum
}
function runLegacyShowOne(items, filteredItems, selectedItems, key) {
  return collectMetricValues(items, key).length
    + collectMetricValues(filteredItems, key).length
    + collectMetricValues(selectedItems, key).length
}
function runCachedShowOne(items, filteredItems, selectedItems, key) {
  const scope = [key]
  const population = collectMetricValuesByKey(items, scope)
  const filtered = collectMetricValuesByKey(filteredItems, scope)
  const selected = collectMetricValuesByKey(selectedItems, scope)
  return (population.get(key) || []).length
    + (filtered.get(key) || []).length
    + (selected.get(key) || []).length
}
function summarize(times) {
  const sorted = [...times].sort((a, b) => a - b)
  const median = sorted[Math.floor(sorted.length / 2)]
  const mean = times.reduce((sum, v) => sum + v, 0) / Math.max(1, times.length)
  return { median, mean }
}
const items = makeItems(ITEM_COUNT)
const filteredItems = items.slice(0, FILTERED_COUNT)
const selectedItems = items.slice(0, SELECTED_COUNT)
const showAllLegacy = []
const showAllCached = []
const showOneLegacy = []
const showOneCached = []
let showAllChecksum = null
let showOneChecksum = null
for (let i = 0; i < ROUNDS; i += 1) {
  const t0 = performance.now()
  const a0 = runLegacyShowAll(items, filteredItems, selectedItems, metricKeys)
  const t1 = performance.now()
  const a1 = runCachedShowAll(items, filteredItems, selectedItems, metricKeys)
  const t2 = performance.now()
  const b0 = runLegacyShowOne(items, filteredItems, selectedItems, ACTIVE_KEY)
  const t3 = performance.now()
  const b1 = runCachedShowOne(items, filteredItems, selectedItems, ACTIVE_KEY)
  const t4 = performance.now()
  if (a0 !== a1) throw new Error(`show-all checksum mismatch: ${a0} vs ${a1}`)
  if (b0 !== b1) throw new Error(`show-one checksum mismatch: ${b0} vs ${b1}`)
  showAllChecksum = a0
  showOneChecksum = b0
  if (i >= WARMUP) {
    showAllLegacy.push(t1 - t0)
    showAllCached.push(t2 - t1)
    showOneLegacy.push(t3 - t2)
    showOneCached.push(t4 - t3)
  }
}
console.log(JSON.stringify({
  checksums: { showAll: showAllChecksum, showOne: showOneChecksum },
  showAll: { legacy: summarize(showAllLegacy), cached: summarize(showAllCached) },
  showOne: { legacy: summarize(showOneLegacy), cached: summarize(showOneCached) },
}, null, 2))
JS
```

Result snapshot:

- Checksums matched: `showAll=465068`, `showOne=19377`.
- Show-all median: `18.12ms` legacy -> `9.33ms` cached (`~48.5%` lower).
- Show-all mean: `18.23ms` legacy -> `9.87ms` cached (`~45.9%` lower).
- Show-one median: `0.85ms` legacy -> `0.96ms` cached (`+0.11ms`).
- Show-one mean: `0.88ms` legacy -> `1.04ms` cached (`+0.16ms`).

Interpretation:

- The shared keyed cache materially reduces the heavy `show all metrics` path.
- The scoped-key strategy keeps `show one` overhead in the sub-millisecond range while preserving output parity.
