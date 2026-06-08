import { describe, expect, it } from 'vitest'
import type { BrowseItemPayload, DerivedMetricSpec, ViewState } from '../../lib/types'
import type { DerivedMetricEvaluation } from '../../features/metrics/model/derivedMetric'
import {
  applyDerivedMetricToViewState,
  buildDerivedMetricWarning,
  buildStarCounts,
  getDisplayItemCount,
  getDisplayTotalCount,
  getDerivedMetricRankDisabledReason,
  getSimilarityCountLabel,
  getSimilarityQueryLabel,
  getUnavailableDerivedMetricFilterKeys,
  hasMetricSortValues,
  rankByDerivedMetricInViewState,
  resolveCategoricalKeys,
  resolveDerivedMetricTotalItems,
  resolveMetricKeys,
  resolveSelectedMetricKey,
  shouldResetUnavailableMetricSort,
} from '../model/appShellSelectors'

function makeItem(
  path: string,
  options?: {
    star?: BrowseItemPayload['star']
    metrics?: BrowseItemPayload['metrics']
    categoricals?: BrowseItemPayload['categoricals']
  }
): BrowseItemPayload {
  return {
    path,
    name: path.split('/').pop() ?? path,
    mime: 'image/jpeg',
    width: 100,
    height: 100,
    size: 1,
    has_thumbnail: true,
    has_metadata: true,
    star: options?.star,
    metrics: options?.metrics,
    categoricals: options?.categoricals,
  }
}

function makeDerivedMetricEvaluation(
  overrides: Partial<DerivedMetricEvaluation> = {},
): DerivedMetricEvaluation {
  return {
    items: [],
    metricKeys: ['q1', '@derived/rubric_1'],
    categoricalKeys: [],
    metricDisplayNames: { '@derived/rubric_1': 'Rubric score' },
    spec: null,
    key: '@derived/rubric_1',
    name: 'Rubric score',
    status: 'valid',
    validCount: 2,
    invalidCount: 0,
    invalidReasons: [],
    missingMetricKeys: [],
    missingCategoricalKeys: [],
    loadedCount: 2,
    totalItems: 2,
    partialLoadWarning: false,
    ...overrides,
  }
}

function makeDerivedMetricSpec(overrides: Partial<DerivedMetricSpec> = {}): DerivedMetricSpec {
  return {
    version: 1,
    id: 'rubric_1',
    name: 'Rubric score',
    intercept: 0,
    numericTerms: [{ key: 'q1', weight: 1, missing: 'invalid' }],
    categoricalTerms: [],
    ...overrides,
  }
}

describe('appShellSelectors', () => {
  it('detects whether a metric sort key has numeric values', () => {
    const items = [
      makeItem('/a.jpg', { metrics: { score: null } }),
      makeItem('/b.jpg', { metrics: { score: Number.NaN } }),
      makeItem('/c.jpg', { metrics: { score: Number.POSITIVE_INFINITY } }),
      makeItem('/d.jpg', { metrics: { score: Number.NEGATIVE_INFINITY } }),
    ]

    expect(hasMetricSortValues(items, 'score')).toBe(false)
  })

  it('detects a finite metric sort value among missing values', () => {
    const items = [
      makeItem('/a.jpg', { metrics: { score: null } }),
      makeItem('/b.jpg', { metrics: { score: Number.NaN } }),
      makeItem('/c.jpg', { metrics: { score: 0.42 } }),
    ]

    expect(hasMetricSortValues(items, null)).toBe(false)
    expect(hasMetricSortValues(items, 'other')).toBe(false)
    expect(hasMetricSortValues(items, 'score')).toBe(true)
  })

  it('builds star counts from base stars and local overrides', () => {
    const items = [
      makeItem('/a.jpg', { star: 2 }),
      makeItem('/b.jpg', { star: null }),
      makeItem('/c.jpg', { star: 5 }),
    ]

    const counts = buildStarCounts(items, {
      '/a.jpg': 4,
      '/b.jpg': null,
    })

    expect(counts).toEqual({
      '0': 1,
      '1': 0,
      '2': 0,
      '3': 0,
      '4': 1,
      '5': 1,
    })
  })

  it('uses folder payload metric keys for normal browse and search mode', () => {
    const items = [
      makeItem('/a.jpg', { metrics: { score: 1 } }),
      makeItem('/b.jpg'),
    ]

    expect(resolveMetricKeys(['quality_score', 'score'], false, items)).toEqual([
      'quality_score',
      'score',
    ])
  })

  it('derives sorted metric keys from similarity items only when similarity mode is active', () => {
    const items = Array.from({ length: 40 }, (_, index) => {
      if (index === 0) {
        return makeItem(`/item-${index}.jpg`, { metrics: { score: 1 } })
      }
      if (index === 1) {
        return makeItem(`/item-${index}.jpg`, { metrics: { quality: 2 } })
      }
      return makeItem(`/item-${index}.jpg`)
    })

    expect(resolveMetricKeys(['folder_only'], true, items)).toEqual(['quality', 'score'])
  })

  it('does not expose reserved derived keys from raw source metric keys', () => {
    const items = [
      makeItem('/a.jpg', { metrics: { '@derived/raw': 1, score: 2 } }),
    ]

    expect(resolveMetricKeys(['@derived/raw', 'score'], false, [])).toEqual(['score'])
    expect(resolveMetricKeys([], true, items)).toEqual(['score'])
  })

  it('scans similarity items until required derived metric inputs are found', () => {
    const items = Array.from({ length: 260 }, (_, index) => {
      if (index === 0) {
        return makeItem(`/item-${index}.jpg`, { metrics: { score: 1 } })
      }
      if (index === 259) {
        return makeItem(`/item-${index}.jpg`, { metrics: { q_late: 2 } })
      }
      return makeItem(`/item-${index}.jpg`)
    })

    expect(resolveMetricKeys([], true, items)).toEqual(['score'])
    expect(resolveMetricKeys([], true, items, ['q_late'])).toEqual(['q_late', 'score'])
  })

  it('keeps selected derived metrics when the active definition owns the key', () => {
    expect(resolveSelectedMetricKey(
      '@derived/rubric_1',
      ['score', '@derived/rubric_1'],
      '@derived/rubric_1',
    )).toBe('@derived/rubric_1')
    expect(resolveSelectedMetricKey('@derived/rubric_1', ['score'], '@derived/rubric_1')).toBe('@derived/rubric_1')
    expect(resolveSelectedMetricKey('missing_score', ['score'])).toBe('score')
    expect(resolveSelectedMetricKey('@derived/stale', ['score'], '@derived/rubric_1')).toBe('score')
  })

  it('resets missing raw and stale derived metric sorts but keeps active unavailable derived sorts', () => {
    expect(shouldResetUnavailableMetricSort(
      { kind: 'metric', key: 'missing_score', dir: 'desc' },
      ['score'],
      false,
    )).toBe(true)
    expect(shouldResetUnavailableMetricSort(
      { kind: 'metric', key: '@derived/rubric_1', dir: 'desc' },
      ['score'],
      false,
      '@derived/rubric_1',
      'unavailable',
    )).toBe(false)
    expect(shouldResetUnavailableMetricSort(
      { kind: 'metric', key: '@derived/stale', dir: 'desc' },
      ['score'],
      false,
      '@derived/rubric_1',
      'unavailable',
    )).toBe(true)
    expect(shouldResetUnavailableMetricSort(
      { kind: 'metric', key: 'missing_score', dir: 'desc' },
      ['score'],
      true,
    )).toBe(false)
  })

  it('builds warnings for unavailable derived sorts and filters', () => {
    const filters = {
      and: [{ metricRange: { key: '@derived/rubric_1', min: 0, max: 10 } }],
    }
    const unavailable = makeDerivedMetricEvaluation({
      metricKeys: ['q1'],
      status: 'unavailable',
      validCount: 0,
      invalidCount: 2,
      missingMetricKeys: ['q2'],
      missingCategoricalKeys: ['dataset_from'],
    })

    expect(getUnavailableDerivedMetricFilterKeys(filters, unavailable)).toEqual(['@derived/rubric_1'])
    expect(buildDerivedMetricWarning(
      { kind: 'metric', key: '@derived/rubric_1', dir: 'desc' },
      filters,
      unavailable,
    )).toBe('Derived score inputs unavailable in this view: dataset_from, q2.')
  })

  it('detects stale derived filter keys and clears the warning when inputs return', () => {
    const filters = {
      and: [{ metricRange: { key: '@derived/stale', min: 0, max: 10 } }],
    }
    expect(buildDerivedMetricWarning(
      { kind: 'builtin', key: 'added', dir: 'desc' },
      filters,
      makeDerivedMetricEvaluation(),
    )).toBe('Saved derived score is unavailable in this view.')

    const validFilters = {
      and: [{ metricRange: { key: '@derived/rubric_1', min: 0, max: 10 } }],
    }
    expect(buildDerivedMetricWarning(
      { kind: 'metric', key: '@derived/rubric_1', dir: 'desc' },
      validFilters,
      makeDerivedMetricEvaluation(),
    )).toBeNull()
  })

  it('warns when an active derived sort ranks only a loaded window', () => {
    expect(buildDerivedMetricWarning(
      { kind: 'metric', key: '@derived/rubric_1', dir: 'desc' },
      { and: [] },
      makeDerivedMetricEvaluation({
        loadedCount: 25,
        totalItems: 100,
        partialLoadWarning: true,
      }),
    )).toBe('Derived score ranks only the 25 loaded items out of 100.')
  })

  it('reports mode-level disabled reasons for derived ranking', () => {
    expect(getDerivedMetricRankDisabledReason(true, false)).toBe('Ranking disabled in similarity mode.')
    expect(getDerivedMetricRankDisabledReason(false, true)).toBe('Ranking disabled while scan order is locked.')
    expect(getDerivedMetricRankDisabledReason(false, false)).toBeNull()
  })

  it('applies and clears derived metrics without losing unrelated view state', () => {
    const viewState: ViewState = {
      filters: {
        and: [
          { nameContains: { value: 'cat' } },
          { metricRange: { key: '@derived/rubric_1', min: 0, max: 10 } },
          { metricRange: { key: 'q1', min: 0, max: 10 } },
        ],
      },
      sort: { kind: 'metric', key: '@derived/rubric_1', dir: 'asc' },
      selectedMetric: '@derived/rubric_1',
      derivedMetric: makeDerivedMetricSpec(),
    }

    const cleared = applyDerivedMetricToViewState(viewState, null)
    expect(cleared).toEqual({
      filters: {
        and: [
          { nameContains: { value: 'cat' } },
          { metricRange: { key: 'q1', min: 0, max: 10 } },
        ],
      },
      sort: { kind: 'builtin', key: 'added', dir: 'asc' },
      derivedMetric: null,
    })

    const applied = applyDerivedMetricToViewState(
      { ...viewState, sort: { kind: 'metric', key: 'q1', dir: 'desc' }, selectedMetric: 'q1' },
      makeDerivedMetricSpec({ name: 'Renamed score' }),
    )
    expect(applied.sort).toEqual({ kind: 'metric', key: 'q1', dir: 'desc' })
    expect(applied.selectedMetric).toBe('q1')
    expect(applied.derivedMetric).toMatchObject({ name: 'Renamed score' })
  })

  it('ranks by a derived metric through the stable key', () => {
    const spec = makeDerivedMetricSpec()
    const ranked = rankByDerivedMetricInViewState({
      filters: { and: [] },
      sort: { kind: 'builtin', key: 'added', dir: 'asc' },
    }, spec)

    expect(ranked.derivedMetric).toBe(spec)
    expect(ranked.selectedMetric).toBe('@derived/rubric_1')
    expect(ranked.sort).toEqual({ kind: 'metric', key: '@derived/rubric_1', dir: 'desc' })
  })

  it('uses loaded counts for search and similarity derived-score partial metadata', () => {
    expect(resolveDerivedMetricTotalItems(false, false, 5000, 40000)).toBe(40000)
    expect(resolveDerivedMetricTotalItems(true, false, 2, 40000)).toBe(2)
    expect(resolveDerivedMetricTotalItems(false, true, 10, 40000)).toBe(10)
    expect(resolveDerivedMetricTotalItems(false, false, 3, null)).toBe(3)
  })

  it('resolves categorical keys from folder payload or similarity items', () => {
    const items = [
      makeItem('/a.jpg', { categoricals: { l0r_viewpoint_family: 'frontal' } }),
      makeItem('/b.jpg', { categoricals: { l0r_focus_mechanism: 'face_or_gaze' } }),
    ]

    expect(resolveCategoricalKeys(['folder_only'], false, items)).toEqual(['folder_only'])
    expect(resolveCategoricalKeys(['folder_only'], true, items)).toEqual([
      'l0r_focus_mechanism',
      'l0r_viewpoint_family',
    ])
  })

  it('formats display counts for similarity and standard browsing modes', () => {
    expect(getDisplayItemCount(true, false, 12, 90)).toBe(12)
    expect(getDisplayItemCount(false, true, 12, 90)).toBe(12)
    expect(getDisplayItemCount(false, false, 12, 90)).toBe(90)

    expect(getDisplayTotalCount(true, false, 50, 90, 400, '/nested')).toBe(50)
    expect(getDisplayTotalCount(false, true, 50, 90, 400, '/nested')).toBe(90)
    expect(getDisplayTotalCount(false, false, 50, 90, 400, '/nested')).toBe(400)
    expect(getDisplayTotalCount(false, false, 50, 90, 400, '/')).toBe(90)
  })

  it('formats similarity labels from query path/vector and active filter state', () => {
    expect(getSimilarityQueryLabel({ queryPath: '/set/cat.jpg', queryVector: null })).toBe('cat.jpg')
    expect(getSimilarityQueryLabel({ queryPath: null, queryVector: 'abc' })).toBe('Vector query')
    expect(getSimilarityQueryLabel({ queryPath: null, queryVector: null })).toBeNull()
    expect(getSimilarityQueryLabel(null)).toBeNull()

    expect(getSimilarityCountLabel(false, 0, 3, 10)).toBeNull()
    expect(getSimilarityCountLabel(true, 0, 3, 10)).toBe('10')
    expect(getSimilarityCountLabel(true, 2, 3, 10)).toBe('3 of 10')
  })
})
