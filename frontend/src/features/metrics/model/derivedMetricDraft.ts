import type {
  BrowseFacetFields,
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

export type DerivedMetricFormulaDiagnostics = {
  errors: string[]
  missingMetricKeys: string[]
  missingCategoricalKeys: string[]
  skippedTerms: string[]
}

export type DerivedMetricFormulaApplyResult = {
  draft: DerivedMetricDraft
  diagnostics: DerivedMetricFormulaDiagnostics
  applied: boolean
}

const DEFAULT_DERIVED_METRIC_ID = 'score_v1'
const DEFAULT_DERIVED_METRIC_NAME = 'new_score'
const DEFAULT_WEIGHT = '1'
const SIMPLE_FORMULA_TOKEN_RE = /^[A-Za-z0-9_./:]+$/

export function derivedMetricDraftResetToken(
  evaluation: DerivedMetricEvaluation,
  metricKeys: readonly string[],
  categoricalKeys: readonly string[],
): string {
  const definition = evaluation.spec
    ? {
      kind: 'valid',
      version: evaluation.spec.version,
      id: evaluation.spec.id,
      name: evaluation.spec.name,
      intercept: evaluation.spec.intercept,
      numericTerms: evaluation.spec.numericTerms.map((term) => ({
        key: term.key,
        weight: term.weight,
        missing: term.missing,
        zNormalize: term.zNormalize,
      })),
      categoricalTerms: evaluation.spec.categoricalTerms.map((term) => ({
        key: term.key,
        value: term.value,
        weight: term.weight,
      })),
    }
    : evaluation.definitionIdentity == null
      ? null
      : { kind: 'invalid', identity: evaluation.definitionIdentity }
  return JSON.stringify({
    definition,
    metricKeys: Array.from(new Set(metricKeys)).sort(),
    categoricalKeys: Array.from(new Set(categoricalKeys)).sort(),
  })
}

export function derivedMetricEditorResetToken(
  evaluation: DerivedMetricEvaluation,
  hardResetKey: string,
): string {
  return JSON.stringify([
    hardResetKey,
    derivedMetricDraftResetToken(evaluation, [], []),
  ])
}

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

export function derivedFacetFieldsFromDraft(draft: DerivedMetricDraft): BrowseFacetFields {
  return {
    metric_keys: uniqueDraftFieldKeys(draft.numericTerms),
    categorical_keys: uniqueDraftFieldKeys(draft.categoricalTerms),
  }
}

function uniqueDraftFieldKeys(terms: readonly { key: string }[]): string[] {
  return Array.from(new Set(
    terms.map((term) => term.key.trim()).filter(Boolean),
  )).sort()
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

export function buildDerivedMetricFormulaCode(draft: DerivedMetricDraft): string {
  const name = draft.name.trim() || DEFAULT_DERIVED_METRIC_NAME
  const parts = [draft.intercept.trim() || '0']
  for (const term of draft.numericTerms) {
    const key = term.key.trim() || '?'
    const weight = term.weight.trim() || '?'
    const value = term.zNormalize
      ? `znorm(${formatFormulaToken(key)})`
      : formatFormulaToken(key)
    parts.push(`${weight}*${value}`)
  }
  for (const term of draft.categoricalTerms) {
    const key = term.key.trim() || '?'
    const value = term.value.trim() || '?'
    const weight = term.weight.trim() || '?'
    parts.push(`${weight} if ${formatFormulaToken(key)} = ${formatFormulaToken(value)}`)
  }
  return `${name} = ${parts.join(' + ')}`
}

export function applyDerivedMetricFormulaCode(
  formula: string,
  currentDraft: DerivedMetricDraft,
  options: {
    metricKeys: readonly string[]
    categoricalKeys: readonly string[]
  },
): DerivedMetricFormulaApplyResult {
  const diagnostics: DerivedMetricFormulaDiagnostics = {
    errors: [],
    missingMetricKeys: [],
    missingCategoricalKeys: [],
    skippedTerms: [],
  }
  const availableMetrics = new Set(options.metricKeys)
  const availableCategoricals = new Set(options.categoricalKeys)
  const source = formula.trim()
  if (!source) {
    return {
      draft: currentDraft,
      diagnostics: { ...diagnostics, errors: ['Formula is empty.'] },
      applied: false,
    }
  }

  const split = splitFormulaAssignment(source)
  const terms = splitFormulaTerms(split.rhs)
  if (!terms.length) {
    return {
      draft: currentDraft,
      diagnostics: { ...diagnostics, errors: ['Formula has no terms.'] },
      applied: false,
    }
  }

  let intercept = 0
  let sawIntercept = false
  const numericTerms: DerivedMetricNumericDraftTerm[] = []
  const categoricalTerms: DerivedMetricCategoricalDraftTerm[] = []
  const missingMetricKeys = new Set<string>()
  const missingCategoricalKeys = new Set<string>()

  for (const rawTerm of terms) {
    const parsed = parseFormulaTerm(rawTerm)
    if (parsed.kind === 'invalid') {
      diagnostics.errors.push(parsed.error)
      diagnostics.skippedTerms.push(rawTerm.trim())
      continue
    }
    if (parsed.kind === 'intercept') {
      intercept += parsed.value
      sawIntercept = true
      continue
    }
    if (parsed.kind === 'numeric') {
      if (!availableMetrics.has(parsed.key)) {
        missingMetricKeys.add(parsed.key)
        diagnostics.skippedTerms.push(rawTerm.trim())
        continue
      }
      numericTerms.push({
        key: parsed.key,
        weight: formatDraftNumber(parsed.weight),
        missing: existingMissingPolicy(currentDraft, parsed.key),
        zNormalize: parsed.zNormalize,
      })
      continue
    }
    if (!availableCategoricals.has(parsed.key)) {
      missingCategoricalKeys.add(parsed.key)
      diagnostics.skippedTerms.push(rawTerm.trim())
      continue
    }
    categoricalTerms.push({
      key: parsed.key,
      value: parsed.value,
      weight: formatDraftNumber(parsed.weight),
    })
  }

  diagnostics.missingMetricKeys = Array.from(missingMetricKeys).sort()
  diagnostics.missingCategoricalKeys = Array.from(missingCategoricalKeys).sort()
  if (diagnostics.missingMetricKeys.length || diagnostics.missingCategoricalKeys.length) {
    return {
      draft: currentDraft,
      diagnostics: {
        ...diagnostics,
        errors: ['Formula references unavailable inputs.'],
      },
      applied: false,
    }
  }
  if (!numericTerms.length && !categoricalTerms.length && !sawIntercept) {
    return {
      draft: currentDraft,
      diagnostics: {
        ...diagnostics,
        errors: diagnostics.errors.length ? diagnostics.errors : ['Formula has no usable terms.'],
      },
      applied: false,
    }
  }

  return {
    draft: {
      ...currentDraft,
      name: split.name ?? currentDraft.name,
      intercept: formatDraftNumber(intercept),
      numericTerms,
      categoricalTerms,
    },
    diagnostics,
    applied: true,
  }
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

type ParsedFormulaTerm =
  | { kind: 'intercept'; value: number }
  | { kind: 'numeric'; key: string; weight: number; zNormalize: boolean }
  | { kind: 'categorical'; key: string; value: string; weight: number }
  | { kind: 'invalid'; error: string }

function splitFormulaAssignment(source: string): { name: string | null; rhs: string } {
  const index = findTopLevelEquals(source)
  if (index < 0) return { name: null, rhs: source }
  const head = source.slice(0, index).trim()
  if (!head || head.includes('+') || head.includes('*') || findTopLevelIf(head) >= 0) {
    return { name: null, rhs: source }
  }
  return { name: head, rhs: source.slice(index + 1).trim() }
}

function splitFormulaTerms(source: string): string[] {
  const terms: string[] = []
  let start = 0
  let bracketDepth = 0
  let parenDepth = 0
  for (let index = 0; index < source.length; index += 1) {
    const char = source[index]
    const previous = source[index - 1]
    if (char === '[' && parenDepth >= 0) bracketDepth += 1
    else if (char === ']' && bracketDepth > 0) bracketDepth -= 1
    else if (char === '(' && bracketDepth === 0) parenDepth += 1
    else if (char === ')' && bracketDepth === 0 && parenDepth > 0) parenDepth -= 1
    else if (
      bracketDepth === 0
      && parenDepth === 0
      && (char === '+' || char === '-')
      && index > start
      && previous !== 'e'
      && previous !== 'E'
    ) {
      const term = source.slice(start, index).trim()
      if (term) terms.push(term)
      start = index
    }
  }
  const tail = source.slice(start).trim()
  if (tail) terms.push(tail)
  return terms
}

function parseFormulaTerm(rawTerm: string): ParsedFormulaTerm {
  const term = rawTerm.trim()
  const ifIndex = findTopLevelIf(term)
  if (ifIndex >= 0) return parseCategoricalFormulaTerm(term, ifIndex)

  const starIndex = findTopLevelChar(term, '*')
  if (starIndex < 0) {
    const intercept = parseFormulaNumber(term)
    if (intercept != null) return { kind: 'intercept', value: intercept }
    const key = parseFormulaToken(term)
    if (!key) return { kind: 'invalid', error: `Invalid metric term: ${term}.` }
    return { kind: 'numeric', key, weight: 1, zNormalize: false }
  }

  const weight = parseFormulaNumber(term.slice(0, starIndex))
  if (weight == null) return { kind: 'invalid', error: `Invalid weight in term: ${term}.` }
  const value = parseNumericFormulaValue(term.slice(starIndex + 1))
  if (!value) return { kind: 'invalid', error: `Invalid metric in term: ${term}.` }
  return { kind: 'numeric', key: value.key, weight, zNormalize: value.zNormalize }
}

function parseCategoricalFormulaTerm(term: string, ifIndex: number): ParsedFormulaTerm {
  const rawWeight = term.slice(0, ifIndex).trim()
  const weight = rawWeight ? parseFormulaNumber(rawWeight) : 1
  if (weight == null) return { kind: 'invalid', error: `Invalid categorical weight in term: ${term}.` }

  const condition = term.slice(ifIndex).trim().replace(/^if\s+/i, '')
  const equalsIndex = findTopLevelEquals(condition)
  if (equalsIndex < 0) return { kind: 'invalid', error: `Invalid categorical condition: ${term}.` }
  const key = parseFormulaToken(condition.slice(0, equalsIndex))
  const valueStart = condition[equalsIndex + 1] === '=' ? equalsIndex + 2 : equalsIndex + 1
  const value = parseFormulaToken(condition.slice(valueStart))
  if (!key || !value) return { kind: 'invalid', error: `Invalid categorical condition: ${term}.` }
  return { kind: 'categorical', key, value, weight }
}

function parseNumericFormulaValue(rawValue: string): { key: string; zNormalize: boolean } | null {
  const value = rawValue.trim()
  const lower = value.toLowerCase()
  if (lower.startsWith('znorm(') && value.endsWith(')')) {
    const key = parseFormulaToken(value.slice(6, -1))
    return key ? { key, zNormalize: true } : null
  }
  const key = parseFormulaToken(value)
  return key ? { key, zNormalize: false } : null
}

function findTopLevelIf(source: string): number {
  let bracketDepth = 0
  let parenDepth = 0
  const lower = source.toLowerCase()
  for (let index = 0; index < source.length; index += 1) {
    const char = source[index]
    if (char === '[') bracketDepth += 1
    else if (char === ']' && bracketDepth > 0) bracketDepth -= 1
    else if (char === '(' && bracketDepth === 0) parenDepth += 1
    else if (char === ')' && bracketDepth === 0 && parenDepth > 0) parenDepth -= 1
    if (bracketDepth !== 0 || parenDepth !== 0) continue
    if (
      lower.slice(index, index + 2) === 'if'
      && (index === 0 || /\s/.test(source[index - 1]))
      && (index + 2 >= source.length || /\s/.test(source[index + 2]))
    ) {
      return index
    }
  }
  return -1
}

function findTopLevelEquals(source: string): number {
  return findTopLevelChar(source, '=')
}

function findTopLevelChar(source: string, target: string): number {
  let bracketDepth = 0
  let parenDepth = 0
  for (let index = 0; index < source.length; index += 1) {
    const char = source[index]
    if (char === '[') bracketDepth += 1
    else if (char === ']' && bracketDepth > 0) bracketDepth -= 1
    else if (char === '(' && bracketDepth === 0) parenDepth += 1
    else if (char === ')' && bracketDepth === 0 && parenDepth > 0) parenDepth -= 1
    else if (char === target && bracketDepth === 0 && parenDepth === 0) return index
  }
  return -1
}

function parseFormulaToken(rawValue: string): string | null {
  const value = rawValue.trim()
  if (!value) return null
  if (!value.startsWith('[')) return value
  if (!value.endsWith(']')) return null
  let out = ''
  for (let index = 1; index < value.length - 1; index += 1) {
    const char = value[index]
    if (char === '\\' && index + 1 < value.length - 1) {
      out += value[index + 1]
      index += 1
    } else {
      out += char
    }
  }
  const token = out.trim()
  return token || null
}

function parseFormulaNumber(value: string): number | null {
  return parseFiniteDraftNumber(value.trim().replace(/^([+-])\s+/, '$1'))
}

function formatFormulaToken(value: string): string {
  const token = value.trim()
  if (SIMPLE_FORMULA_TOKEN_RE.test(token)) return token
  return `[${token.replace(/\\/g, '\\\\').replace(/]/g, '\\]')}]`
}

function existingMissingPolicy(
  draft: DerivedMetricDraft,
  key: string,
): DerivedMetricNumericMissingPolicy {
  return draft.numericTerms.find((term) => term.key.trim() === key)?.missing ?? 'invalid'
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
