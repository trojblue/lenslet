import { describe, expect, it } from 'vitest'
import { renderToStaticMarkup } from 'react-dom/server'
import MetricsPanel from '../MetricsPanel'
import type { Item } from '../../../lib/types'

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
        selectedMetric="quality_score"
        onSelectMetric={() => {}}
        filters={{ and: [] }}
        onChangeRange={() => {}}
        onChangeFilters={() => {}}
      />,
    )

    expect(html).toContain('<option value="quality_score" selected="">quality_score</option>')
    expect(html).not.toContain('__index_level_0__')
  })
})
