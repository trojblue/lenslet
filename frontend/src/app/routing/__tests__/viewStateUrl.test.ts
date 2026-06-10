import { describe, expect, it } from 'vitest'
import {
  buildSharedViewStateSearch,
  readSharedViewStateFromSearch,
} from '../viewStateUrl'
import type { DerivedMetricSpec, ViewState } from '../../../lib/types'

const DEFAULT_VIEW_STATE: ViewState = {
  filters: { and: [] },
  sort: { kind: 'builtin', key: 'added', dir: 'desc' },
}

function makeDerivedMetric(): DerivedMetricSpec {
  return {
    version: 1,
    id: 'score_v1',
    name: 'Score v1',
    intercept: 0,
    numericTerms: [{ key: 'raw_score', weight: 1, missing: 'invalid', zNormalize: false }],
    categoricalTerms: [],
  }
}

describe('shared view-state URL params', () => {
  it('round-trips metric sort and categorical filters', () => {
    const viewState: ViewState = {
      sort: { kind: 'metric', key: 'dpo_preference_score', dir: 'desc' },
      filters: {
        and: [
          { categoricalIn: { key: 'source_column', values: ['ptv03'] } },
        ],
      },
    }

    const search = buildSharedViewStateSearch('', viewState)
    const restored = readSharedViewStateFromSearch(search, DEFAULT_VIEW_STATE)

    expect(new URLSearchParams(search).get('sort')).toBe('metric:desc:dpo_preference_score')
    expect(restored.viewState).toEqual(viewState)
    expect(restored.hasSharedAnalysisState).toBe(true)
    expect(restored.hasSharedViewState).toBe(true)
  })

  it('removes default sort and empty filters while preserving unrelated params', () => {
    const search = buildSharedViewStateSearch(
      '?foo=bar&sort=metric%3Adesc%3Ascore&filters=%7B%22and%22%3A%5B%5D%7D',
      DEFAULT_VIEW_STATE,
    )

    expect(search).toBe('?foo=bar')
  })

  it('keeps metric keys with delimiter characters intact', () => {
    const viewState: ViewState = {
      sort: { kind: 'metric', key: 'score:human:dpo', dir: 'asc' },
      filters: { and: [] },
    }

    const restored = readSharedViewStateFromSearch(
      buildSharedViewStateSearch('', viewState),
      DEFAULT_VIEW_STATE,
    )

    expect(restored.viewState.sort).toEqual(viewState.sort)
  })

  it('includes a derived metric definition only when the shared view references it', () => {
    const derivedMetric = makeDerivedMetric()
    const viewState: ViewState = {
      sort: { kind: 'metric', key: '@derived/score_v1', dir: 'desc' },
      filters: {
        and: [{ metricRange: { key: '@derived/score_v1', min: 0, max: 10 } }],
      },
      derivedMetric,
    }

    const search = buildSharedViewStateSearch('', viewState)
    const params = new URLSearchParams(search)
    const restored = readSharedViewStateFromSearch(search, DEFAULT_VIEW_STATE)

    expect(params.get('derived_metric')).toBe(JSON.stringify(derivedMetric))
    expect(restored.viewState).toEqual(viewState)
  })

  it('does not report shared state when no Lenslet view params are present', () => {
    expect(readSharedViewStateFromSearch('?foo=bar', DEFAULT_VIEW_STATE)).toEqual({
      viewState: DEFAULT_VIEW_STATE,
      query: '',
      randomSeed: null,
      unsupportedMetricIntent: null,
      hasSharedAnalysisState: false,
      hasSharedViewState: false,
    })
  })

  it('round-trips query, active random seed, and unsupported metric intent', () => {
    const viewState: ViewState = {
      sort: { kind: 'builtin', key: 'random', dir: 'asc' },
      filters: { and: [] },
    }
    const search = buildSharedViewStateSearch('', viewState, {
      query: '  tabby   cats ',
      randomSeed: 12345,
      unsupportedMetricIntent: 'derived metric unavailable',
    })
    const params = new URLSearchParams(search)
    const restored = readSharedViewStateFromSearch(search, DEFAULT_VIEW_STATE)

    expect(params.get('q')).toBe('tabby cats')
    expect(params.get('random_seed')).toBe('12345')
    expect(params.get('unsupported_metric_intent')).toBe('derived metric unavailable')
    expect(restored.query).toBe('tabby cats')
    expect(restored.randomSeed).toBe(12345)
    expect(restored.unsupportedMetricIntent).toBe('derived metric unavailable')
    expect(restored.viewState.sort).toEqual(viewState.sort)
  })

  it('keeps explicit URL analysis state ahead of conflicting fallback preferences', () => {
    const fallback: ViewState = {
      sort: { kind: 'metric', key: 'saved_score', dir: 'desc' },
      filters: { and: [{ starsIn: { values: [5] } }] },
      selectedMetric: 'saved_score',
      derivedMetric: { ...makeDerivedMetric(), id: 'saved_score' },
    }

    const restored = readSharedViewStateFromSearch(
      '?sort=builtin:name:asc&q=shared',
      fallback,
    )

    expect(restored.viewState).toEqual({
      sort: { kind: 'builtin', key: 'name', dir: 'asc' },
      filters: { and: [] },
    })
    expect(restored.query).toBe('shared')
  })
})
