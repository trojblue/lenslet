import { describe, expect, it } from 'vitest'
import {
  browseProjectionForViewState,
  browseProjectionUnavailableReason,
  conclusiveClientFilters,
  resolveBrowseCapabilityKeys,
  type BrowseCapabilityKeys,
} from '../useAppDataScope'

const EMPTY_ROOT_KEYS: BrowseCapabilityKeys = {
  path: '/',
  metricKeys: [],
  categoricalKeys: [],
  ready: false,
}

describe('resolveBrowseCapabilityKeys', () => {
  it('projects only active metric and categorical view fields', () => {
    expect(browseProjectionForViewState({
      selectedMetric: 'selected',
      sort: { kind: 'metric', key: 'sorted', dir: 'desc' },
      filters: {
        and: [
          { metricRange: { key: 'filtered', min: 0, max: 1 } },
          { categoricalIn: { key: 'source_column', values: ['target'] } },
        ],
      },
      derivedMetric: {
        version: 1,
        id: 'rubric_1',
        name: 'Rubric',
        intercept: 0,
        numericTerms: [{ key: 'input', weight: 1, missing: 'invalid', zNormalize: false }],
        categoricalTerms: [],
      },
    })).toEqual({
      metric_keys: ['@derived/rubric_1', 'filtered', 'selected', 'sorted'],
      categorical_keys: ['source_column'],
    })
  })

  it('reports projection overflow instead of silently dropping filter fields', () => {
    const projection = browseProjectionForViewState({
      selectedMetric: undefined,
      sort: { kind: 'builtin', key: 'name', dir: 'asc' },
      filters: {
        and: Array.from({ length: 65 }, (_, index) => ({
          metricRange: { key: `metric_${index}`, min: 0, max: 1 },
        })),
      },
    })

    expect(projection.metric_keys).toHaveLength(65)
    expect(browseProjectionUnavailableReason(projection)).toContain('more than 64')
  })

  it('does not re-evaluate redacted URL predicates on lean browser entities', () => {
    expect(conclusiveClientFilters({
      and: [
        { urlContains: { value: 'private/source' } },
        { urlNotContains: { value: 'other' } },
        { starsIn: { values: [0] } },
      ],
    })).toEqual({ and: [{ starsIn: { values: [0] } }] })
  })

  it('keeps known scope metric keys while a same-scope browse query refetches', () => {
    const loaded = resolveBrowseCapabilityKeys('/', {
      path: '/',
      metric_keys: ['quality_score'],
      categorical_keys: ['source_column'],
    }, EMPTY_ROOT_KEYS)

    expect(loaded.ready).toBe(true)

    const refetching = resolveBrowseCapabilityKeys('/', undefined, loaded)

    expect(refetching).toBe(loaded)
    expect(refetching.metricKeys).toEqual(['quality_score'])
    expect(refetching.categoricalKeys).toEqual(['source_column'])
    expect(refetching.ready).toBe(true)
  })

  it('does not carry stale metric keys across folder changes', () => {
    const loaded = resolveBrowseCapabilityKeys('/', {
      path: '/',
      metric_keys: ['quality_score'],
      categorical_keys: ['source_column'],
    }, EMPTY_ROOT_KEYS)

    const nextFolder = resolveBrowseCapabilityKeys('/other', undefined, loaded)

    expect(nextFolder).toEqual({
      path: '/other',
      metricKeys: [],
      categoricalKeys: [],
      ready: false,
    })
  })

  it('treats a returned empty key list as ready backend metadata', () => {
    const loaded = resolveBrowseCapabilityKeys('/empty', {
      path: '/empty',
      metric_keys: [],
      categorical_keys: [],
    }, EMPTY_ROOT_KEYS)

    expect(loaded).toEqual({
      path: '/empty',
      metricKeys: [],
      categoricalKeys: [],
      ready: true,
    })
  })
})
