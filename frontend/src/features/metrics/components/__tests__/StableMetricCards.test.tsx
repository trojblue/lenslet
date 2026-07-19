import { describe, expect, it } from 'vitest'
import { renderToStaticMarkup } from 'react-dom/server'
import CategoricalCard from '../CategoricalCard'
import MetricCategoryCard from '../MetricCategoryCard'
import MetricHistogramCard, { projectRangeInput } from '../MetricHistogramCard'

describe('stable metric card regions', () => {
  it('projects committed histogram bounds without an effect-late mirror', () => {
    expect(projectRangeInput(0, 0)).toBe('')
    expect(projectRangeInput(0.25, 0)).toBe('0.25')
    expect(projectRangeInput(undefined, 0)).toBe('')
  })

  it('keeps categorical Clear in one slot without rendering redundant Active copy', () => {
    const render = (active: boolean) => renderToStaticMarkup(
      <CategoricalCard
        categoricalKey="dataset_from"
        buckets={[
          { value: 'gt', populationCount: 793, filteredCount: 793, selectedCount: 0 },
          { value: 'synthetic', populationCount: 792, filteredCount: 792, selectedCount: 0 },
        ]}
        filters={{ and: active ? [{ categoricalIn: { key: 'dataset_from', values: ['gt'] } }] : [] }}
        onChangeValues={() => {}}
      />,
    )

    const inactive = render(false)
    const active = render(true)
    expect(inactive).toContain('data-card-action="clear"')
    expect(inactive).toContain('invisible')
    expect(active).toContain('data-card-action="clear"')
    expect(active).not.toContain('Active:')
    const activeClear = active.match(/<button[^>]*data-card-action="clear"[^>]*>/)?.[0]
    expect(activeClear).toBeDefined()
    expect(activeClear).not.toContain('invisible')
  })

  it('keeps metric-category Clear in one slot without rendering redundant Active copy', () => {
    const html = renderToStaticMarkup(
      <MetricCategoryCard
        metricKey="quality_class"
        categories={[
          { code: 0, label: 'low', populationCount: 10, filteredCount: 10, selectedCount: 0 },
          { code: 1, label: 'high', populationCount: 10, filteredCount: 10, selectedCount: 0 },
        ]}
        filters={{ and: [{ metricRange: { key: 'quality_class', min: 1, max: 1 } }] }}
        onChangeRange={() => {}}
      />,
    )

    expect(html).toContain('data-card-action="clear"')
    expect(html).not.toContain('Active:')
  })

  it('uses one fixed no-wrap histogram information slot', () => {
    const html = renderToStaticMarkup(
      <MetricHistogramCard
        metricKey="quality_score"
        populationValues={[0, 0.5, 1]}
        filteredValues={[0, 0.5, 1]}
        filters={{ and: [{ metricRange: { key: 'quality_score', min: 0.25, max: 0.75 } }] }}
        onChangeRange={() => {}}
      />,
    )

    expect(html).toContain('data-histogram-footer="true"')
    expect(html).toContain('whitespace-nowrap')
    expect(html).toContain('0.250 – 0.750')
    expect(html).toContain('data-card-action="clear"')
  })

  it('uses the same fixed card and body shells for pending, empty, and ready content', () => {
    const render = (state: 'pending' | 'error' | 'ready', values: number[]) => renderToStaticMarkup(
      <MetricHistogramCard
        metricKey="quality_score"
        populationValues={values}
        filteredValues={values}
        state={state}
        filters={{ and: [] }}
        onChangeRange={() => {}}
      />,
    )

    for (const html of [render('pending', []), render('error', []), render('ready', []), render('ready', [1, 2])]) {
      expect(html).toContain('ui-card flex h-96 flex-col')
      expect(html).toContain('data-histogram-footer="true"')
      expect(html).toContain('data-card-action="clear"')
    }
  })

  it('keeps header and row count roles present when filtering and selection are inactive', () => {
    const html = renderToStaticMarkup(
      <CategoricalCard
        categoricalKey="dataset_from"
        buckets={[
          { value: 'gt', populationCount: 10, filteredCount: 0, selectedCount: 0 },
        ]}
        filters={{ and: [] }}
        showFilteredCounts={false}
        onChangeValues={() => {}}
      />,
    )

    expect(html).toContain('data-count-role="filtered"')
    expect(html).toContain('Filtered: —')
    expect(html).toContain('data-count-role="selected"')
    expect(html).toContain('Selected: 0')
    expect(html).toContain('data-count-role="row-selected"')
    expect(html).toContain('data-count-role="row-filtered-population"')
  })
})
