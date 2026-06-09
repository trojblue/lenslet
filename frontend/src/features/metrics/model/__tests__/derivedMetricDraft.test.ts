import { describe, expect, it } from 'vitest'
import type { BrowseItemPayload } from '../../../../lib/types'
import {
  buildDerivedMetricFormulaPreview,
  buildDerivedMetricSpecFromDraft,
  collectCategoricalValuesByKey,
  createCategoricalDraftTerm,
  createDerivedMetricDraft,
  evaluateDerivedMetricDraft,
} from '../derivedMetricDraft'

function makeItem(path: string, options: {
  metrics?: BrowseItemPayload['metrics']
  categoricals?: BrowseItemPayload['categoricals']
} = {}): BrowseItemPayload {
  return {
    path,
    name: path.split('/').pop() ?? path,
    mime: 'image/jpeg',
    width: 10,
    height: 10,
    size: 1,
    has_thumbnail: true,
    has_metadata: true,
    metrics: options.metrics,
    categoricals: options.categoricals,
  }
}

describe('derived metric drafts', () => {
  it('builds a valid spec and formula preview from a draft', () => {
    const draft = createDerivedMetricDraft(null, ['q1'])
    draft.name = 'new_score'
    draft.intercept = '2'
    draft.numericTerms = [
      { key: 'q1', weight: '0.5', missing: 'zero', zNormalize: true },
    ]
    draft.categoricalTerms = [
      { key: 'dataset_from', value: 'gt', weight: '3' },
    ]

    const build = buildDerivedMetricSpecFromDraft(draft)

    expect(build.errors).toEqual([])
    expect(build.spec).toMatchObject({
      version: 1,
      id: 'score_v1',
      name: 'new_score',
      intercept: 2,
      numericTerms: [{ key: 'q1', weight: 0.5, missing: 'zero', zNormalize: true }],
      categoricalTerms: [{ key: 'dataset_from', value: 'gt', weight: 3 }],
    })
    expect(buildDerivedMetricFormulaPreview(draft, { q1: 'Question 1' })).toBe(
      'new_score = 2 + 0.5*znorm(Question 1) + 3 if dataset_from = gt',
    )
  })

  it('reports missing fields before apply', () => {
    const draft = createDerivedMetricDraft(null, [])
    draft.intercept = ''
    draft.numericTerms = [{ key: '', weight: '', missing: 'invalid', zNormalize: false }]

    const build = buildDerivedMetricSpecFromDraft(draft)

    expect(build.spec).toBeNull()
    expect(build.errors).toContain('Intercept must be finite.')
    expect(build.errors).toContain('Numeric term 1 needs a metric.')
    expect(build.errors).toContain('Numeric term 1 needs a finite weight.')
  })

  it('computes valid and invalid draft counts for rank gating', () => {
    const draft = createDerivedMetricDraft(null, ['q1'])
    draft.numericTerms = [{ key: 'q1', weight: '1', missing: 'invalid', zNormalize: false }]
    const items = [
      makeItem('/a.jpg', { metrics: { q1: 2 } }),
      makeItem('/b.jpg', { metrics: { q1: null } }),
    ]

    const state = evaluateDerivedMetricDraft(draft, {
      items,
      metricKeys: ['q1'],
      categoricalKeys: [],
    })

    expect(state.disabledReason).toBeNull()
    expect(state.evaluation?.validCount).toBe(1)
    expect(state.evaluation?.invalidCount).toBe(1)
  })

  it('collects categorical value options and defaults new categorical rows', () => {
    const items = [
      makeItem('/a.jpg', { categoricals: { dataset_from: 'gt' } }),
      makeItem('/b.jpg', { categoricals: { dataset_from: 'train' } }),
    ]
    const valuesByKey = collectCategoricalValuesByKey(items, ['dataset_from'])

    expect(valuesByKey.get('dataset_from')).toEqual(['gt', 'train'])
    expect(createCategoricalDraftTerm(['dataset_from'], valuesByKey)).toEqual({
      key: 'dataset_from',
      value: 'gt',
      weight: '1',
    })
  })
})
