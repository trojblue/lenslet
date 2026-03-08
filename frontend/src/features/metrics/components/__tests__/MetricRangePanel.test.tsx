import { describe, expect, it } from 'vitest'
import { renderToStaticMarkup } from 'react-dom/server'
import type { Item } from '../../../../lib/types'
import MetricRangePanel from '../MetricRangePanel'

function makeItem(path: string, metrics?: Item['metrics']): Item {
  return {
    path,
    name: path.split('/').pop() ?? path,
    type: 'image/jpeg',
    w: 100,
    h: 100,
    size: 1,
    hasThumb: true,
    hasMeta: true,
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
