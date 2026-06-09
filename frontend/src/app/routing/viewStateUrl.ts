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

const DEFAULT_VIEW_STATE: ViewState = {
  filters: { and: [] },
  sort: { kind: 'builtin', key: 'added', dir: 'desc' },
}

export type SharedViewStateSnapshot = {
  viewState: ViewState
  hasSharedViewState: boolean
}

export function readSharedViewStateFromCurrentUrl(
  fallback: ViewState = DEFAULT_VIEW_STATE,
): SharedViewStateSnapshot {
  if (typeof window === 'undefined') {
    return { viewState: normalizeViewState(fallback), hasSharedViewState: false }
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

  if (!hasSharedViewState) {
    return { viewState: normalizeViewState(fallback), hasSharedViewState: false }
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
    viewState: normalizeViewState(raw, fallback),
    hasSharedViewState: true,
  }
}

export function replaceSharedViewStateInCurrentUrl(viewState: ViewState): void {
  if (typeof window === 'undefined') return
  const nextSearch = buildSharedViewStateSearch(window.location.search, viewState)
  if (window.location.search === nextSearch) return
  const nextUrl = `${window.location.pathname}${nextSearch}${window.location.hash}`
  window.history.replaceState(window.history.state, '', nextUrl)
}

export function buildSharedViewStateSearch(search: string, viewState: ViewState): string {
  const params = parseSearchParams(search)
  const normalized = normalizeViewState(viewState)

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

  const next = params.toString()
  return next ? `?${next}` : ''
}

function parseSearchParams(search: string): URLSearchParams {
  const raw = search.startsWith('?') ? search.slice(1) : search
  return new URLSearchParams(raw)
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
  return params.has(SORT_PARAM) || params.has(FILTERS_PARAM) || params.has(DERIVED_METRIC_PARAM)
}
