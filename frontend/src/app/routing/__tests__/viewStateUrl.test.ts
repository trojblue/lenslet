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
    expect(restored).toEqual({
      viewState,
      hasSharedViewState: true,
    })
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
      hasSharedViewState: false,
    })
  })

  it.todo('keeps explicit URL analysis state ahead of conflicting localStorage preferences')
})
