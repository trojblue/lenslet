import { describe, expect, it } from 'vitest'
import { renderToStaticMarkup } from 'react-dom/server'
import type { ComponentProps } from 'react'
import DerivedScorePanel from '../DerivedScorePanel'
import { resolveScorePreviewState } from '../components/DerivedScoreCard'
import MetricsPanel from '../MetricsPanel'
import type { BrowseFacetsPayload, BrowseItemPayload } from '../../../lib/types'
import type { DerivedMetricEvaluation } from '../model/derivedMetric'

const SINGLE_FIELD_DEMAND = {
  metric: { showAll: false, schemaRevision: 0, visibleKeys: [] },
  categorical: {
    showAll: false,
    schemaRevision: 0,
    selectedKey: null,
    visibleKeys: [],
  },
}

function makeItem(path: string, metrics?: BrowseItemPayload['metrics']): BrowseItemPayload {
  return {
    path,
    name: path.split('/').pop() ?? path,
    mime: 'image/jpeg',
    width: 100,
    height: 100,
    size: 1,
    has_thumbnail: true,
    has_metadata: true,
    metrics,
  }
}

function makeCategoricalFacets(key: string, values: string[]): BrowseFacetsPayload {
  return {
    version: 1,
    path: '/',
    generated_at: 'test',
    total_items: values.length,
    metric_keys: [],
    categorical_keys: [key],
    metrics: {},
    categoricals: {
      [key]: {
        values: values.map((value) => ({ value, population_count: 1 })),
      },
    },
    dependency_manifest: {
      fields: [],
      metric_keys: [],
      categorical_keys: [key],
      unknown: false,
    },
  }
}

function makeScanPoisonItems(): BrowseItemPayload[] {
  return new Proxy(
    [{
      ...makeItem('/poison.jpg', { q1: 1 }),
      categoricals: { group: 'poison' },
    }],
    {
      get(target, property, receiver) {
        if (property === Symbol.iterator) throw new Error('inactive panel scanned item rows')
        return Reflect.get(target, property, receiver)
      },
    },
  )
}

function makeDerivedMetricEvaluation(
  overrides: Partial<DerivedMetricEvaluation> = {},
): DerivedMetricEvaluation {
  return {
    items: [],
    metricKeys: [],
    categoricalKeys: [],
    metricDisplayNames: {},
    spec: null,
    definitionIdentity: null,
    key: null,
    name: null,
    status: 'none',
    validCount: 0,
    invalidCount: 0,
    invalidReasons: [],
    missingMetricKeys: [],
    missingCategoricalKeys: [],
    loadedCount: 0,
    totalItems: null,
    partialLoadWarning: false,
    ...overrides,
  }
}

describe('MetricsPanel', () => {
  it('does not scan item rows while mounted inactive', () => {
    const items = makeScanPoisonItems()
    const demand = {
      metric: { showAll: true, schemaRevision: 0, visibleKeys: ['q1'] },
      categorical: {
        showAll: true,
        schemaRevision: 0,
        selectedKey: 'group',
        visibleKeys: ['group'],
      },
    }

    expect(() => renderToStaticMarkup(
      <MetricsPanel
        active={false}
        items={items}
        filteredItems={items}
        metricKeys={['q1']}
        categoricalKeys={['group']}
        facetDemand={demand}
        onSelectMetric={() => {}}
        onFacetDemandAction={() => {}}
        filters={{ and: [] }}
        onChangeRange={() => {}}
        onChangeCategoricalValues={() => {}}
        onChangeFilters={() => {}}
      />,
    )).not.toThrow()

    expect(() => renderToStaticMarkup(
      <DerivedScorePanel
        active={false}
        items={items}
        metricKeys={['q1']}
        categoricalKeys={['group']}
        derivedMetric={makeDerivedMetricEvaluation()}
        onApplyDerivedMetric={() => {}}
        onRankByDerivedMetric={() => {}}
      />,
    )).not.toThrow()
  })

  it('renders metric filter options from the provided metric key schema', () => {
    const items = [
      makeItem('/a.jpg', { quality_score: 0.2 }),
      makeItem('/b.jpg', { quality_score: 0.8 }),
    ]

    const html = renderToStaticMarkup(
      <MetricsPanel
        items={items}
        filteredItems={items}
        metricKeys={['quality_score']}
        categoricalKeys={[]}
        selectedMetric="quality_score"
        facetDemand={SINGLE_FIELD_DEMAND}
        onSelectMetric={() => {}}
        onFacetDemandAction={() => {}}
        filters={{ and: [] }}
        onChangeRange={() => {}}
        onChangeCategoricalValues={() => {}}
        onChangeFilters={() => {}}
      />,
    )

    expect(html).toContain('data-metric-selector')
    expect(html).toContain('quality_score')
    expect(html).not.toContain('__index_level_0__')
  })

  it('renders categorical filter options when no numeric metrics are present', () => {
    const items = [
      { ...makeItem('/a.jpg'), categoricals: { l0r_viewpoint_family: 'frontal' } },
      { ...makeItem('/b.jpg'), categoricals: { l0r_viewpoint_family: 'profile' } },
    ]

    const html = renderToStaticMarkup(
      <MetricsPanel
        items={items}
        filteredItems={items.slice(0, 1)}
        metricKeys={[]}
        categoricalKeys={['l0r_viewpoint_family']}
        facetDemand={SINGLE_FIELD_DEMAND}
        onSelectMetric={() => {}}
        onFacetDemandAction={() => {}}
        filters={{ and: [] }}
        onChangeRange={() => {}}
        onChangeCategoricalValues={() => {}}
        onChangeFilters={() => {}}
      />,
    )

    expect(html).toContain('data-categorical-selector')
    expect(html).toContain('l0r_viewpoint_family')
    expect(html).toContain('frontal')
    expect(html).toContain('profile')
    expect(html).toContain('Filtered: 1')
  })

  it('renders categorical domains from facets instead of the loaded item page', () => {
    const items = [
      { ...makeItem('/a.jpg'), categoricals: { original_source: 'ptv03' } },
      { ...makeItem('/b.jpg'), categoricals: { original_source: 'gt' } },
    ]

    const html = renderToStaticMarkup(
      <MetricsPanel
        items={items}
        filteredItems={items}
        metricKeys={[]}
        categoricalKeys={['original_source']}
        facets={{
          version: 1,
          path: '/',
          generated_at: 'test',
          total_items: 4,
          metric_keys: [],
          categorical_keys: ['original_source'],
          dependency_manifest: {
            fields: [],
            metric_keys: [],
            categorical_keys: ['original_source'],
            unknown: false,
          },
          metrics: {},
          categoricals: {
            original_source: {
              values: [
                { value: 'ptv03', population_count: 1 },
                { value: 'gt', population_count: 1 },
                { value: 'synthetic', population_count: 1 },
                { value: 'rapidata', population_count: 1 },
              ],
            },
          },
        }}
        populationItemsComplete={false}
        filteredItemsComplete={false}
        facetDemand={SINGLE_FIELD_DEMAND}
        onSelectMetric={() => {}}
        onFacetDemandAction={() => {}}
        filters={{ and: [] }}
        onChangeRange={() => {}}
        onChangeCategoricalValues={() => {}}
        onChangeFilters={() => {}}
      />,
    )

    expect(html).toContain('ptv03')
    expect(html).toContain('gt')
    expect(html).toContain('synthetic')
    expect(html).toContain('rapidata')
    expect(html).toContain('Filtered: —')
  })

  it('does not use loaded-window categorical values when population is incomplete', () => {
    const items = [
      { ...makeItem('/a.jpg'), categoricals: { original_source: 'ptv03' } },
      { ...makeItem('/b.jpg'), categoricals: { original_source: 'gt' } },
    ]

    const html = renderToStaticMarkup(
      <MetricsPanel
        items={items}
        filteredItems={items.slice(0, 1)}
        metricKeys={[]}
        categoricalKeys={['original_source']}
        facetsState="pending"
        populationItemsComplete={false}
        filteredItemsComplete={false}
        facetDemand={SINGLE_FIELD_DEMAND}
        onSelectMetric={() => {}}
        onFacetDemandAction={() => {}}
        filters={{ and: [] }}
        onChangeRange={() => {}}
        onChangeCategoricalValues={() => {}}
        onChangeFilters={() => {}}
      />,
    )

    expect(html).not.toContain('ptv03')
    expect(html).not.toContain('title="gt"')
    expect(html).not.toContain('>gt<')
    expect(html).toContain('Filtered: —')
    expect(html).not.toContain('1/1')
    expect(html).toContain('data-facet-state="pending"')
    expect(html).toContain('Loading values for this field…')
  })

  it('renders the derived score card even when no source inputs exist', () => {
    const html = renderToStaticMarkup(
      <DerivedScorePanel
        items={[]}
        metricKeys={[]}
        categoricalKeys={[]}
        derivedMetric={makeDerivedMetricEvaluation()}
        onApplyDerivedMetric={() => {}}
        onRankByDerivedMetric={() => {}}
      />,
    )

    expect(html).toContain('Derived Score')
    expect(html).toContain('No score inputs in this view.')
  })

  it('keeps selected values in reserved card regions instead of inserting a summary card', () => {
    const items = [
      makeItem('/a.jpg', { quality_score: 0.2 }),
      makeItem('/b.jpg', { quality_score: 0.8 }),
    ]
    const html = renderToStaticMarkup(
      <MetricsPanel
        items={items}
        filteredItems={items}
        metricKeys={['quality_score']}
        categoricalKeys={[]}
        selectedItems={items}
        selectedMetric="quality_score"
        facetDemand={SINGLE_FIELD_DEMAND}
        onSelectMetric={() => {}}
        onFacetDemandAction={() => {}}
        filters={{ and: [] }}
        onChangeRange={() => {}}
        onChangeCategoricalValues={() => {}}
        onChangeFilters={() => {}}
      />,
    )

    expect(html).not.toContain('Selected metrics')
    expect(html).toContain('Selected: 2')
    expect(html).toContain('h-96')
  })

  it('keeps the derived categorical value control app-owned across facet states', () => {
    const html = renderToStaticMarkup(
      <DerivedScorePanel
        items={[{ ...makeItem('/a.jpg'), categoricals: { dataset_from: 'partial-only' } }]}
        metricKeys={['q1']}
        categoricalKeys={['dataset_from']}
        facetsState="pending"
        populationItemsComplete={false}
        derivedMetric={makeDerivedMetricEvaluation({
          spec: {
            version: 1,
            id: 'score_v1',
            name: 'new_score',
            intercept: 0,
            numericTerms: [{ key: 'q1', weight: 1, missing: 'invalid', zNormalize: false }],
            categoricalTerms: [{ key: 'dataset_from', value: 'custom', weight: 1 }],
          },
        })}
        onApplyDerivedMetric={() => {}}
        onRankByDerivedMetric={() => {}}
      />,
    )

    expect(html).toContain('data-facet-state="pending"')
    expect(html).toContain('role="combobox"')
    expect(html).toContain('value="custom"')
    expect(html).not.toContain('<select')
  })

  it('distinguishes explicit empty Derived facets from partial local errors', () => {
    const derivedMetric = makeDerivedMetricEvaluation({
      spec: {
        version: 1,
        id: 'score_v1',
        name: 'new_score',
        intercept: 0,
        numericTerms: [{ key: 'q1', weight: 1, missing: 'invalid', zNormalize: false }],
        categoricalTerms: [{ key: 'dataset_from', value: 'custom', weight: 1 }],
      },
    })
    const render = (props: Partial<ComponentProps<typeof DerivedScorePanel>>) => (
      renderToStaticMarkup(
        <DerivedScorePanel
          items={[{ ...makeItem('/a.jpg'), categoricals: { dataset_from: 'partial-only' } }]}
          metricKeys={['q1']}
          categoricalKeys={['dataset_from']}
          populationItemsComplete={false}
          derivedMetric={derivedMetric}
          onApplyDerivedMetric={() => {}}
          onRankByDerivedMetric={() => {}}
          {...props}
        />,
      )
    )

    const empty = render({ facets: makeCategoricalFacets('dataset_from', []) })
    const error = render({ facetsState: 'error' })

    expect(empty).toContain('data-derived-categorical-value="0" data-facet-state="empty"')
    expect(error).toContain('data-derived-categorical-value="0" data-facet-state="error"')
    expect(error).not.toContain('partial-only')
  })

  it('keeps Derived numeric histograms pending until population facets settle', () => {
    const html = renderToStaticMarkup(
      <DerivedScorePanel
        items={[makeItem('/partial.jpg', { q1: 0.5 })]}
        metricKeys={['q1']}
        categoricalKeys={[]}
        facetsState="pending"
        populationItemsComplete={false}
        derivedMetric={makeDerivedMetricEvaluation({
          spec: {
            version: 1,
            id: 'score_v1',
            name: 'new_score',
            intercept: 0,
            numericTerms: [{ key: 'q1', weight: 1, missing: 'invalid', zNormalize: false }],
            categoricalTerms: [],
          },
        })}
        onApplyDerivedMetric={() => {}}
        onRankByDerivedMetric={() => {}}
      />,
    )

    expect(html).toContain('data-derived-metric-histogram="q1" data-facet-state="pending"')
    expect(html).toContain('Loading values…')
    expect(html).not.toContain('No finite values')
  })

  it('makes the Derived score preview terminal on source-facet errors', () => {
    expect(resolveScorePreviewState({
      histogram: null,
      populationItemsComplete: false,
      requiredStates: [],
    })).toBe('empty')
    expect(resolveScorePreviewState({
      histogram: null,
      populationItemsComplete: false,
      requiredStates: ['ready', 'error'],
    })).toBe('error')
    expect(resolveScorePreviewState({
      histogram: null,
      populationItemsComplete: true,
      requiredStates: ['error'],
    })).toBe('empty')
  })

  it('allows backend ranking without loading every source metric into card entities', () => {
    const html = renderToStaticMarkup(
      <DerivedScorePanel
        items={[makeItem('/a.jpg')]}
        metricKeys={['q1']}
        categoricalKeys={[]}
        derivedMetric={makeDerivedMetricEvaluation()}
        backendAuthoritative
        onApplyDerivedMetric={() => {}}
        onRankByDerivedMetric={() => {}}
      />,
    )

    const rankButton = html.match(/<button[^>]*data-derived-score-rank[^>]*>/)?.[0]
    expect(rankButton).toBeDefined()
    expect(rankButton).not.toContain('disabled')
  })

  it('keeps backend ranking disabled when the folder schema proves an input is unavailable', () => {
    const html = renderToStaticMarkup(
      <DerivedScorePanel
        items={[makeItem('/a.jpg')]}
        metricKeys={['q1']}
        categoricalKeys={[]}
        derivedMetric={makeDerivedMetricEvaluation({
          spec: {
            version: 1,
            id: 'stale_score',
            name: 'Stale score',
            intercept: 0,
            numericTerms: [{ key: 'q_old', weight: 1, missing: 'zero', zNormalize: false }],
            categoricalTerms: [],
          },
        })}
        backendAuthoritative
        onApplyDerivedMetric={() => {}}
        onRankByDerivedMetric={() => {}}
      />,
    )

    const rankButton = html.match(/<button[^>]*data-derived-score-rank[^>]*>/)?.[0]
    expect(rankButton).toBeDefined()
    expect(rankButton).toContain('disabled')
    expect(html).toContain('Unavailable inputs: q_old.')
  })

  it('uses derived metric display names in primary metric labels', () => {
    const items = [
      makeItem('/a.jpg', { '@derived/rubric_1': 0.2 }),
      makeItem('/b.jpg', { '@derived/rubric_1': 0.8 }),
    ]

    const html = renderToStaticMarkup(
      <MetricsPanel
        items={items}
        filteredItems={items}
        metricKeys={['@derived/rubric_1']}
        categoricalKeys={[]}
        metricDisplayNames={{ '@derived/rubric_1': 'Rubric score' }}
        selectedMetric="@derived/rubric_1"
        facetDemand={SINGLE_FIELD_DEMAND}
        onSelectMetric={() => {}}
        onFacetDemandAction={() => {}}
        filters={{ and: [] }}
        onChangeRange={() => {}}
        onChangeCategoricalValues={() => {}}
        onChangeFilters={() => {}}
      />,
    )

    expect(html).toContain('Rubric score')
    expect(html).not.toContain('>@derived/rubric_1<')
  })
})
