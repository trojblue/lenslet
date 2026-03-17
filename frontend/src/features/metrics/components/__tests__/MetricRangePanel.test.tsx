import { describe, expect, it } from 'vitest'
import { renderToStaticMarkup } from 'react-dom/server'
import type { BrowseItemPayload } from '../../../../lib/types'
import MetricRangePanel from '../MetricRangePanel'

function makeItem(path: string, metrics?: BrowseItemPayload['metrics']): BrowseItemPayload {
  return {
    path,
    name: path.split('/').pop() ?? path,
    mime: 'image/jpeg',
    width: 100,
    height: 100,
    size: 1,
    hasThumbnail: true,
    hasMetadata: true,
    metrics,
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

    expect(html).toContain('<option value="quality_score" selected="">quality_score</option>')
    expect(html).toContain('Population: 2')
  })
})
