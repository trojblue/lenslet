import type { FilterAST, FilterClause, FilterExpr, FilterNode, Item } from '../../../lib/types'

type CompareOp = '<' | '<=' | '>' | '>='

const STAR_VALUES = new Set([0, 1, 2, 3, 4, 5])
const COMPARE_OPS = new Set<CompareOp>(['<', '<=', '>', '>='])
const DATE_ONLY_RE = /^\d{4}-\d{2}-\d{2}$/

export type FilterPath = number[]

export function applyFilterAst(items: Item[], filters: FilterAST | null): Item[] {
  if (!filters || !hasActiveClauses(filters)) return items
  return items.filter((it) => matchesNode(it, filters))
}

function hasActiveClauses(node: FilterNode): boolean {
  if (isFilterExpr(node)) {
    const children = getExprNodes(node)
    if (!children.length) return false
    for (const child of children) {
      if (hasActiveClauses(child)) return true
    }
    return false
  }
  return true
}

function matchesNode(item: Item, node: FilterNode): boolean {
  if (isFilterExpr(node)) {
    const children = getExprNodes(node)
    if (!children.length) return true
    if (isAllExpr(node)) return children.every((child) => matchesNode(item, child))
    return children.some((child) => matchesNode(item, child))
  }
  return matchesClause(item, node)
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
    const url = item.url ?? ''
    if (!url) return false
    return url.toLowerCase().includes(value.toLowerCase())
  }
  if ('urlNotContains' in clause) {
    const value = clause.urlNotContains.value?.trim()
    if (!value) return true
    const url = item.url ?? ''
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

  if (isLegacyAst(raw)) {
    const normalized: FilterClause[] = []
    for (const clause of raw.and) {
      const next = normalizeClause(clause)
      if (next) normalized.push(next)
    }
    return { all: normalized }
  }

  if (!isFilterExprLike(raw)) return null
  return normalizeExpr(raw, true)
}

export function getStarFilter(filters: FilterAST): number[] {
  const values = new Set<number>()
  walkFilterClauses(filters, (clause) => {
    if ('stars' in clause) {
      clause.stars.forEach((v) => values.add(v))
    } else if ('starsIn' in clause) {
      clause.starsIn.values.forEach((v) => values.add(v))
    }
  })
  return Array.from(values)
}

export function setStarFilter(filters: FilterAST, stars: number[]): FilterAST {
  return setStarsInFilter(filters, stars)
}

export function getStarsInFilter(filters: FilterAST): number[] {
  const clause = findFirstClause(filters, (c) => 'starsIn' in c || 'stars' in c)
  if (!clause) return []
  if ('starsIn' in clause) return clause.starsIn.values ?? []
  return 'stars' in clause ? clause.stars ?? [] : []
}

export function setStarsInFilter(filters: FilterAST, values: number[]): FilterAST {
  const normalized = normalizeStarValues(values)
  let next = removeClausesByPredicate(filters, (c) => 'starsIn' in c || 'stars' in c)
  if (!normalized.length) return next
  next = addClauseToRoot(next, { starsIn: { values: normalized } })
  return next
}

export function getStarsNotInFilter(filters: FilterAST): number[] {
  const clause = findFirstClause(filters, (c) => 'starsNotIn' in c)
  return clause && 'starsNotIn' in clause ? clause.starsNotIn.values ?? [] : []
}

export function setStarsNotInFilter(filters: FilterAST, values: number[]): FilterAST {
  const normalized = normalizeStarValues(values)
  let next = removeClausesByPredicate(filters, (c) => 'starsNotIn' in c)
  if (!normalized.length) return next
  next = addClauseToRoot(next, { starsNotIn: { values: normalized } })
  return next
}

export function getNameContainsFilter(filters: FilterAST): string | null {
  const clause = findFirstClause(filters, (c) => 'nameContains' in c)
  return clause && 'nameContains' in clause ? clause.nameContains.value ?? null : null
}

export function setNameContainsFilter(filters: FilterAST, value: string | null): FilterAST {
  const normalized = normalizeTextValue(value)
  let next = removeClausesByPredicate(filters, (c) => 'nameContains' in c)
  if (!normalized) return next
  next = addClauseToRoot(next, { nameContains: { value: normalized } })
  return next
}

export function getNameNotContainsFilter(filters: FilterAST): string | null {
  const clause = findFirstClause(filters, (c) => 'nameNotContains' in c)
  return clause && 'nameNotContains' in clause ? clause.nameNotContains.value ?? null : null
}

export function setNameNotContainsFilter(filters: FilterAST, value: string | null): FilterAST {
  const normalized = normalizeTextValue(value)
  let next = removeClausesByPredicate(filters, (c) => 'nameNotContains' in c)
  if (!normalized) return next
  next = addClauseToRoot(next, { nameNotContains: { value: normalized } })
  return next
}

export function getCommentsContainsFilter(filters: FilterAST): string | null {
  const clause = findFirstClause(filters, (c) => 'commentsContains' in c)
  return clause && 'commentsContains' in clause ? clause.commentsContains.value ?? null : null
}

export function setCommentsContainsFilter(filters: FilterAST, value: string | null): FilterAST {
  const normalized = normalizeTextValue(value)
  let next = removeClausesByPredicate(filters, (c) => 'commentsContains' in c)
  if (!normalized) return next
  next = addClauseToRoot(next, { commentsContains: { value: normalized } })
  return next
}

export function getCommentsNotContainsFilter(filters: FilterAST): string | null {
  const clause = findFirstClause(filters, (c) => 'commentsNotContains' in c)
  return clause && 'commentsNotContains' in clause ? clause.commentsNotContains.value ?? null : null
}

export function setCommentsNotContainsFilter(filters: FilterAST, value: string | null): FilterAST {
  const normalized = normalizeTextValue(value)
  let next = removeClausesByPredicate(filters, (c) => 'commentsNotContains' in c)
  if (!normalized) return next
  next = addClauseToRoot(next, { commentsNotContains: { value: normalized } })
  return next
}

export function getUrlContainsFilter(filters: FilterAST): string | null {
  const clause = findFirstClause(filters, (c) => 'urlContains' in c)
  return clause && 'urlContains' in clause ? clause.urlContains.value ?? null : null
}

export function setUrlContainsFilter(filters: FilterAST, value: string | null): FilterAST {
  const normalized = normalizeTextValue(value)
  let next = removeClausesByPredicate(filters, (c) => 'urlContains' in c)
  if (!normalized) return next
  next = addClauseToRoot(next, { urlContains: { value: normalized } })
  return next
}

export function getUrlNotContainsFilter(filters: FilterAST): string | null {
  const clause = findFirstClause(filters, (c) => 'urlNotContains' in c)
  return clause && 'urlNotContains' in clause ? clause.urlNotContains.value ?? null : null
}

export function setUrlNotContainsFilter(filters: FilterAST, value: string | null): FilterAST {
  const normalized = normalizeTextValue(value)
  let next = removeClausesByPredicate(filters, (c) => 'urlNotContains' in c)
  if (!normalized) return next
  next = addClauseToRoot(next, { urlNotContains: { value: normalized } })
  return next
}

export function getDateRangeFilter(filters: FilterAST): { from?: string; to?: string } | null {
  const clause = findFirstClause(filters, (c) => 'dateRange' in c)
  return clause && 'dateRange' in clause ? clause.dateRange ?? null : null
}

export function setDateRangeFilter(
  filters: FilterAST,
  range: { from?: string | null; to?: string | null } | null
): FilterAST {
  const from = normalizeDateValue(range?.from ?? null)
  const to = normalizeDateValue(range?.to ?? null)
  let next = removeClausesByPredicate(filters, (c) => 'dateRange' in c)
  if (!from && !to) return next
  next = addClauseToRoot(next, { dateRange: { ...(from ? { from } : {}), ...(to ? { to } : {}) } })
  return next
}

export function getWidthCompareFilter(filters: FilterAST): { op: CompareOp; value: number } | null {
  const clause = findFirstClause(filters, (c) => 'widthCompare' in c)
  return clause && 'widthCompare' in clause ? clause.widthCompare ?? null : null
}

export function setWidthCompareFilter(filters: FilterAST, compare: { op: CompareOp; value: number } | null): FilterAST {
  let next = removeClausesByPredicate(filters, (c) => 'widthCompare' in c)
  if (!compare || !Number.isFinite(compare.value) || !COMPARE_OPS.has(compare.op)) return next
  next = addClauseToRoot(next, { widthCompare: { op: compare.op, value: compare.value } })
  return next
}

export function getHeightCompareFilter(filters: FilterAST): { op: CompareOp; value: number } | null {
  const clause = findFirstClause(filters, (c) => 'heightCompare' in c)
  return clause && 'heightCompare' in clause ? clause.heightCompare ?? null : null
}

export function setHeightCompareFilter(
  filters: FilterAST,
  compare: { op: CompareOp; value: number } | null
): FilterAST {
  let next = removeClausesByPredicate(filters, (c) => 'heightCompare' in c)
  if (!compare || !Number.isFinite(compare.value) || !COMPARE_OPS.has(compare.op)) return next
  next = addClauseToRoot(next, { heightCompare: { op: compare.op, value: compare.value } })
  return next
}

export function getMetricRangeFilter(filters: FilterAST, key: string): { min: number; max: number } | null {
  const clause = findFirstClause(filters, (c) => 'metricRange' in c && c.metricRange.key === key)
  return clause && 'metricRange' in clause ? clause.metricRange ?? null : null
}

export function setMetricRangeFilter(
  filters: FilterAST,
  key: string,
  range: { min: number; max: number } | null
): FilterAST {
  let next = removeClausesByPredicate(filters, (c) => 'metricRange' in c && c.metricRange.key === key)
  if (!range) return next
  next = addClauseToRoot(next, { metricRange: { key, min: range.min, max: range.max } })
  return next
}

export function countActiveFilters(filters: FilterAST): number {
  const normalized = normalizeFilterAst(filters)
  if (!normalized) return 0
  return countClauses(normalized)
}

export function walkFilterClauses(
  node: FilterNode,
  visit: (clause: FilterClause, path: FilterPath) => void,
  path: FilterPath = []
): void {
  if (isFilterExpr(node)) {
    const children = getExprNodes(node)
    children.forEach((child, index) => {
      walkFilterClauses(child, visit, [...path, index])
    })
    return
  }
  visit(node, path)
}

export function removeClauseAtPath(filters: FilterAST, path: FilterPath): FilterAST {
  const next = removeNodeAtPath(filters, path)
  if (!next || !isFilterExpr(next)) return { all: [] }
  return next
}

function removeNodeAtPath(node: FilterNode, path: FilterPath): FilterNode | null {
  if (!path.length) return node
  if (!isFilterExpr(node)) return node
  const mode = getExprMode(node)
  const children = [...getExprNodes(node)]
  const index = path[0]
  if (index < 0 || index >= children.length) return node

  if (path.length === 1) {
    children.splice(index, 1)
  } else {
    const updated = removeNodeAtPath(children[index], path.slice(1))
    if (!updated) {
      children.splice(index, 1)
    } else {
      children[index] = updated
    }
  }

  if (!children.length) return null
  return mode === 'all' ? { all: children } : { any: children }
}

function normalizeExpr(raw: FilterExpr, allowEmpty: boolean): FilterExpr | null {
  const mode = getExprMode(raw)
  const rawNodes = getExprNodes(raw)
  const normalizedNodes: FilterNode[] = []
  for (const node of rawNodes) {
    const normalized = normalizeNode(node, false)
    if (normalized) normalizedNodes.push(normalized)
  }
  if (!normalizedNodes.length && !allowEmpty) return null
  return mode === 'all' ? { all: normalizedNodes } : { any: normalizedNodes }
}

function normalizeNode(raw: unknown, allowEmpty: boolean): FilterNode | null {
  if (isFilterExprLike(raw)) {
    return normalizeExpr(raw, allowEmpty)
  }
  return normalizeClause(raw)
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
  for (const raw of values) {
    const num = typeof raw === 'number' ? raw : (typeof raw === 'string' ? Number(raw) : NaN)
    if (!Number.isInteger(num) || !STAR_VALUES.has(num)) continue
    if (!out.includes(num)) out.push(num)
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

function isLegacyAst(raw: unknown): raw is { and: unknown[] } {
  return Boolean(
    raw
    && typeof raw === 'object'
    && 'and' in raw
    && Array.isArray((raw as { and?: unknown }).and)
  )
}

function isFilterExprLike(raw: unknown): raw is FilterExpr {
  return Boolean(
    raw
    && typeof raw === 'object'
    && (('all' in raw && Array.isArray((raw as { all?: unknown }).all))
      || ('any' in raw && Array.isArray((raw as { any?: unknown }).any)))
  )
}

function isFilterExpr(node: FilterNode | unknown): node is FilterExpr {
  return isFilterExprLike(node)
}

function isAllExpr(expr: FilterExpr): expr is { all: FilterNode[] } {
  return 'all' in expr
}

function getExprMode(expr: FilterExpr): 'all' | 'any' {
  return isAllExpr(expr) ? 'all' : 'any'
}

function getExprNodes(expr: FilterExpr): FilterNode[] {
  return isAllExpr(expr) ? expr.all : expr.any
}

function countClauses(node: FilterNode): number {
  if (isFilterExpr(node)) {
    return getExprNodes(node).reduce((acc, child) => acc + countClauses(child), 0)
  }
  return 1
}

function findFirstClause(filters: FilterAST, predicate: (clause: FilterClause) => boolean): FilterClause | null {
  let found: FilterClause | null = null
  walkFilterClauses(filters, (clause) => {
    if (!found && predicate(clause)) found = clause
  })
  return found
}

function removeClausesByPredicate(filters: FilterAST, predicate: (clause: FilterClause) => boolean): FilterAST {
  const next = pruneNode(filters, predicate)
  if (!next || !isFilterExpr(next)) return { all: [] }
  return next
}

function pruneNode(node: FilterNode, predicate: (clause: FilterClause) => boolean): FilterNode | null {
  if (!isFilterExpr(node)) {
    return predicate(node) ? null : node
  }
  const mode = getExprMode(node)
  const children = getExprNodes(node)
  const nextChildren: FilterNode[] = []
  for (const child of children) {
    const next = pruneNode(child, predicate)
    if (next) nextChildren.push(next)
  }
  if (!nextChildren.length) return null
  return mode === 'all' ? { all: nextChildren } : { any: nextChildren }
}

function addClauseToRoot(filters: FilterAST, clause: FilterClause): FilterAST {
  const mode = getExprMode(filters)
  const nodes = [...getExprNodes(filters), clause]
  return mode === 'all' ? { all: nodes } : { any: nodes }
}
