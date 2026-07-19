import { describe, expect, it } from 'vitest'
import type { BrowseItemPayload } from '../../../../lib/types'
import {
  applyDerivedMetricFormulaCode,
  buildDerivedMetricFormulaCode,
  buildDerivedMetricFormulaPreview,
  buildDerivedMetricSpecFromDraft,
  collectCategoricalValuesByKey,
  createCategoricalDraftTerm,
  createDerivedMetricDraft,
  derivedMetricDraftResetToken,
  derivedMetricEditorResetToken,
  evaluateDerivedMetricDraft,
} from '../derivedMetricDraft'
import { evaluateBackendDerivedMetric, evaluateDerivedMetric } from '../derivedMetric'

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
    expect(buildDerivedMetricFormulaCode(draft)).toBe(
      'new_score = 2 + 0.5*znorm(q1) + 3 if dataset_from = gt',
    )
  })

  it('imports formula code into ordered available terms and preserves known missing policies', () => {
    const draft = createDerivedMetricDraft(null, ['q1', 'q2'])
    draft.numericTerms = [{ key: 'q1', weight: '1', missing: 'zero', zNormalize: false }]

    const result = applyDerivedMetricFormulaCode(
      'combo = 1 + 0.7*q1 - 0.2*znorm(q2) + 3 if source_column = gt',
      draft,
      {
        metricKeys: ['q1', 'q2'],
        categoricalKeys: ['source_column'],
      },
    )

    expect(result.applied).toBe(true)
    expect(result.diagnostics).toEqual({
      errors: [],
      missingMetricKeys: [],
      missingCategoricalKeys: [],
      skippedTerms: [],
    })
    expect(result.draft).toMatchObject({
      name: 'combo',
      intercept: '1',
      numericTerms: [
        { key: 'q1', weight: '0.7', missing: 'zero', zNormalize: false },
        { key: 'q2', weight: '-0.2', missing: 'invalid', zNormalize: true },
      ],
      categoricalTerms: [
        { key: 'source_column', value: 'gt', weight: '3' },
      ],
    })
  })

  it('fails closed when formula code references missing inputs', () => {
    const draft = createDerivedMetricDraft(null, ['q1'])

    const result = applyDerivedMetricFormulaCode(
      'score = 0 + 1*q1 + 2*missing_metric + 5 if missing_field = gt + 4 if source = train',
      draft,
      {
        metricKeys: ['q1'],
        categoricalKeys: ['source'],
      },
    )

    expect(result.applied).toBe(false)
    expect(result.draft).toBe(draft)
    expect(result.diagnostics.errors).toEqual(['Formula references unavailable inputs.'])
    expect(result.diagnostics.missingMetricKeys).toEqual(['missing_metric'])
    expect(result.diagnostics.missingCategoricalKeys).toEqual(['missing_field'])
    expect(result.diagnostics.skippedTerms).toEqual(['+ 2*missing_metric', '+ 5 if missing_field = gt'])
  })

  it('supports bracket-quoted formula tokens', () => {
    const draft = createDerivedMetricDraft(null, [])

    const result = applyDerivedMetricFormulaCode(
      'score = 0 + 0.5*[manual-score] + 2 if [source column] = [ptv-03]',
      draft,
      {
        metricKeys: ['manual-score'],
        categoricalKeys: ['source column'],
      },
    )

    expect(result.applied).toBe(true)
    expect(result.draft.numericTerms).toEqual([
      { key: 'manual-score', weight: '0.5', missing: 'invalid', zNormalize: false },
    ])
    expect(result.draft.categoricalTerms).toEqual([
      { key: 'source column', value: 'ptv-03', weight: '2' },
    ])
    expect(buildDerivedMetricFormulaCode(result.draft)).toBe(
      'score = 0 + 0.5*[manual-score] + 2 if [source column] = [ptv-03]',
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

  it('uses semantic spec and schema identity for editor resets', () => {
    const draft = createDerivedMetricDraft(null, ['q1'])
    const spec = buildDerivedMetricSpecFromDraft(draft).spec!
    const evaluation = evaluateDerivedMetric({
      items: [],
      metricKeys: ['q1', 'q2'],
      categoricalKeys: ['source'],
      spec,
    })
    const equivalentEvaluation = evaluateDerivedMetric({
      items: [],
      metricKeys: ['q2', 'q1'],
      categoricalKeys: ['source'],
      spec: {
        ...spec,
        numericTerms: spec.numericTerms.map((term) => ({ ...term })),
        categoricalTerms: spec.categoricalTerms.map((term) => ({ ...term })),
      },
    })
    const baseline = derivedMetricDraftResetToken(evaluation, ['q1', 'q2'], ['source'])

    expect(derivedMetricDraftResetToken(
      equivalentEvaluation,
      ['q2', 'q1'],
      ['source'],
    )).toBe(baseline)
    expect(derivedMetricDraftResetToken(evaluation, ['q1', 'q2', 'q3'], ['source'])).not.toBe(baseline)
    expect(derivedMetricDraftResetToken(
      evaluateDerivedMetric({
        items: [],
        metricKeys: ['q1', 'q2'],
        categoricalKeys: ['source'],
        spec: { ...spec, name: 'Changed score' },
      }),
      ['q1', 'q2'],
      ['source'],
    )).not.toBe(baseline)
  })

  it('distinguishes invalid saved definitions from an absent draft identity', () => {
    const invalid = evaluateDerivedMetric({
      items: [],
      metricKeys: ['q1'],
      categoricalKeys: [],
      spec: {
        version: 1,
        id: 'broken_score',
        name: 'Broken score',
        intercept: Number.NaN,
        numericTerms: [],
        categoricalTerms: [],
      },
    })
    const absent = evaluateDerivedMetric({
      items: [],
      metricKeys: ['q1'],
      categoricalKeys: [],
      spec: null,
    })

    expect(invalid.status).toBe('invalid')
    expect(derivedMetricDraftResetToken(invalid, ['q1'], [])).not.toBe(
      derivedMetricDraftResetToken(absent, ['q1'], []),
    )
  })

  it('ignores backend status changes for the same valid saved definition', () => {
    const spec = buildDerivedMetricSpecFromDraft(createDerivedMetricDraft(null, ['q1'])).spec!
    const pending = evaluateBackendDerivedMetric({
      items: [],
      metricKeys: ['q1'],
      categoricalKeys: [],
      spec,
      backendStatus: null,
    })
    const invalid = evaluateBackendDerivedMetric({
      items: [],
      metricKeys: ['q1'],
      categoricalKeys: [],
      spec,
      backendStatus: {
        key: '@derived/score_v1',
        display_name: spec.name,
        status: 'invalid',
        score_scope: 'none',
        score_population_count: 0,
        valid_count: 0,
        invalid_count: 0,
        missing_numeric_inputs: [],
        unavailable_categorical_inputs: [],
        z_stats: {},
      },
    })

    expect(derivedMetricDraftResetToken(invalid, ['q1'], [])).toBe(
      derivedMetricDraftResetToken(pending, ['q1'], []),
    )
  })

  it('shares the presentation hard-reset boundary with the Derived editor owner', () => {
    const evaluation = evaluateDerivedMetric({
      items: [],
      metricKeys: ['q1'],
      categoricalKeys: [],
      spec: null,
    })

    expect(derivedMetricEditorResetToken(evaluation, 'workspace-a')).toBe(
      derivedMetricEditorResetToken(evaluation, 'workspace-a'),
    )
    expect(derivedMetricEditorResetToken(evaluation, 'workspace-a')).not.toBe(
      derivedMetricEditorResetToken(evaluation, 'workspace-b'),
    )
    expect(derivedMetricEditorResetToken(evaluation, 'workspace-a')).toBe(
      derivedMetricEditorResetToken({ ...evaluation, metricKeys: [] }, 'workspace-a'),
    )
  })

  it('keys malformed saved definitions by their canonical raw content', () => {
    const evaluateInvalid = (spec: Record<string, unknown>) => evaluateDerivedMetric({
      items: [],
      metricKeys: ['q1'],
      categoricalKeys: [],
      spec,
    })
    const first = evaluateInvalid({
      version: 1,
      id: 'broken_score',
      name: 'Broken score',
      intercept: 'not-a-number',
      numericTerms: [],
      categoricalTerms: [],
    })
    const reordered = evaluateInvalid({
      categoricalTerms: [],
      numericTerms: [],
      intercept: 'not-a-number',
      name: 'Broken score',
      id: 'broken_score',
      version: 1,
    })
    const changed = evaluateInvalid({
      version: 1,
      id: 'broken_score',
      name: 'Broken score',
      intercept: 'still-not-a-number',
      numericTerms: [],
      categoricalTerms: [],
    })

    expect(derivedMetricDraftResetToken(reordered, ['q1'], [])).toBe(
      derivedMetricDraftResetToken(first, ['q1'], []),
    )
    expect(derivedMetricDraftResetToken(changed, ['q1'], [])).not.toBe(
      derivedMetricDraftResetToken(first, ['q1'], []),
    )
  })
})
