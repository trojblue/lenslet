# Metrics computation scalability audit

Scope: main-gallery metrics model only. Ranking, component presentation, query ownership, and hooks were excluded. Reviewed the repository continuity contract, the `better-code` frontend performance guidance, and jaku `better-ui` performance guidance. This change targets measured computation cost; it adds no animation, dependency, cache, or memoization layer.

## Implemented finding

| Severity | Location | Before | After | User impact |
| --- | --- | --- | --- | --- |
| High | `frontend/src/features/metrics/model/histogram.ts:12` | Population extrema used `Math.min(...values)` and `Math.max(...values)`. A 250,000-value population throws `RangeError` in Chromium. | One constant-space loop computes both extrema without constructing a function argument list. | Large local metrics/derived previews produce a histogram instead of crashing rendering. |

The same shared function serves ordinary metric, filtered/selected overlay, and derived-score histograms. Existing semantics remain: empty values return null; supplied population bounds skip extrema calculation; constant domains expand by one; out-of-domain overlay values clamp to edge bins; inputs are not mutated. Two-argument `Math.min`/`Math.max` retain signed-zero and nonfinite propagation semantics. Upstream collectors already exclude nonfinite metric values.

## Measurements

Headless Chromium 148.0.7778.96, Linux x86_64; 40 bins, fractional repeating values `(index % 1000) / 7 - 50`. Each case loaded a fresh function, performed 100 warmups, then measured 51 batches of 10 invocations. These are isolated model timings, not whole-gallery responsiveness claims. JIT and machine load affect timings.

| Values | Before median / p95 | After median / p95 |
| --- | --- | --- |
| 40,000 | 0.64 / 1.18 ms | 0.28 / 0.29 ms |
| 100,000 | 1.52 / 2.95 ms | 0.70 / 0.83 ms |
| 250,000 | `RangeError: Maximum call stack size exceeded` | 1.74 / 1.77 ms |
| 1,000,000 | `RangeError: Maximum call stack size exceeded` | 6.90 / 7.09 ms |

Every successful output's count equalled the sum of its bins. Baseline was copied before editing; both versions were transpiled with TypeScript target ES2022, imported into the same browser evaluation, and measured in source order. Preserving native spread during transpilation matters: a default legacy target can optimize differently and conceal the failure. Node 24 also reproduced the native-spread failure at 250,000 and 1,000,000 values. Node small-population timings were roughly comparable, so the reliable cross-runtime claim is removal of the population-size crash.

Session reproduction artifacts: `/tmp/lenslet-histogram-before.ts`, `/tmp/lenslet-histogram-benchmark.cjs`, `/tmp/lenslet-histogram-sources.json`, and `/tmp/lenslet-histogram-browser.py`. The checked-in tests retain the large-input correctness gate.

## Validation

- Histogram tests cover a 250,000-value mixed-sign population with exact bins and count, a 250,000-value overlay clamped to an unchanged base, and signed-zero domain behavior.
- Focused histogram, metric-value collection, and derived-metric suites: 3 files / 31 tests passed.
- `npx tsc --noEmit`: passed.
- No component or asynchronous presentation behavior changed; full application/browser integration remains owned by the main session.

## Remaining model review

`metricValues.ts` and `categoricalValues.ts` already aggregate by map; work scales with rows times requested keys, followed by sorting category buckets. No population-size quadratic membership loop or additional spread-extrema call was found in this model directory. `derivedMetric.ts` uses per-key aggregation and one item-scoring pass. Its normalization and reserved-key stripping allocate intermediate objects, but this audit did not establish a material bottleneck warranting a change. No speculative rewrite was made.

The isolated histogram remains synchronous and linear. Very large in-memory populations still consume main-thread time, and this fix does not establish an end-to-end budget for derived expression evaluation, metric collection, server facets, or rendering. Those require workload-specific traces before considering workers or more complex aggregation ownership.
