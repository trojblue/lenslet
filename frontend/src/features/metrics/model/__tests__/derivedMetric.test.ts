import { describe, expect, it } from 'vitest'
import type { BrowseItemPayload, DerivedMetricSpec } from '../../../../lib/types'
import {
  derivedMetricKey,
  evaluateDerivedMetric,
  normalizeDerivedMetricSpec,
  normalizeViewState,
} from '../derivedMetric'

function makeSpec(overrides: Partial<DerivedMetricSpec> = {}): DerivedMetricSpec {
  return {
    version: 1,
    id: 'rubric_1',
    name: 'Rubric score',
    intercept: 1,
    numericTerms: [
      { key: 'q1', weight: 0.5, missing: 'zero' },
      { key: 'q2', weight: 2, missing: 'invalid' },
    ],
    categoricalTerms: [
      { key: 'dataset_from', value: 'gt', weight: 5 },
    ],
    ...overrides,
  }
}

function makeItem(
  path: string,
  options: {
    metrics?: BrowseItemPayload['metrics']
    categoricals?: BrowseItemPayload['categoricals']
  } = {},
): BrowseItemPayload {
  return {
    path,
    name: path.split('/').pop() ?? path,
    mime: 'image/jpeg',
    width: 10,
    height: 10,
    size: 1,
    has_thumbnail: true,
    has_metadata: true,
    metrics: options.metrics,
    categoricals: options.categoricals,
  }
}

describe('derived metric normalization', () => {
  it('normalizes a v1 spec and generates a stable opaque key from the id', () => {
    const normalized = normalizeViewState({
      filters: { and: [] },
      sort: { kind: 'metric', key: ' @derived/rubric_1 ', dir: 'desc' },
      selectedMetric: ' @derived/rubric_1 ',
      derivedMetric: makeSpec({ name: '  New score  ' }),
    })

    expect(normalized.derivedMetric?.name).toBe('New score')
    expect(normalized.sort).toEqual({ kind: 'metric', key: '@derived/rubric_1', dir: 'desc' })
    expect(normalized.selectedMetric).toBe('@derived/rubric_1')
    expect(derivedMetricKey(normalized.derivedMetric!)).toBe('@derived/rubric_1')
    expect(derivedMetricKey(makeSpec({ name: 'Renamed score' }))).toBe('@derived/rubric_1')
  })

  it('rejects unsupported numeric missing policies', () => {
    const raw = makeSpec({
      numericTerms: [
        { key: 'q1', weight: 1, missing: 'zero' },
      ],
    }) as unknown as { numericTerms: Array<Record<string, unknown>> }
    raw.numericTerms[0].missing = 'omit'

    expect(normalizeDerivedMetricSpec(raw)).toBeNull()
  })

  it('rejects non-finite weights and intercepts', () => {
    expect(normalizeDerivedMetricSpec(makeSpec({ intercept: Number.NaN }))).toBeNull()
    expect(normalizeDerivedMetricSpec(makeSpec({
      numericTerms: [{ key: 'q1', weight: Number.POSITIVE_INFINITY, missing: 'zero' }],
    }))).toBeNull()
    expect(normalizeDerivedMetricSpec(makeSpec({
      categoricalTerms: [{ key: 'dataset_from', value: 'gt', weight: Number.NEGATIVE_INFINITY }],
    }))).toBeNull()
  })

  it('rejects derived metric keys as numeric or categorical inputs', () => {
    expect(normalizeDerivedMetricSpec(makeSpec({
      numericTerms: [{ key: '@derived/other', weight: 1, missing: 'zero' }],
    }))).toBeNull()
    expect(normalizeDerivedMetricSpec(makeSpec({
      categoricalTerms: [{ key: '@derived/other', value: 'gt', weight: 1 }],
    }))).toBeNull()
  })
})

describe('derived metric evaluation', () => {
  it('computes weighted numeric terms and categorical exact-match bonuses', () => {
    const items = [
      makeItem('/a.jpg', {
        metrics: { q1: 2, q2: 3 },
        categoricals: { dataset_from: 'gt' },
      }),
      makeItem('/b.jpg', {
        metrics: { q1: null, q2: 1 },
        categoricals: { dataset_from: 'train' },
      }),
    ]

    const result = evaluateDerivedMetric({
      items,
      metricKeys: ['q1', 'q2'],
      categoricalKeys: ['dataset_from'],
      spec: makeSpec(),
      totalItems: 2,
    })

    expect(result.status).toBe('valid')
    expect(result.key).toBe('@derived/rubric_1')
    expect(result.metricKeys).toEqual(['q1', 'q2', '@derived/rubric_1'])
    expect(result.metricDisplayNames).toEqual({ '@derived/rubric_1': 'Rubric score' })
    expect(result.validCount).toBe(2)
    expect(result.invalidCount).toBe(0)
    expect(result.items.map((item) => item.metrics?.['@derived/rubric_1'])).toEqual([13, 3])
    expect(items[0].metrics).toEqual({ q1: 2, q2: 3 })
    expect(result.items[0]).not.toBe(items[0])
    expect(result.items[0].metrics).not.toBe(items[0].metrics)
  })

  it('treats missing categorical keys as unavailable and absent item values as no bonus', () => {
    const items = [
      makeItem('/a.jpg', { metrics: { q1: 2, q2: 3 } }),
    ]
    const unavailable = evaluateDerivedMetric({
      items,
      metricKeys: ['q1', 'q2'],
      categoricalKeys: [],
      spec: makeSpec(),
    })

    expect(unavailable.status).toBe('unavailable')
    expect(unavailable.missingCategoricalKeys).toEqual(['dataset_from'])
    expect(unavailable.items).toBe(items)

    const available = evaluateDerivedMetric({
      items,
      metricKeys: ['q1', 'q2'],
      categoricalKeys: ['dataset_from'],
      spec: makeSpec(),
    })

    expect(available.status).toBe('valid')
    expect(available.items[0].metrics?.['@derived/rubric_1']).toBe(8)
  })

  it('reports all-invalid loaded scores while still exposing the derived key', () => {
    const items = [
      makeItem('/a.jpg', { metrics: { q1: null } }),
      makeItem('/b.jpg', { metrics: {} }),
    ]
    const result = evaluateDerivedMetric({
      items,
      metricKeys: ['q1'],
      categoricalKeys: [],
      spec: makeSpec({
        numericTerms: [{ key: 'q1', weight: 1, missing: 'invalid' }],
        categoricalTerms: [],
      }),
    })

    expect(result.status).toBe('valid')
    expect(result.metricKeys).toEqual(['q1', '@derived/rubric_1'])
    expect(result.validCount).toBe(0)
    expect(result.invalidCount).toBe(2)
    expect(result.items).toBe(items)
  })

  it('surfaces missing metric inputs and loaded-window warning metadata', () => {
    const items = [makeItem('/a.jpg', { metrics: { q1: 1 } })]
    const result = evaluateDerivedMetric({
      items,
      metricKeys: ['q1'],
      categoricalKeys: ['dataset_from'],
      spec: makeSpec(),
      loadedCount: 1,
      totalItems: 5,
    })

    expect(result.status).toBe('unavailable')
    expect(result.missingMetricKeys).toEqual(['q2'])
    expect(result.loadedCount).toBe(1)
    expect(result.totalItems).toBe(5)
    expect(result.partialLoadWarning).toBe(true)
  })

  it('distinguishes malformed saved specs from an absent derived metric', () => {
    const items = [makeItem('/a.jpg', { metrics: { q1: 1 } })]
    const invalidSpec = {
      version: 1,
      id: 'rubric_1',
      name: 'Saved score',
      intercept: Number.NaN,
      numericTerms: [],
      categoricalTerms: [],
    }
    const result = evaluateDerivedMetric({
      items,
      metricKeys: ['q1'],
      categoricalKeys: [],
      spec: invalidSpec,
    })

    expect(result.status).toBe('invalid')
    expect(result.key).toBe('@derived/rubric_1')
    expect(result.name).toBe('Saved score')
    expect(result.invalidReasons).toEqual(['Invalid derived metric definition.'])
    expect(result.metricDisplayNames).toEqual({ '@derived/rubric_1': 'Saved score' })
    expect(result.items).toBe(items)
  })

  it('strips reserved raw derived metric keys from source metrics', () => {
    const items = [
      makeItem('/a.jpg', { metrics: { '@derived/raw': 10 } }),
    ]
    const result = evaluateDerivedMetric({
      items,
      metricKeys: ['@derived/raw'],
      categoricalKeys: [],
      spec: null,
    })

    expect(result.status).toBe('none')
    expect(result.metricKeys).toEqual([])
    expect(result.items).not.toBe(items)
    expect(result.items[0].metrics).toBeUndefined()
    expect(items[0].metrics).toEqual({ '@derived/raw': 10 })
  })
})
