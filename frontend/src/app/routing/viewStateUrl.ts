import { normalizeFilterAst } from '../../features/browse/model/filters'
import {
  normalizeDerivedMetricSpec,
  normalizeViewState,
} from '../../features/metrics/model/derivedMetric'
import { safeJsonParse } from '../../lib/util'
import type {
  DerivedMetricViewSpec,
  FilterAST,
  SortSpec,
  ViewState,
} from '../../lib/types'

const SORT_PARAM = 'sort'
const FILTERS_PARAM = 'filters'
const DERIVED_METRIC_PARAM = 'derived_metric'
const QUERY_PARAM = 'q'
const RANDOM_SEED_PARAM = 'random_seed'
const UNSUPPORTED_METRIC_INTENT_PARAM = 'unsupported_metric_intent'

const DEFAULT_VIEW_STATE: ViewState = {
  filters: { and: [] },
  sort: { kind: 'builtin', key: 'added', dir: 'desc' },
}

export type SharedViewStateSnapshot = {
  viewState: ViewState
  query: string
  randomSeed: number | null
  unsupportedMetricIntent: string | null
  hasSharedAnalysisState: boolean
  hasSharedViewState: boolean
}

export type SharedViewStateUrlOptions = {
  query?: string | null
  randomSeed?: number | string | null
  unsupportedMetricIntent?: string | null
}

export function readSharedViewStateFromCurrentUrl(
  fallback: ViewState = DEFAULT_VIEW_STATE,
): SharedViewStateSnapshot {
  if (typeof window === 'undefined') {
    return emptySharedViewStateSnapshot(fallback)
  }
  return readSharedViewStateFromSearch(window.location.search, fallback)
}

export function readSharedViewStateFromSearch(
  search: string,
  fallback: ViewState = DEFAULT_VIEW_STATE,
): SharedViewStateSnapshot {
  const params = parseSearchParams(search)
  const hasSharedViewState = params.has(SORT_PARAM)
    || params.has(FILTERS_PARAM)
    || params.has(DERIVED_METRIC_PARAM)
  const hasSharedAnalysisState = hasSharedViewState
    || params.has(QUERY_PARAM)
    || params.has(RANDOM_SEED_PARAM)
    || params.has(UNSUPPORTED_METRIC_INTENT_PARAM)

  if (!hasSharedAnalysisState) {
    return emptySharedViewStateSnapshot(fallback)
  }

  const raw: Partial<ViewState> = {}
  if (params.has(SORT_PARAM)) {
    const sort = parseSortParam(params.get(SORT_PARAM))
    if (sort) raw.sort = sort
  }
  if (params.has(FILTERS_PARAM)) {
    const filters = parseFiltersParam(params.get(FILTERS_PARAM))
    if (filters) raw.filters = filters
  }
  if (params.has(DERIVED_METRIC_PARAM)) {
    const derivedMetric = parseDerivedMetricParam(params.get(DERIVED_METRIC_PARAM))
    if (derivedMetric) raw.derivedMetric = derivedMetric
  }

  return {
    viewState: normalizeViewState(raw, DEFAULT_VIEW_STATE),
    query: normalizeQueryParam(params.get(QUERY_PARAM)),
    randomSeed: parseRandomSeedParam(params.get(RANDOM_SEED_PARAM)),
    unsupportedMetricIntent: normalizeNullableParam(params.get(UNSUPPORTED_METRIC_INTENT_PARAM)),
    hasSharedAnalysisState: true,
    hasSharedViewState: true,
  }
}

export function replaceSharedViewStateInCurrentUrl(
  viewState: ViewState,
  options: SharedViewStateUrlOptions = {},
): void {
  if (typeof window === 'undefined') return
  const nextSearch = buildSharedViewStateSearch(window.location.search, viewState, options)
  if (window.location.search === nextSearch) return
  const nextUrl = `${window.location.pathname}${nextSearch}${window.location.hash}`
  window.history.replaceState(window.history.state, '', nextUrl)
}

export function buildSharedViewStateSearch(
  search: string,
  viewState: ViewState,
  options: SharedViewStateUrlOptions = {},
): string {
  const params = parseSearchParams(search)
  const normalized = normalizeViewState(viewState)
  const query = normalizeQueryParam(options.query ?? null)
  if (query) {
    params.set(QUERY_PARAM, query)
  } else {
    params.delete(QUERY_PARAM)
  }

  if (isDefaultSort(normalized.sort)) {
    params.delete(SORT_PARAM)
  } else {
    params.set(SORT_PARAM, serializeSortParam(normalized.sort))
  }

  const filters = normalizeFilterAst(normalized.filters) ?? { and: [] }
  if (filters.and.length) {
    params.set(FILTERS_PARAM, JSON.stringify(filters))
  } else {
    params.delete(FILTERS_PARAM)
  }

  const derivedMetric = normalizeDerivedMetricSpec(normalized.derivedMetric ?? null)
  if (derivedMetric && viewStateUsesDerivedMetric(normalized.sort, filters, derivedMetric.id)) {
    params.set(DERIVED_METRIC_PARAM, JSON.stringify(derivedMetric))
  } else {
    params.delete(DERIVED_METRIC_PARAM)
  }

  const randomSeed = activeRandomSeedParam(normalized.sort, options.randomSeed)
  if (randomSeed) {
    params.set(RANDOM_SEED_PARAM, randomSeed)
  } else {
    params.delete(RANDOM_SEED_PARAM)
  }

  const unsupportedMetricIntent = normalizeNullableParam(options.unsupportedMetricIntent ?? null)
  if (unsupportedMetricIntent) {
    params.set(UNSUPPORTED_METRIC_INTENT_PARAM, unsupportedMetricIntent)
  } else {
    params.delete(UNSUPPORTED_METRIC_INTENT_PARAM)
  }

  const next = params.toString()
  return next ? `?${next}` : ''
}

function parseSearchParams(search: string): URLSearchParams {
  const raw = search.startsWith('?') ? search.slice(1) : search
  return new URLSearchParams(raw)
}

function emptySharedViewStateSnapshot(fallback: ViewState): SharedViewStateSnapshot {
  return {
    viewState: normalizeViewState(fallback),
    query: '',
    randomSeed: null,
    unsupportedMetricIntent: null,
    hasSharedAnalysisState: false,
    hasSharedViewState: false,
  }
}

function normalizeNullableParam(raw: string | null): string | null {
  const value = raw?.trim().replace(/\s+/g, ' ') ?? ''
  return value || null
}

function normalizeQueryParam(raw: string | null): string {
  return normalizeNullableParam(raw) ?? ''
}

function parseRandomSeedParam(raw: string | null): number | null {
  const value = normalizeNullableParam(raw)
  if (value === null) return null
  const parsed = Number(value)
  return Number.isFinite(parsed) ? parsed : null
}

function activeRandomSeedParam(
  sort: SortSpec,
  randomSeed: number | string | null | undefined,
): string | null {
  if (sort.kind !== 'builtin' || sort.key !== 'random') return null
  if (randomSeed === null || randomSeed === undefined || randomSeed === '') return null
  const value = String(randomSeed).trim()
  return value || null
}

function serializeSortParam(sort: SortSpec): string {
  if (sort.kind === 'metric') {
    return `metric:${sort.dir}:${sort.key}`
  }
  return `builtin:${sort.key}:${sort.dir}`
}

function parseSortParam(raw: string | null): SortSpec | null {
  if (!raw) return null
  const parts = raw.split(':')
  if (parts[0] === 'metric' && isSortDir(parts[1]) && parts.length >= 3) {
    const key = parts.slice(2).join(':').trim()
    if (!key) return null
    return { kind: 'metric', dir: parts[1], key }
  }
  if (parts[0] === 'builtin' && parts.length === 3 && isBuiltinSortKey(parts[1]) && isSortDir(parts[2])) {
    return { kind: 'builtin', key: parts[1], dir: parts[2] }
  }
  return null
}

function parseFiltersParam(raw: string | null): FilterAST | undefined {
  const parsed = safeJsonParse<unknown>(raw)
  return normalizeFilterAst(parsed) ?? undefined
}

function parseDerivedMetricParam(raw: string | null): DerivedMetricViewSpec | undefined {
  const parsed = safeJsonParse<unknown>(raw)
  const normalized = normalizeDerivedMetricSpec(parsed)
  return normalized ?? undefined
}

function isDefaultSort(sort: SortSpec): boolean {
  return sort.kind === 'builtin' && sort.key === 'added' && sort.dir === 'desc'
}

function isBuiltinSortKey(value: string | undefined): value is Extract<SortSpec, { kind: 'builtin' }>['key'] {
  return value === 'added' || value === 'name' || value === 'random'
}

function isSortDir(value: string | undefined): value is SortSpec['dir'] {
  return value === 'asc' || value === 'desc'
}

function viewStateUsesDerivedMetric(sort: SortSpec, filters: FilterAST, derivedId: string): boolean {
  const key = `@derived/${derivedId}`
  if (sort.kind === 'metric' && sort.key === key) return true
  for (const clause of filters.and) {
    if ('metricRange' in clause && clause.metricRange.key === key) return true
  }
  return false
}

export function hasSharedViewStateSearchParams(search: string): boolean {
  const params = parseSearchParams(search)
  return params.has(SORT_PARAM)
    || params.has(FILTERS_PARAM)
    || params.has(DERIVED_METRIC_PARAM)
    || params.has(QUERY_PARAM)
    || params.has(RANDOM_SEED_PARAM)
    || params.has(UNSUPPORTED_METRIC_INTENT_PARAM)
}
