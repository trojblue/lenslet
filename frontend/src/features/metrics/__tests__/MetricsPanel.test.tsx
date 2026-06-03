import { describe, expect, it } from 'vitest'
import { renderToStaticMarkup } from 'react-dom/server'
import MetricsPanel from '../MetricsPanel'
import type { BrowseItemPayload } from '../../../lib/types'

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
        selectedMetric="quality_score"
        onSelectMetric={() => {}}
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
        onSelectMetric={() => {}}
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
})
