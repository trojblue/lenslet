import { describe, expect, it } from 'vitest'
import { renderToStaticMarkup } from 'react-dom/server'
import type { BrowseItemPayload } from '../../../../lib/types'
import MetricRangePanel from '../MetricRangePanel'

function makeItem(
  path: string,
  metrics?: BrowseItemPayload['metrics'],
  metricLabels?: BrowseItemPayload['metric_labels'],
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
    metrics,
    metric_labels: metricLabels,
  }
}

describe('MetricRangePanel', () => {
  it('renders provided metric keys in the metric selector', () => {
    const html = renderToStaticMarkup(
      <MetricRangePanel
        items={[
          makeItem('/a.jpg', { quality_score: 0.9 }),
          makeItem('/b.jpg', { quality_score: 0.2 }),
        ]}
        filteredItems={[
          makeItem('/a.jpg', { quality_score: 0.9 }),
          makeItem('/b.jpg', { quality_score: 0.2 }),
        ]}
        metricKeys={['quality_score']}
        selectedMetric="quality_score"
        onSelectMetric={() => {}}
        filters={{ and: [] }}
        onChangeRange={() => {}}
      />,
    )

    expect(html).toContain('data-metric-selector')
    expect(html).toContain('data-metric-card-host="quality_score"')
    expect(html).toContain('quality_score')
    expect(html).toContain('Population: 2')
  })

  it('renders classification metric labels as category choices', () => {
    const html = renderToStaticMarkup(
      <MetricRangePanel
        items={[
          makeItem('/a.jpg', { l0p_style_family: 0 }, { l0p_style_family: 'anime' }),
          makeItem('/b.jpg', { l0p_style_family: 1 }, { l0p_style_family: 'photographic' }),
        ]}
        filteredItems={[
          makeItem('/a.jpg', { l0p_style_family: 0 }, { l0p_style_family: 'anime' }),
        ]}
        metricKeys={['l0p_style_family']}
        selectedMetric="l0p_style_family"
        onSelectMetric={() => {}}
        filters={{ and: [] }}
        onChangeRange={() => {}}
      />,
    )

    expect(html).toContain('anime')
    expect(html).toContain('photographic')
    expect(html).toContain('Filtered: 1')
    expect(html).toContain('0/1')
  })

  it('keeps the population histogram domain while a metric range is selected', () => {
    const html = renderToStaticMarkup(
      <MetricRangePanel
        items={[]}
        filteredItems={[]}
        metricKeys={['quality_score']}
        facets={{
          version: 1,
          path: '/',
          generated_at: 'test',
          total_items: 100,
          metric_keys: ['quality_score'],
          categorical_keys: [],
          metrics: {
            quality_score: {
              histogram: {
                bins: Array.from({ length: 40 }, (_, index) => index === 0 ? 100 : 0),
                min: 0,
                max: 100,
                count: 100,
              },
              categories: [],
            },
          },
          categoricals: {},
          dependency_manifest: {
            fields: [],
            metric_keys: ['quality_score'],
            categorical_keys: [],
            unknown: false,
          },
        }}
        populationItemsComplete={false}
        filteredItemsComplete={false}
        selectedMetric="quality_score"
        onSelectMetric={() => {}}
        filters={{ and: [{ metricRange: { key: 'quality_score', min: 40, max: 60 } }] }}
        onChangeRange={() => {}}
      />,
    )

    expect(html).toContain('Population: 100')
    expect(html).toContain('placeholder="0"')
    expect(html).toContain('placeholder="100"')
    expect(html).toContain('40.00 – 60.00')
  })

  it('does not substitute a complete filtered slice for a pending population', () => {
    const filteredItems = [
      makeItem('/a.jpg', { quality_score: 0.4 }),
      makeItem('/b.jpg', { quality_score: 0.6 }),
    ]
    const html = renderToStaticMarkup(
      <MetricRangePanel
        items={filteredItems}
        filteredItems={filteredItems}
        metricKeys={['quality_score']}
        populationItemsComplete={false}
        filteredItemsComplete
        facetsState="pending"
        selectedMetric="quality_score"
        onSelectMetric={() => {}}
        filters={{ and: [{ metricRange: { key: 'quality_score', min: 0.4, max: 0.6 } }] }}
        onChangeRange={() => {}}
      />,
    )

    expect(html).toContain('data-facet-state="pending"')
    expect(html).toContain('Loading values for this metric…')
    expect(html).not.toContain('Population: 2')
  })
})
