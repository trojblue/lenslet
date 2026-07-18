import { normalizeFilterAst } from '../../browse/model/filters'
import { finiteMetricValue } from '../../../lib/metrics'
import type {
  BrowseItemPayload,
  DerivedMetricStatusPayload,
  DerivedMetricCategoricalTerm,
  DerivedMetricNumericMissingPolicy,
  DerivedMetricNumericTerm,
  DerivedMetricSpec,
  DerivedMetricViewSpec,
  FilterAST,
  MetricDisplayNames,
  SortSpec,
  ViewState,
} from '../../../lib/types'

export const DERIVED_METRIC_PREFIX = '@derived/'

const DEFAULT_DERIVED_METRIC_NAME = 'Derived score'
const DERIVED_ID_RE = /^[A-Za-z0-9][A-Za-z0-9_-]{0,79}$/
const MISSING_POLICIES = new Set<DerivedMetricNumericMissingPolicy>(['zero', 'invalid'])
const DEFAULT_VIEW_STATE: ViewState = {
  filters: { and: [] },
  sort: { kind: 'builtin', key: 'added', dir: 'desc' },
}

export type DerivedMetricStatus = 'none' | 'valid' | 'unavailable' | 'invalid'

export type DerivedMetricEvaluation = {
  items: BrowseItemPayload[]
  metricKeys: string[]
  categoricalKeys: string[]
  metricDisplayNames: MetricDisplayNames
  spec: DerivedMetricSpec | null
  definitionIdentity: string | null
  key: string | null
  name: string | null
  status: DerivedMetricStatus
  validCount: number
  invalidCount: number
  invalidReasons: string[]
  missingMetricKeys: string[]
  missingCategoricalKeys: string[]
  loadedCount: number
  totalItems: number | null
  partialLoadWarning: boolean
  scoreScope?: 'none' | 'query_filtered' | 'loaded_window'
  scorePopulationCount?: number | null
  zStats?: DerivedMetricStatusPayload['z_stats']
}

export type EvaluateDerivedMetricParams = {
  items: BrowseItemPayload[]
  metricKeys: readonly string[] | undefined
  categoricalKeys: readonly string[] | undefined
  spec?: unknown
  loadedCount?: number
  totalItems?: number | null
}

export type EvaluateBackendDerivedMetricParams = {
  items: BrowseItemPayload[]
  metricKeys: readonly string[] | undefined
  categoricalKeys: readonly string[] | undefined
  spec?: unknown
  backendStatus?: DerivedMetricStatusPayload | null
  loadedCount?: number
  totalItems?: number | null
}

export type DerivedMetricInputKeys = {
  metricKeys: string[]
  categoricalKeys: string[]
}

type ZStatsByKey = Map<string, { mean: number; std: number }>

export function isDerivedMetricKey(key: string | null | undefined): boolean {
  return typeof key === 'string'
    && key.startsWith(DERIVED_METRIC_PREFIX)
    && key.length > DERIVED_METRIC_PREFIX.length
}

export function derivedMetricKey(spec: Pick<DerivedMetricSpec, 'id'> | string): string {
  const id = typeof spec === 'string' ? spec : spec.id
  return `${DERIVED_METRIC_PREFIX}${id}`
}

export function normalizeDerivedMetricSpec(raw: unknown): DerivedMetricSpec | null {
  if (!raw || typeof raw !== 'object') return null
  const value = raw as {
    version?: unknown
    id?: unknown
    name?: unknown
    intercept?: unknown
    numericTerms?: unknown
    categoricalTerms?: unknown
  }
  if (value.version !== 1) return null

  const id = normalizeDerivedId(value.id)
  const intercept = toFiniteNumber(value.intercept)
  if (!id || intercept == null) return null

  const numericTerms = normalizeNumericTerms(value.numericTerms)
  const categoricalTerms = normalizeCategoricalTerms(value.categoricalTerms)
  if (!numericTerms || !categoricalTerms) return null

  return {
    version: 1,
    id,
    name: normalizeDisplayName(value.name),
    intercept,
    numericTerms,
    categoricalTerms,
  }
}

export function getDerivedMetricInputKeys(raw: unknown): DerivedMetricInputKeys {
  const spec = normalizeDerivedMetricSpec(raw)
  if (!spec) return { metricKeys: [], categoricalKeys: [] }
  return {
    metricKeys: uniqueSortedStrings(spec.numericTerms.map((term) => term.key)),
    categoricalKeys: uniqueSortedStrings(spec.categoricalTerms.map((term) => term.key)),
  }
}

export function normalizeViewState(raw: unknown, fallback: ViewState = DEFAULT_VIEW_STATE): ViewState {
  if (!raw || typeof raw !== 'object') return { ...fallback }
  const value = raw as {
    filters?: unknown
    sort?: unknown
    selectedMetric?: unknown
    derivedMetric?: unknown
  }
  const filters = normalizeFilterAst(value.filters) ?? fallback.filters
  const sort = normalizeSortSpec(value.sort) ?? fallback.sort
  const selectedMetric = normalizeMetricKey(value.selectedMetric) ?? fallback.selectedMetric
  const derivedMetric = normalizeDerivedMetricViewSpec(value.derivedMetric)

  return {
    filters,
    sort,
    ...(selectedMetric ? { selectedMetric } : {}),
    ...(derivedMetric ? { derivedMetric } : {}),
  }
}

function normalizeDerivedMetricViewSpec(raw: unknown): DerivedMetricViewSpec | null {
  if (!raw || typeof raw !== 'object' || Array.isArray(raw)) return null
  const normalized = normalizeDerivedMetricSpec(raw)
  if (normalized) return normalized
  return { ...(raw as Record<string, unknown>) }
}

export function evaluateDerivedMetric({
  items,
  metricKeys,
  categoricalKeys,
  spec = null,
  loadedCount = items.length,
  totalItems = null,
}: EvaluateDerivedMetricParams): DerivedMetricEvaluation {
  const sourceMetricKeys = filterSourceMetricKeys(metricKeys)
  const sourceCategoricalKeys = uniqueSortedStrings(categoricalKeys)
  const normalizedSpec = normalizeDerivedMetricSpec(spec)
  const definitionIdentity = derivedMetricDefinitionIdentity(spec)
  const normalizedTotalItems = normalizeTotalItems(totalItems)
  const partialLoadWarning = normalizedTotalItems != null && loadedCount < normalizedTotalItems

  if (!normalizedSpec) {
    const invalidMetadata = spec == null ? null : extractInvalidDerivedMetricMetadata(spec)
    const invalidKey = invalidMetadata?.key ?? null
    const invalidName = invalidMetadata?.name ?? null
    return {
      items: stripReservedDerivedMetrics(items),
      metricKeys: sourceMetricKeys,
      categoricalKeys: sourceCategoricalKeys,
      metricDisplayNames: invalidKey && invalidName ? { [invalidKey]: invalidName } : {},
      spec: null,
      definitionIdentity,
      key: invalidKey,
      name: invalidName,
      status: spec == null ? 'none' : 'invalid',
      validCount: 0,
      invalidCount: spec == null ? 0 : items.length,
      invalidReasons: spec == null ? [] : ['Invalid derived metric definition.'],
      missingMetricKeys: [],
      missingCategoricalKeys: [],
      loadedCount,
      totalItems: normalizedTotalItems,
      partialLoadWarning: spec == null ? false : partialLoadWarning,
      scoreScope: 'loaded_window',
      scorePopulationCount: normalizedTotalItems,
      zStats: {},
    }
  }

  const key = derivedMetricKey(normalizedSpec)
  const displayName = normalizedSpec.name
  const missingMetricKeys = findMissingKeys(
    normalizedSpec.numericTerms.map((term) => term.key),
    sourceMetricKeys,
  )
  const missingCategoricalKeys = findMissingKeys(
    normalizedSpec.categoricalTerms.map((term) => term.key),
    sourceCategoricalKeys,
  )
  const metricDisplayNames = { [key]: displayName }

  if (missingMetricKeys.length || missingCategoricalKeys.length) {
    return {
      items: stripReservedDerivedMetrics(items),
      metricKeys: sourceMetricKeys,
      categoricalKeys: sourceCategoricalKeys,
      metricDisplayNames,
      spec: normalizedSpec,
      definitionIdentity,
      key,
      name: displayName,
      status: 'unavailable',
      validCount: 0,
      invalidCount: items.length,
      invalidReasons: [],
      missingMetricKeys,
      missingCategoricalKeys,
      loadedCount,
      totalItems: normalizedTotalItems,
      partialLoadWarning,
      scoreScope: 'loaded_window',
      scorePopulationCount: normalizedTotalItems,
      zStats: {},
    }
  }

  let changed = false
  let validCount = 0
  let invalidCount = 0
  const zStats = buildZStats(items, normalizedSpec.numericTerms)
  const augmentedItems = items.map((item) => {
    const score = evaluateItemScore(item, normalizedSpec, zStats)
    if (score == null) {
      invalidCount += 1
      const stripped = withoutReservedDerivedMetricKeys(item.metrics)
      if (!stripped.changed) return item
      changed = true
      return { ...item, metrics: stripped.metrics }
    }
    validCount += 1
    const stripped = withoutReservedDerivedMetricKeys(item.metrics)
    changed = true
    return {
      ...item,
      metrics: {
        ...(stripped.metrics ?? {}),
        [key]: score,
      },
    }
  })

  return {
    items: changed ? augmentedItems : items,
    metricKeys: appendMetricKey(sourceMetricKeys, key),
    categoricalKeys: sourceCategoricalKeys,
    metricDisplayNames,
    spec: normalizedSpec,
    definitionIdentity,
    key,
    name: displayName,
    status: 'valid',
    validCount,
    invalidCount,
    invalidReasons: [],
    missingMetricKeys: [],
    missingCategoricalKeys: [],
    loadedCount,
    totalItems: normalizedTotalItems,
    partialLoadWarning,
    scoreScope: 'loaded_window',
    scorePopulationCount: normalizedTotalItems,
    zStats: {},
  }
}

export function evaluateBackendDerivedMetric({
  items,
  metricKeys,
  categoricalKeys,
  spec = null,
  backendStatus = null,
  loadedCount = items.length,
  totalItems = null,
}: EvaluateBackendDerivedMetricParams): DerivedMetricEvaluation {
  const status = backendStatus?.status ?? 'none'
  const normalizedSpec = normalizeDerivedMetricSpec(spec)
  const definitionIdentity = derivedMetricDefinitionIdentity(spec)
  if (status === 'none') {
    if (spec != null && !normalizedSpec) {
      return evaluateDerivedMetric({
        items,
        metricKeys,
        categoricalKeys,
        spec,
        loadedCount,
        totalItems,
      })
    }
    const key = normalizedSpec ? derivedMetricKey(normalizedSpec) : null
    return {
      items,
      metricKeys: filterSourceMetricKeys(metricKeys),
      categoricalKeys: uniqueSortedStrings(categoricalKeys),
      metricDisplayNames: key ? { [key]: normalizedSpec!.name } : {},
      spec: normalizedSpec,
      definitionIdentity,
      key,
      name: normalizedSpec?.name ?? null,
      status: 'none',
      validCount: 0,
      invalidCount: 0,
      invalidReasons: [],
      missingMetricKeys: [],
      missingCategoricalKeys: [],
      loadedCount,
      totalItems: normalizeTotalItems(totalItems),
      partialLoadWarning: false,
      scoreScope: 'none',
      scorePopulationCount: null,
      zStats: {},
    }
  }

  const sourceMetricKeys = filterSourceMetricKeys(metricKeys)
  const sourceCategoricalKeys = uniqueSortedStrings(categoricalKeys)
  const normalizedTotalItems = normalizeTotalItems(totalItems)
  const key = normalizeMetricKey(backendStatus?.key) ?? (
    normalizedSpec ? derivedMetricKey(normalizedSpec) : null
  )
  const displayName = normalizeDisplayName(backendStatus?.display_name ?? normalizedSpec?.name)
  const metricDisplayNames = key ? { [key]: displayName } : {}
  const validCount = normalizeCount(backendStatus?.valid_count)
  const invalidCount = normalizeCount(backendStatus?.invalid_count)
  const scorePopulationCount = normalizeCount(backendStatus?.score_population_count)
  const scoreScope = backendStatus?.score_scope ?? 'none'
  const zStats = backendStatus?.z_stats ?? {}
  return {
    items,
    metricKeys: key && status === 'applied'
      ? appendMetricKey(sourceMetricKeys, key)
      : sourceMetricKeys,
    categoricalKeys: sourceCategoricalKeys,
    metricDisplayNames,
    spec: normalizedSpec,
    definitionIdentity,
    key,
    name: key ? displayName : null,
    status: status === 'applied' ? 'valid' : status,
    validCount,
    invalidCount,
    invalidReasons: status === 'invalid' ? ['Invalid derived metric definition.'] : [],
    missingMetricKeys: uniqueSortedStrings(backendStatus?.missing_numeric_inputs),
    missingCategoricalKeys: uniqueSortedStrings(backendStatus?.unavailable_categorical_inputs),
    loadedCount,
    totalItems: normalizedTotalItems,
    partialLoadWarning: false,
    scoreScope,
    scorePopulationCount,
    zStats,
  }
}

function derivedMetricDefinitionIdentity(raw: unknown): string | null {
  if (raw == null) return null
  const normalized = normalizeDerivedMetricSpec(raw)
  return JSON.stringify(normalized ?? canonicalizeDefinitionValue(raw))
}

function canonicalizeDefinitionValue(value: unknown): unknown {
  if (typeof value === 'number' && !Number.isFinite(value)) {
    return { __nonfinite_number__: String(value) }
  }
  if (Array.isArray(value)) return value.map(canonicalizeDefinitionValue)
  if (value && typeof value === 'object') {
    const record = value as Record<string, unknown>
    return Object.fromEntries(
      Object.keys(record).sort().map((key) => [key, canonicalizeDefinitionValue(record[key])]),
    )
  }
  if (value === undefined) return { __undefined__: true }
  if (typeof value === 'bigint') return { __bigint__: value.toString() }
  if (typeof value === 'function' || typeof value === 'symbol') return String(value)
  return value
}

function normalizeDerivedId(value: unknown): string | null {
  if (typeof value !== 'string') return null
  const id = value.trim()
  return DERIVED_ID_RE.test(id) ? id : null
}

function normalizeDisplayName(value: unknown): string {
  if (typeof value !== 'string') return DEFAULT_DERIVED_METRIC_NAME
  const name = value.trim()
  return name || DEFAULT_DERIVED_METRIC_NAME
}

function extractInvalidDerivedMetricMetadata(raw: unknown): { key: string | null; name: string } | null {
  if (!raw || typeof raw !== 'object') return null
  const value = raw as { id?: unknown; name?: unknown }
  const id = normalizeDerivedId(value.id)
  return {
    key: id ? derivedMetricKey(id) : null,
    name: normalizeDisplayName(value.name),
  }
}

function normalizeMetricKey(value: unknown): string | null {
  if (typeof value !== 'string') return null
  const key = value.trim()
  return key || null
}

function normalizeSortSpec(value: unknown): SortSpec | null {
  if (!value || typeof value !== 'object') return null
  const spec = value as Partial<SortSpec>
  if (spec.kind === 'builtin') {
    if (
      (spec.key === 'name' || spec.key === 'added' || spec.key === 'random')
      && isSortDir(spec.dir)
    ) {
      return { kind: 'builtin', key: spec.key, dir: spec.dir }
    }
  }
  if (spec.kind === 'metric') {
    const key = normalizeMetricKey(spec.key)
    if (key && isSortDir(spec.dir)) {
      return { kind: 'metric', key, dir: spec.dir }
    }
  }
  return null
}

function isSortDir(value: unknown): value is SortSpec['dir'] {
  return value === 'asc' || value === 'desc'
}

function normalizeNumericTerms(value: unknown): DerivedMetricNumericTerm[] | null {
  if (value === undefined) return []
  if (!Array.isArray(value)) return null
  const terms: DerivedMetricNumericTerm[] = []
  for (const rawTerm of value) {
    if (!rawTerm || typeof rawTerm !== 'object') return null
    const term = rawTerm as { key?: unknown; weight?: unknown; missing?: unknown; zNormalize?: unknown }
    const key = normalizeMetricKey(term.key)
    const weight = toFiniteNumber(term.weight)
    if (!key || isDerivedMetricKey(key) || weight == null || !isMissingPolicy(term.missing)) {
      return null
    }
    terms.push({ key, weight, missing: term.missing, zNormalize: term.zNormalize === true })
  }
  return terms
}

function normalizeCategoricalTerms(value: unknown): DerivedMetricCategoricalTerm[] | null {
  if (value === undefined) return []
  if (!Array.isArray(value)) return null
  const terms: DerivedMetricCategoricalTerm[] = []
  for (const rawTerm of value) {
    if (!rawTerm || typeof rawTerm !== 'object') return null
    const term = rawTerm as { key?: unknown; value?: unknown; weight?: unknown }
    const key = normalizeMetricKey(term.key)
    const categoricalValue = typeof term.value === 'string' ? term.value.trim() : ''
    const weight = toFiniteNumber(term.weight)
    if (!key || isDerivedMetricKey(key) || !categoricalValue || weight == null) {
      return null
    }
    terms.push({ key, value: categoricalValue, weight })
  }
  return terms
}

function isMissingPolicy(value: unknown): value is DerivedMetricNumericMissingPolicy {
  return typeof value === 'string' && MISSING_POLICIES.has(value as DerivedMetricNumericMissingPolicy)
}

function toFiniteNumber(value: unknown): number | null {
  return typeof value === 'number' && Number.isFinite(value) ? value : null
}

function normalizeTotalItems(value: number | null | undefined): number | null {
  if (typeof value !== 'number' || !Number.isFinite(value) || value < 0) return null
  return value
}

function normalizeCount(value: number | null | undefined): number {
  if (typeof value !== 'number' || !Number.isFinite(value) || value < 0) return 0
  return Math.trunc(value)
}

function uniqueSortedStrings(values: readonly string[] | undefined): string[] {
  if (!values?.length) return []
  const keys = new Set<string>()
  for (const value of values) {
    if (typeof value !== 'string') continue
    const key = value.trim()
    if (key) keys.add(key)
  }
  return Array.from(keys).sort()
}

function filterSourceMetricKeys(values: readonly string[] | undefined): string[] {
  return uniqueSortedStrings(values).filter((key) => !isDerivedMetricKey(key))
}

function findMissingKeys(keys: readonly string[], availableKeys: readonly string[]): string[] {
  const available = new Set(availableKeys)
  const missing = new Set<string>()
  for (const key of keys) {
    if (!available.has(key)) missing.add(key)
  }
  return Array.from(missing).sort()
}

function appendMetricKey(metricKeys: readonly string[], key: string): string[] {
  if (metricKeys.includes(key)) return [...metricKeys]
  return [...metricKeys, key]
}

function buildZStats(items: readonly BrowseItemPayload[], terms: readonly DerivedMetricNumericTerm[]): ZStatsByKey {
  const zKeys = new Set(terms.filter((term) => term.zNormalize).map((term) => term.key))
  if (!zKeys.size) return new Map()
  const sums = new Map<string, number>()
  const sumsSq = new Map<string, number>()
  const counts = new Map<string, number>()
  for (const key of zKeys) {
    sums.set(key, 0)
    sumsSq.set(key, 0)
    counts.set(key, 0)
  }
  for (const item of items) {
    const metrics = item.metrics
    if (!metrics) continue
    for (const key of zKeys) {
      const value = finiteMetricValue(metrics[key])
      if (value == null) continue
      sums.set(key, (sums.get(key) ?? 0) + value)
      sumsSq.set(key, (sumsSq.get(key) ?? 0) + value * value)
      counts.set(key, (counts.get(key) ?? 0) + 1)
    }
  }

  const stats: ZStatsByKey = new Map()
  for (const key of zKeys) {
    const count = counts.get(key) ?? 0
    if (count <= 0) continue
    const mean = (sums.get(key) ?? 0) / count
    const variance = Math.max(0, ((sumsSq.get(key) ?? 0) / count) - (mean * mean))
    stats.set(key, { mean, std: Math.sqrt(variance) })
  }
  return stats
}

function evaluateItemScore(item: BrowseItemPayload, spec: DerivedMetricSpec, zStats: ZStatsByKey): number | null {
  let score = spec.intercept
  for (const term of spec.numericTerms) {
    let value = finiteMetricValue(item.metrics?.[term.key])
    if (value == null) {
      if (term.missing === 'invalid') return null
      continue
    }
    if (term.zNormalize) {
      const stats = zStats.get(term.key)
      value = !stats || stats.std <= 0 ? 0 : (value - stats.mean) / stats.std
    }
    score += value * term.weight
  }
  for (const term of spec.categoricalTerms) {
    if (item.categoricals?.[term.key] === term.value) {
      score += term.weight
    }
  }
  return finiteMetricValue(score)
}

function stripReservedDerivedMetrics(items: BrowseItemPayload[]): BrowseItemPayload[] {
  let changed = false
  const nextItems = items.map((item) => {
    const stripped = withoutReservedDerivedMetricKeys(item.metrics)
    if (!stripped.changed) return item
    changed = true
    return { ...item, metrics: stripped.metrics }
  })
  return changed ? nextItems : items
}

function withoutReservedDerivedMetricKeys(
  metrics: BrowseItemPayload['metrics'],
): { metrics: BrowseItemPayload['metrics']; changed: boolean } {
  if (!metrics) return { metrics, changed: false }
  let changed = false
  const nextMetrics: Record<string, number | null> = {}
  for (const [key, value] of Object.entries(metrics)) {
    if (isDerivedMetricKey(key)) {
      changed = true
      continue
    }
    nextMetrics[key] = value
  }
  if (!changed) return { metrics, changed: false }
  const keys = Object.keys(nextMetrics)
  return {
    metrics: keys.length ? nextMetrics : undefined,
    changed: true,
  }
}
