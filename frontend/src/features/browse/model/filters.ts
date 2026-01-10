import type { FilterAST, FilterClause, Item } from '../../../lib/types'

type CompareOp = '<' | '<=' | '>' | '>='

const STAR_VALUES = new Set([0, 1, 2, 3, 4, 5])
const COMPARE_OPS = new Set<CompareOp>(['<', '<=', '>', '>='])
const DATE_ONLY_RE = /^\d{4}-\d{2}-\d{2}$/

export function applyFilterAst(items: Item[], filters: FilterAST | null): Item[] {
  if (!filters || !filters.and.length) return items
  return items.filter((it) => matchesAll(it, filters.and))
}

function matchesAll(item: Item, clauses: FilterClause[]): boolean {
  for (const clause of clauses) {
    if (!matchesClause(item, clause)) return false
  }
  return true
}

function matchesClause(item: Item, clause: FilterClause): boolean {
  if ('stars' in clause) {
    const active = clause.stars
    if (!active || !active.length) return true
    const val = item.star ?? 0
    return active.includes(val)
  }
  if ('starsIn' in clause) {
    const active = clause.starsIn.values
    if (!active || !active.length) return true
    const val = item.star ?? 0
    return active.includes(val)
  }
  if ('starsNotIn' in clause) {
    const active = clause.starsNotIn.values
    if (!active || !active.length) return true
    const val = item.star ?? 0
    return !active.includes(val)
  }
  if ('nameContains' in clause) {
    const value = clause.nameContains.value?.trim()
    if (!value) return true
    const name = item.name ?? ''
    return name.toLowerCase().includes(value.toLowerCase())
  }
  if ('nameNotContains' in clause) {
    const value = clause.nameNotContains.value?.trim()
    if (!value) return true
    const name = item.name ?? ''
    return !name.toLowerCase().includes(value.toLowerCase())
  }
  if ('commentsContains' in clause) {
    const value = clause.commentsContains.value?.trim()
    if (!value) return true
    const comments = item.comments ?? ''
    if (!comments) return false
    return comments.toLowerCase().includes(value.toLowerCase())
  }
  if ('commentsNotContains' in clause) {
    const value = clause.commentsNotContains.value?.trim()
    if (!value) return true
    const comments = item.comments ?? ''
    if (!comments) return false
    return !comments.toLowerCase().includes(value.toLowerCase())
  }
  if ('urlContains' in clause) {
    const value = clause.urlContains.value?.trim()
    if (!value) return true
    const url = item.source ?? item.url ?? ''
    if (!url) return false
    return url.toLowerCase().includes(value.toLowerCase())
  }
  if ('urlNotContains' in clause) {
    const value = clause.urlNotContains.value?.trim()
    if (!value) return true
    const url = item.source ?? item.url ?? ''
    if (!url) return false
    return !url.toLowerCase().includes(value.toLowerCase())
  }
  if ('dateRange' in clause) {
    const { from, to } = clause.dateRange
    if (!from && !to) return true
    if (!item.addedAt) return false
    const itemMs = Date.parse(item.addedAt)
    if (Number.isNaN(itemMs)) return false
    const fromMs = parseDateBound(from, false)
    const toMs = parseDateBound(to, true)
    if (fromMs != null && itemMs < fromMs) return false
    if (toMs != null && itemMs > toMs) return false
    return true
  }
  if ('widthCompare' in clause) {
    const { op, value } = clause.widthCompare
    if (!Number.isFinite(value)) return true
    const w = item.w
    if (!Number.isFinite(w) || w <= 0) return false
    return compareNumber(w, op, value)
  }
  if ('heightCompare' in clause) {
    const { op, value } = clause.heightCompare
    if (!Number.isFinite(value)) return true
    const h = item.h
    if (!Number.isFinite(h) || h <= 0) return false
    return compareNumber(h, op, value)
  }
  if ('metricRange' in clause) {
    const { key, min, max } = clause.metricRange
    const raw = item.metrics?.[key]
    if (raw == null) return false
    if (raw < min) return false
    if (raw > max) return false
    return true
  }
  return true
}

export function normalizeFilterAst(raw: unknown): FilterAST | null {
  if (!raw || typeof raw !== 'object') return null
  const and = (raw as FilterAST).and
  if (!Array.isArray(and)) return null
  const normalized: FilterClause[] = []
  for (const clause of and) {
    const next = normalizeClause(clause)
    if (next) normalized.push(next)
  }
  return { and: normalized }
}

export function getStarFilter(filters: FilterAST): number[] {
  const legacy = filters.and.find((c) => 'stars' in c) as { stars: number[] } | undefined
  const include = filters.and.find((c) => 'starsIn' in c) as { starsIn: { values: number[] } } | undefined
  if (include?.starsIn?.values) return include.starsIn.values
  return legacy?.stars ?? []
}

export function setStarFilter(filters: FilterAST, stars: number[]): FilterAST {
  return setStarsInFilter(filters, stars)
}

export function getStarsInFilter(filters: FilterAST): number[] {
  const clause = filters.and.find((c) => 'starsIn' in c) as { starsIn: { values: number[] } } | undefined
  return clause?.starsIn?.values ?? []
}

export function setStarsInFilter(filters: FilterAST, values: number[]): FilterAST {
  const normalized = normalizeStarValues(values)
  const rest = filters.and.filter((c) => !('starsIn' in c) && !('stars' in c))
  if (!normalized.length) return { and: rest }
  return { and: [{ starsIn: { values: normalized } }, ...rest] }
}

export function getStarsNotInFilter(filters: FilterAST): number[] {
  const clause = filters.and.find((c) => 'starsNotIn' in c) as { starsNotIn: { values: number[] } } | undefined
  return clause?.starsNotIn?.values ?? []
}

export function setStarsNotInFilter(filters: FilterAST, values: number[]): FilterAST {
  const normalized = normalizeStarValues(values)
  const rest = filters.and.filter((c) => !('starsNotIn' in c))
  if (!normalized.length) return { and: rest }
  return { and: [{ starsNotIn: { values: normalized } }, ...rest] }
}

export function getNameContainsFilter(filters: FilterAST): string | null {
  const clause = filters.and.find((c) => 'nameContains' in c) as { nameContains: { value: string } } | undefined
  return clause?.nameContains?.value ?? null
}

export function setNameContainsFilter(filters: FilterAST, value: string | null): FilterAST {
  const normalized = normalizeTextValue(value)
  const rest = filters.and.filter((c) => !('nameContains' in c))
  if (!normalized) return { and: rest }
  return { and: [{ nameContains: { value: normalized } }, ...rest] }
}

export function getNameNotContainsFilter(filters: FilterAST): string | null {
  const clause = filters.and.find((c) => 'nameNotContains' in c) as { nameNotContains: { value: string } } | undefined
  return clause?.nameNotContains?.value ?? null
}

export function setNameNotContainsFilter(filters: FilterAST, value: string | null): FilterAST {
  const normalized = normalizeTextValue(value)
  const rest = filters.and.filter((c) => !('nameNotContains' in c))
  if (!normalized) return { and: rest }
  return { and: [{ nameNotContains: { value: normalized } }, ...rest] }
}

export function getCommentsContainsFilter(filters: FilterAST): string | null {
  const clause = filters.and.find((c) => 'commentsContains' in c) as { commentsContains: { value: string } } | undefined
  return clause?.commentsContains?.value ?? null
}

export function setCommentsContainsFilter(filters: FilterAST, value: string | null): FilterAST {
  const normalized = normalizeTextValue(value)
  const rest = filters.and.filter((c) => !('commentsContains' in c))
  if (!normalized) return { and: rest }
  return { and: [{ commentsContains: { value: normalized } }, ...rest] }
}

export function getCommentsNotContainsFilter(filters: FilterAST): string | null {
  const clause = filters.and.find((c) => 'commentsNotContains' in c) as { commentsNotContains: { value: string } } | undefined
  return clause?.commentsNotContains?.value ?? null
}

export function setCommentsNotContainsFilter(filters: FilterAST, value: string | null): FilterAST {
  const normalized = normalizeTextValue(value)
  const rest = filters.and.filter((c) => !('commentsNotContains' in c))
  if (!normalized) return { and: rest }
  return { and: [{ commentsNotContains: { value: normalized } }, ...rest] }
}

export function getUrlContainsFilter(filters: FilterAST): string | null {
  const clause = filters.and.find((c) => 'urlContains' in c) as { urlContains: { value: string } } | undefined
  return clause?.urlContains?.value ?? null
}

export function setUrlContainsFilter(filters: FilterAST, value: string | null): FilterAST {
  const normalized = normalizeTextValue(value)
  const rest = filters.and.filter((c) => !('urlContains' in c))
  if (!normalized) return { and: rest }
  return { and: [{ urlContains: { value: normalized } }, ...rest] }
}

export function getUrlNotContainsFilter(filters: FilterAST): string | null {
  const clause = filters.and.find((c) => 'urlNotContains' in c) as { urlNotContains: { value: string } } | undefined
  return clause?.urlNotContains?.value ?? null
}

export function setUrlNotContainsFilter(filters: FilterAST, value: string | null): FilterAST {
  const normalized = normalizeTextValue(value)
  const rest = filters.and.filter((c) => !('urlNotContains' in c))
  if (!normalized) return { and: rest }
  return { and: [{ urlNotContains: { value: normalized } }, ...rest] }
}

export function getDateRangeFilter(filters: FilterAST): { from?: string; to?: string } | null {
  const clause = filters.and.find((c) => 'dateRange' in c) as { dateRange: { from?: string; to?: string } } | undefined
  return clause?.dateRange ?? null
}

export function setDateRangeFilter(
  filters: FilterAST,
  range: { from?: string | null; to?: string | null } | null
): FilterAST {
  const from = normalizeDateValue(range?.from ?? null)
  const to = normalizeDateValue(range?.to ?? null)
  const rest = filters.and.filter((c) => !('dateRange' in c))
  if (!from && !to) return { and: rest }
  return { and: [{ dateRange: { ...(from ? { from } : {}), ...(to ? { to } : {}) } }, ...rest] }
}

export function getWidthCompareFilter(filters: FilterAST): { op: CompareOp; value: number } | null {
  const clause = filters.and.find((c) => 'widthCompare' in c) as
    | { widthCompare: { op: CompareOp; value: number } }
    | undefined
  return clause?.widthCompare ?? null
}

export function setWidthCompareFilter(filters: FilterAST, compare: { op: CompareOp; value: number } | null): FilterAST {
  const rest = filters.and.filter((c) => !('widthCompare' in c))
  if (!compare || !Number.isFinite(compare.value) || !COMPARE_OPS.has(compare.op)) return { and: rest }
  return { and: [{ widthCompare: { op: compare.op, value: compare.value } }, ...rest] }
}

export function getHeightCompareFilter(filters: FilterAST): { op: CompareOp; value: number } | null {
  const clause = filters.and.find((c) => 'heightCompare' in c) as
    | { heightCompare: { op: CompareOp; value: number } }
    | undefined
  return clause?.heightCompare ?? null
}

export function setHeightCompareFilter(
  filters: FilterAST,
  compare: { op: CompareOp; value: number } | null
): FilterAST {
  const rest = filters.and.filter((c) => !('heightCompare' in c))
  if (!compare || !Number.isFinite(compare.value) || !COMPARE_OPS.has(compare.op)) return { and: rest }
  return { and: [{ heightCompare: { op: compare.op, value: compare.value } }, ...rest] }
}

export function getMetricRangeFilter(filters: FilterAST, key: string): { min: number; max: number } | null {
  const clause = filters.and.find((c) => 'metricRange' in c && c.metricRange.key === key) as
    | { metricRange: { key: string; min: number; max: number } }
    | undefined
  return clause?.metricRange ?? null
}

export function setMetricRangeFilter(
  filters: FilterAST,
  key: string,
  range: { min: number; max: number } | null
): FilterAST {
  const rest = filters.and.filter((c) => !('metricRange' in c && c.metricRange.key === key))
  if (!range) return { and: rest }
  return { and: [{ metricRange: { key, min: range.min, max: range.max } }, ...rest] }
}

export function countActiveFilters(filters: FilterAST): number {
  const normalized = normalizeFilterAst(filters)
  return normalized ? normalized.and.length : 0
}

function normalizeClause(clause: unknown): FilterClause | null {
  if (!clause || typeof clause !== 'object') return null
  if ('stars' in clause) {
    const values = normalizeStarValues((clause as { stars?: unknown }).stars)
    if (!values.length) return null
    return { starsIn: { values } }
  }
  if ('starsIn' in clause) {
    const values = normalizeStarValues((clause as { starsIn?: { values?: unknown } }).starsIn?.values)
    if (!values.length) return null
    return { starsIn: { values } }
  }
  if ('starsNotIn' in clause) {
    const values = normalizeStarValues((clause as { starsNotIn?: { values?: unknown } }).starsNotIn?.values)
    if (!values.length) return null
    return { starsNotIn: { values } }
  }
  if ('nameContains' in clause) {
    const value = normalizeTextValue((clause as { nameContains?: { value?: unknown } }).nameContains?.value)
    if (!value) return null
    return { nameContains: { value } }
  }
  if ('nameNotContains' in clause) {
    const value = normalizeTextValue((clause as { nameNotContains?: { value?: unknown } }).nameNotContains?.value)
    if (!value) return null
    return { nameNotContains: { value } }
  }
  if ('commentsContains' in clause) {
    const value = normalizeTextValue((clause as { commentsContains?: { value?: unknown } }).commentsContains?.value)
    if (!value) return null
    return { commentsContains: { value } }
  }
  if ('commentsNotContains' in clause) {
    const value = normalizeTextValue((clause as { commentsNotContains?: { value?: unknown } }).commentsNotContains?.value)
    if (!value) return null
    return { commentsNotContains: { value } }
  }
  if ('urlContains' in clause) {
    const value = normalizeTextValue((clause as { urlContains?: { value?: unknown } }).urlContains?.value)
    if (!value) return null
    return { urlContains: { value } }
  }
  if ('urlNotContains' in clause) {
    const value = normalizeTextValue((clause as { urlNotContains?: { value?: unknown } }).urlNotContains?.value)
    if (!value) return null
    return { urlNotContains: { value } }
  }
  if ('dateRange' in clause) {
    const raw = (clause as { dateRange?: { from?: unknown; to?: unknown } }).dateRange
    const from = normalizeDateValue(raw?.from ?? null)
    const to = normalizeDateValue(raw?.to ?? null)
    if (!from && !to) return null
    return { dateRange: { ...(from ? { from } : {}), ...(to ? { to } : {}) } }
  }
  if ('widthCompare' in clause) {
    const raw = (clause as { widthCompare?: { op?: unknown; value?: unknown } }).widthCompare
    const compare = normalizeCompare(raw?.op, raw?.value)
    if (!compare) return null
    return { widthCompare: compare }
  }
  if ('heightCompare' in clause) {
    const raw = (clause as { heightCompare?: { op?: unknown; value?: unknown } }).heightCompare
    const compare = normalizeCompare(raw?.op, raw?.value)
    if (!compare) return null
    return { heightCompare: compare }
  }
  if ('metricRange' in clause) {
    const raw = (clause as { metricRange?: { key?: unknown; min?: unknown; max?: unknown } }).metricRange
    if (!raw || typeof raw !== 'object') return null
    const key = typeof raw.key === 'string' ? raw.key : ''
    const min = toNumber(raw.min)
    const max = toNumber(raw.max)
    if (!key || min == null || max == null) return null
    if (min > max) return null
    return { metricRange: { key, min, max } }
  }
  return null
}

function normalizeStarValues(values: unknown): number[] {
  if (!Array.isArray(values)) return []
  const out: number[] = []
  const seen = new Set<number>()
  for (const raw of values) {
    const num = typeof raw === 'number' ? raw : (typeof raw === 'string' ? Number(raw) : NaN)
    if (!Number.isInteger(num) || !STAR_VALUES.has(num)) continue
    if (!seen.has(num)) {
      seen.add(num)
      out.push(num)
    }
  }
  return out
}

function normalizeTextValue(value: unknown): string | null {
  if (typeof value !== 'string') return null
  const trimmed = value.trim()
  return trimmed ? trimmed : null
}

function normalizeDateValue(value: unknown): string | null {
  if (typeof value !== 'string') return null
  const trimmed = value.trim()
  if (!trimmed) return null
  const ms = Date.parse(trimmed)
  if (Number.isNaN(ms)) return null
  return trimmed
}

function normalizeCompare(op: unknown, value: unknown): { op: CompareOp; value: number } | null {
  if (typeof op !== 'string' || !COMPARE_OPS.has(op as CompareOp)) return null
  const num = toNumber(value)
  if (num == null) return null
  return { op: op as CompareOp, value: num }
}

function parseDateBound(value: string | undefined, asEnd: boolean): number | null {
  if (!value) return null
  const trimmed = value.trim()
  if (!trimmed) return null
  const ms = Date.parse(trimmed)
  if (Number.isNaN(ms)) return null
  if (asEnd && DATE_ONLY_RE.test(trimmed)) {
    return ms + 24 * 60 * 60 * 1000 - 1
  }
  return ms
}

function compareNumber(value: number, op: CompareOp, target: number): boolean {
  switch (op) {
    case '<':
      return value < target
    case '<=':
      return value <= target
    case '>':
      return value > target
    case '>=':
      return value >= target
    default:
      return true
  }
}

function toNumber(value: unknown): number | null {
  if (typeof value === 'number' && Number.isFinite(value)) return value
  if (typeof value === 'string') {
    const num = Number(value)
    if (Number.isFinite(num)) return num
  }
  return null
}
