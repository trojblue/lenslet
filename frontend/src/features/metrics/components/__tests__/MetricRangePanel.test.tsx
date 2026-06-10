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
})
