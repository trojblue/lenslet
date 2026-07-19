import { describe, expect, it } from 'vitest'

import {
  INITIAL_METRICS_FACET_DEMAND_OWNER,
  facetSchemaKey,
  resolveMetricsFacetDemand,
  resolveMetricsFacetFields,
  updateMetricsFacetDemandOwner,
} from '../facetDemand'

const metricKeys = Array.from({ length: 30 }, (_, index) => `metric_${index}`)
const categoricalKeys = Array.from({ length: 30 }, (_, index) => `category_${index}`)

describe('metrics facet demand ownership', () => {
  it('derives selected field requirements without child registration', () => {
    const demand = resolveMetricsFacetDemand(
      INITIAL_METRICS_FACET_DEMAND_OWNER,
      'reset-a',
      metricKeys,
      categoricalKeys,
    )

    expect(resolveMetricsFacetFields(
      demand,
      'metric_5',
      metricKeys,
      categoricalKeys,
    )).toEqual({
      metric_keys: ['metric_5'],
      categorical_keys: ['category_0'],
    })
  })

  it('owns Show-all and scroll batches in the same action update', () => {
    const shown = updateMetricsFacetDemandOwner(
      INITIAL_METRICS_FACET_DEMAND_OWNER,
      { type: 'set-show-all', kind: 'metric', showAll: true },
      'reset-a',
    )
    const scrolled = updateMetricsFacetDemandOwner(
      shown,
      {
        type: 'set-visible-keys',
        kind: 'metric',
        schemaKey: facetSchemaKey(metricKeys),
        schemaRevision: 0,
        keys: metricKeys.slice(24),
      },
      'reset-a',
    )
    const demand = resolveMetricsFacetDemand(
      scrolled,
      'reset-a',
      metricKeys,
      categoricalKeys,
    )

    expect(resolveMetricsFacetFields(
      demand,
      'metric_0',
      metricKeys,
      categoricalKeys,
    ).metric_keys).toEqual(metricKeys.slice(24))
  })

  it('preserves Show-all but re-seeds its batch at a hard reset', () => {
    const owner = updateMetricsFacetDemandOwner(
      {
        ...INITIAL_METRICS_FACET_DEMAND_OWNER,
        metric: {
          showAll: true,
          batch: {
            resetKey: 'reset-a',
            schemaKey: facetSchemaKey(metricKeys),
            schemaRevision: 0,
            keys: metricKeys.slice(24),
          },
        },
      },
      { type: 'select-categorical', key: 'category_4' },
      'reset-a',
    )

    const demand = resolveMetricsFacetDemand(
      owner,
      'reset-b',
      metricKeys,
      categoricalKeys,
    )

    expect(demand.metric).toEqual({
      showAll: true,
      schemaRevision: 0,
      visibleKeys: metricKeys.slice(0, 24),
    })
    expect(demand.categorical.selectedKey).toBe('category_4')
  })

  it('re-seeds a visible batch when the field schema changes in place', () => {
    const owner = updateMetricsFacetDemandOwner(
      INITIAL_METRICS_FACET_DEMAND_OWNER,
      {
        type: 'set-visible-keys',
        kind: 'metric',
        schemaKey: facetSchemaKey(metricKeys),
        schemaRevision: 0,
        keys: metricKeys.slice(24),
      },
      'reset-a',
    )
    const reordered = [metricKeys[29], ...metricKeys.slice(0, 29)]

    expect(resolveMetricsFacetDemand(
      owner,
      'reset-a',
      reordered,
      categoricalKeys,
    ).metric.visibleKeys).toEqual(reordered.slice(0, 24))
  })

  it('does not resurrect a batch when a prior schema identity returns', () => {
    const owner = updateMetricsFacetDemandOwner(
      INITIAL_METRICS_FACET_DEMAND_OWNER,
      {
        type: 'set-visible-keys',
        kind: 'metric',
        schemaKey: facetSchemaKey(metricKeys),
        schemaRevision: 0,
        keys: metricKeys.slice(24),
      },
      'reset-a',
    )

    expect(resolveMetricsFacetDemand(
      owner,
      'reset-a',
      metricKeys,
      categoricalKeys,
      { metric: 2, categorical: 0 },
    ).metric.visibleKeys).toEqual(metricKeys.slice(0, 24))
  })
})
