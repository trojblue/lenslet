import { describe, expect, it } from 'vitest'
import { metricsPopulationFacetOptions } from '../metricsFacetScope'

describe('metrics population facet scope', () => {
  it('keeps the full folder population independent of active browse filters and search', () => {
    expect(metricsPopulationFacetOptions({
      path: '/shots',
      derivedMetric: null,
      facetFields: { metric_keys: ['score'], categorical_keys: ['source'] },
    })).toEqual({
      path: '/shots',
      recursive: true,
      filters: { and: [] },
      sort: { kind: 'builtin', key: 'added', dir: 'desc' },
      textQuery: '',
      randomSeed: null,
      derivedMetric: null,
      unsupportedToken: null,
      facetFields: { metric_keys: ['score'], categorical_keys: ['source'] },
    })
  })
})
