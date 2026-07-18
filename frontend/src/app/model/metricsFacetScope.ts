import type { BrowseQueryOptions } from '../../api/folders'
import type { BrowseFacetFields, DerivedMetricViewSpec } from '../../lib/types'

export function metricsPopulationFacetOptions({
  path,
  derivedMetric,
  facetFields,
}: {
  path: string
  derivedMetric: DerivedMetricViewSpec | null
  facetFields: BrowseFacetFields
}): BrowseQueryOptions {
  return {
    path,
    recursive: true,
    filters: { and: [] },
    sort: { kind: 'builtin', key: 'added', dir: 'desc' },
    textQuery: '',
    randomSeed: null,
    derivedMetric,
    unsupportedToken: null,
    facetFields,
  }
}
