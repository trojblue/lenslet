import type {
  BrowseItemPayload,
  DerivedMetricCategoricalTerm,
  DerivedMetricNumericMissingPolicy,
  DerivedMetricNumericTerm,
  DerivedMetricSpec,
  MetricDisplayNames,
} from '../../../lib/types'
import { getMetricDisplayName } from '../../../lib/metricDisplay'
import {
  DERIVED_METRIC_PREFIX,
  evaluateDerivedMetric,
  isDerivedMetricKey,
  type DerivedMetricEvaluation,
} from './derivedMetric'

export type DerivedMetricNumericDraftTerm = {
  key: string
  weight: string
  missing: DerivedMetricNumericMissingPolicy
  zNormalize: boolean
}

export type DerivedMetricCategoricalDraftTerm = {
  key: string
  value: string
  weight: string
}

export type DerivedMetricDraft = {
  id: string
  name: string
  intercept: string
  numericTerms: DerivedMetricNumericDraftTerm[]
  categoricalTerms: DerivedMetricCategoricalDraftTerm[]
}

export type DerivedMetricDraftBuild = {
  spec: DerivedMetricSpec | null
  errors: string[]
}

export type DerivedMetricDraftRankState = {
  disabledReason: string | null
  evaluation: DerivedMetricEvaluation | null
}

const DEFAULT_DERIVED_METRIC_ID = 'score_v1'
const DEFAULT_DERIVED_METRIC_NAME = 'new_score'
const DEFAULT_WEIGHT = '1'

export function createDerivedMetricDraft(
  spec: DerivedMetricSpec | null,
  metricKeys: readonly string[],
): DerivedMetricDraft {
  if (spec) {
    return {
      id: spec.id,
      name: spec.name,
      intercept: formatDraftNumber(spec.intercept),
      numericTerms: spec.numericTerms.map((term) => ({
        key: term.key,
        weight: formatDraftNumber(term.weight),
        missing: term.missing,
        zNormalize: term.zNormalize,
      })),
      categoricalTerms: spec.categoricalTerms.map((term) => ({
        key: term.key,
        value: term.value,
        weight: formatDraftNumber(term.weight),
      })),
    }
  }

  return {
    id: DEFAULT_DERIVED_METRIC_ID,
    name: DEFAULT_DERIVED_METRIC_NAME,
    intercept: '0',
    numericTerms: metricKeys[0]
      ? [{ key: metricKeys[0], weight: DEFAULT_WEIGHT, missing: 'invalid', zNormalize: false }]
      : [],
    categoricalTerms: [],
  }
}

export function createNumericDraftTerm(metricKeys: readonly string[]): DerivedMetricNumericDraftTerm {
  return {
    key: metricKeys[0] ?? '',
    weight: DEFAULT_WEIGHT,
    missing: 'invalid',
    zNormalize: false,
  }
}

export function createCategoricalDraftTerm(
  categoricalKeys: readonly string[],
  categoricalValuesByKey: ReadonlyMap<string, readonly string[]>,
): DerivedMetricCategoricalDraftTerm {
  const key = categoricalKeys[0] ?? ''
  return {
    key,
    value: categoricalValuesByKey.get(key)?.[0] ?? '',
    weight: DEFAULT_WEIGHT,
  }
}

export function buildDerivedMetricSpecFromDraft(draft: DerivedMetricDraft): DerivedMetricDraftBuild {
  const errors: string[] = []
  const id = normalizeDerivedId(draft.id)
  const name = draft.name.trim() || DEFAULT_DERIVED_METRIC_NAME
  const intercept = parseFiniteDraftNumber(draft.intercept)

  if (!id) errors.push('Score id is invalid.')
  if (intercept == null) errors.push('Intercept must be finite.')

  const numericTerms: DerivedMetricNumericTerm[] = []
  draft.numericTerms.forEach((term, index) => {
    const key = term.key.trim()
    const weight = parseFiniteDraftNumber(term.weight)
    if (!key) errors.push(`Numeric term ${index + 1} needs a metric.`)
    if (isDerivedMetricKey(key)) errors.push(`Numeric term ${index + 1} cannot use a derived score.`)
    if (weight == null) errors.push(`Numeric term ${index + 1} needs a finite weight.`)
    if (term.missing !== 'zero' && term.missing !== 'invalid') {
      errors.push(`Numeric term ${index + 1} has an invalid missing policy.`)
    }
    if (key && !isDerivedMetricKey(key) && weight != null && (term.missing === 'zero' || term.missing === 'invalid')) {
      numericTerms.push({ key, weight, missing: term.missing, zNormalize: term.zNormalize })
    }
  })

  const categoricalTerms: DerivedMetricCategoricalTerm[] = []
  draft.categoricalTerms.forEach((term, index) => {
    const key = term.key.trim()
    const value = term.value.trim()
    const weight = parseFiniteDraftNumber(term.weight)
    if (!key) errors.push(`Categorical term ${index + 1} needs a field.`)
    if (isDerivedMetricKey(key)) errors.push(`Categorical term ${index + 1} cannot use a derived score.`)
    if (!value) errors.push(`Categorical term ${index + 1} needs a value.`)
    if (weight == null) errors.push(`Categorical term ${index + 1} needs a finite weight.`)
    if (key && !isDerivedMetricKey(key) && value && weight != null) {
      categoricalTerms.push({ key, value, weight })
    }
  })

  if (!numericTerms.length && !categoricalTerms.length) {
    errors.push('Add at least one score term.')
  }

  if (errors.length || !id || intercept == null) return { spec: null, errors }
  return {
    spec: {
      version: 1,
      id,
      name,
      intercept,
      numericTerms,
      categoricalTerms,
    },
    errors: [],
  }
}

export function buildDerivedMetricFormulaPreview(
  draft: DerivedMetricDraft,
  metricDisplayNames?: MetricDisplayNames | null,
): string {
  const name = draft.name.trim() || DEFAULT_DERIVED_METRIC_NAME
  const parts = [draft.intercept.trim() || '0']
  for (const term of draft.numericTerms) {
    const key = term.key.trim() || '?'
    const weight = term.weight.trim() || '?'
    const value = term.zNormalize
      ? `znorm(${getMetricDisplayName(key, metricDisplayNames)})`
      : getMetricDisplayName(key, metricDisplayNames)
    parts.push(`${weight}*${value}`)
  }
  for (const term of draft.categoricalTerms) {
    const key = term.key.trim() || '?'
    const value = term.value.trim() || '?'
    const weight = term.weight.trim() || '?'
    parts.push(`${weight} if ${key} = ${value}`)
  }
  return `${name} = ${parts.join(' + ')}`
}

export function evaluateDerivedMetricDraft(
  draft: DerivedMetricDraft,
  params: {
    items: BrowseItemPayload[]
    metricKeys: readonly string[]
    categoricalKeys: readonly string[]
    rankDisabledReason?: string | null
  },
): DerivedMetricDraftRankState {
  const build = buildDerivedMetricSpecFromDraft(draft)
  if (!build.spec) {
    return {
      disabledReason: build.errors[0] ?? 'Score definition is invalid.',
      evaluation: null,
    }
  }

  const evaluation = evaluateDerivedMetric({
    items: params.items,
    metricKeys: params.metricKeys,
    categoricalKeys: params.categoricalKeys,
    spec: build.spec,
    loadedCount: params.items.length,
    totalItems: params.items.length,
  })
  if (params.rankDisabledReason) return { disabledReason: params.rankDisabledReason, evaluation }
  if (evaluation.status === 'unavailable') return { disabledReason: 'Score inputs are unavailable.', evaluation }
  if (evaluation.status === 'invalid') return { disabledReason: evaluation.invalidReasons[0] ?? 'Score definition is invalid.', evaluation }
  if (evaluation.validCount <= 0) return { disabledReason: 'Score has no valid values.', evaluation }
  return { disabledReason: null, evaluation }
}

export function collectCategoricalValuesByKey(
  items: readonly BrowseItemPayload[],
  categoricalKeys: readonly string[],
): Map<string, string[]> {
  const byKey = new Map<string, Set<string>>()
  for (const key of categoricalKeys) byKey.set(key, new Set())
  for (const item of items) {
    for (const key of categoricalKeys) {
      const value = item.categoricals?.[key]?.trim()
      if (value) byKey.get(key)?.add(value)
    }
  }
  return new Map(
    Array.from(byKey.entries()).map(([key, values]) => [key, Array.from(values).sort()]),
  )
}

function normalizeDerivedId(value: string): string | null {
  const id = value.trim()
  if (!id || id.startsWith(DERIVED_METRIC_PREFIX)) return null
  return /^[A-Za-z0-9][A-Za-z0-9_-]{0,79}$/.test(id) ? id : null
}

function parseFiniteDraftNumber(value: string): number | null {
  const trimmed = value.trim()
  if (!trimmed) return null
  const parsed = Number(trimmed)
  return Number.isFinite(parsed) ? parsed : null
}

function formatDraftNumber(value: number): string {
  return Number.isInteger(value) ? String(value) : String(Number(value.toPrecision(12)))
}
