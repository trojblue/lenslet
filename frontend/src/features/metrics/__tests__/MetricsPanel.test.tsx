import { describe, expect, it } from 'vitest'
import { renderToStaticMarkup } from 'react-dom/server'
import MetricsPanel from '../MetricsPanel'
import type { BrowseItemPayload } from '../../../lib/types'
import type { DerivedMetricEvaluation } from '../model/derivedMetric'

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

function makeDerivedMetricEvaluation(
  overrides: Partial<DerivedMetricEvaluation> = {},
): DerivedMetricEvaluation {
  return {
    items: [],
    metricKeys: [],
    categoricalKeys: [],
    metricDisplayNames: {},
    spec: null,
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
        derivedMetric={makeDerivedMetricEvaluation()}
        selectedMetric="quality_score"
        onSelectMetric={() => {}}
        onApplyDerivedMetric={() => {}}
        onRankByDerivedMetric={() => {}}
        filters={{ and: [] }}
        onChangeRange={() => {}}
        onChangeCategoricalValues={() => {}}
        onChangeFilters={() => {}}
      />,
    )

    expect(html).toContain('<option value="quality_score" selected="">quality_score</option>')
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
        derivedMetric={makeDerivedMetricEvaluation()}
        onSelectMetric={() => {}}
        onApplyDerivedMetric={() => {}}
        onRankByDerivedMetric={() => {}}
        filters={{ and: [] }}
        onChangeRange={() => {}}
        onChangeCategoricalValues={() => {}}
        onChangeFilters={() => {}}
      />,
    )

    expect(html).toContain('<option value="l0r_viewpoint_family" selected="">l0r_viewpoint_family</option>')
    expect(html).toContain('frontal')
    expect(html).toContain('profile')
    expect(html).toContain('Filtered: 1')
  })

  it('renders the derived score card even when no source inputs exist', () => {
    const html = renderToStaticMarkup(
      <MetricsPanel
        items={[]}
        filteredItems={[]}
        metricKeys={[]}
        categoricalKeys={[]}
        derivedMetric={makeDerivedMetricEvaluation()}
        onSelectMetric={() => {}}
        onApplyDerivedMetric={() => {}}
        onRankByDerivedMetric={() => {}}
        filters={{ and: [] }}
        onChangeRange={() => {}}
        onChangeCategoricalValues={() => {}}
        onChangeFilters={() => {}}
      />,
    )

    expect(html).toContain('Derived Score')
    expect(html).toContain('No score inputs in this view.')
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
        derivedMetric={makeDerivedMetricEvaluation({
          key: '@derived/rubric_1',
          name: 'Rubric score',
          status: 'valid',
          metricKeys: ['@derived/rubric_1'],
          metricDisplayNames: { '@derived/rubric_1': 'Rubric score' },
        })}
        selectedMetric="@derived/rubric_1"
        onSelectMetric={() => {}}
        onApplyDerivedMetric={() => {}}
        onRankByDerivedMetric={() => {}}
        filters={{ and: [] }}
        onChangeRange={() => {}}
        onChangeCategoricalValues={() => {}}
        onChangeFilters={() => {}}
      />,
    )

    expect(html).toContain('>Rubric score</option>')
    expect(html).not.toContain('>@derived/rubric_1</option>')
  })
})
