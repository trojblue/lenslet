import type { FilterClause } from '../../../lib/types'

export type MatchMode = 'all' | 'any'

export type FieldId =
  | 'stars'
  | 'filename'
  | 'comments'
  | 'url'
  | 'dateAdded'
  | 'width'
  | 'height'
  | 'metric'

export type CompareOp = '<' | '<=' | '>' | '>='

export type OperatorId = 'contains' | 'not_contains' | 'in' | 'not_in' | 'between' | CompareOp

export type FieldValue =
  | { kind: 'stars'; values: number[] }
  | { kind: 'text'; value: string }
  | { kind: 'date'; from?: string; to?: string }
  | { kind: 'compare'; value?: number }
  | { kind: 'metric'; key: string; min?: number; max?: number }

export interface FilterRowState {
  id: string
  fieldId: FieldId
  opId: OperatorId
  value: FieldValue
}

export interface FilterGroupState {
  id: string
  mode: MatchMode
  rows: FilterRowState[]
}

export interface OperatorOption {
  id: OperatorId
  label: string
}

export interface FieldDefinition {
  id: FieldId
  label: string
  category: string
  operators: OperatorOption[]
  valueKind: FieldValue['kind']
  defaultOperator: OperatorId
  createValue: (metricKeys: string[]) => FieldValue
  toClause: (row: FilterRowState) => FilterClause | null
  fromClause: (clause: FilterClause) => Omit<FilterRowState, 'id'> | null
  isDisabled?: (metricKeys: string[]) => boolean
}

let idCounter = 0
const nextId = (prefix: string) => `${prefix}-${++idCounter}`

export function createRowState(fieldId: FieldId, metricKeys: string[], id?: string): FilterRowState {
  const def = getFieldDefinition(fieldId, metricKeys)
  return {
    id: id ?? nextId('row'),
    fieldId,
    opId: def.defaultOperator,
    value: def.createValue(metricKeys),
  }
}

export function createGroupState(mode: MatchMode, id?: string): FilterGroupState {
  return {
    id: id ?? nextId('group'),
    mode,
    rows: [],
  }
}

export function rowToClause(row: FilterRowState, metricKeys: string[]): FilterClause | null {
  return getFieldDefinition(row.fieldId, metricKeys).toClause(row)
}

export function clauseToRowState(clause: FilterClause, metricKeys: string[]): Omit<FilterRowState, 'id'> | null {
  for (const def of getFieldDefinitions(metricKeys)) {
    const row = def.fromClause(clause)
    if (row) return row
  }
  return null
}

export function getFieldDefinition(fieldId: FieldId, metricKeys: string[]): FieldDefinition {
  const found = getFieldDefinitions(metricKeys).find((field) => field.id === fieldId)
  if (!found) throw new Error(`Unknown field id: ${fieldId}`)
  return found
}

export function getFieldDefinitions(metricKeys: string[]): FieldDefinition[] {
  const compareOperators: OperatorOption[] = [
    { id: '<', label: '<' },
    { id: '<=', label: '<=' },
    { id: '>', label: '>' },
    { id: '>=', label: '>=' },
  ]

  return [
    {
      id: 'stars',
      label: 'Stars',
      category: 'Attributes',
      operators: [
        { id: 'in', label: 'is any of' },
        { id: 'not_in', label: 'is not' },
      ],
      valueKind: 'stars',
      defaultOperator: 'in',
      createValue: () => ({ kind: 'stars', values: [] }),
      toClause: (row) => {
        if (row.value.kind !== 'stars') return null
        const values = normalizeStarValues(row.value.values)
        if (!values.length) return null
        if (row.opId === 'not_in') return { starsNotIn: { values } }
        return { starsIn: { values } }
      },
      fromClause: (clause) => {
        if ('stars' in clause) {
          const values = normalizeStarValues(clause.stars)
          return { fieldId: 'stars', opId: 'in', value: { kind: 'stars', values } }
        }
        if ('starsIn' in clause) {
          const values = normalizeStarValues(clause.starsIn.values)
          return { fieldId: 'stars', opId: 'in', value: { kind: 'stars', values } }
        }
        if ('starsNotIn' in clause) {
          const values = normalizeStarValues(clause.starsNotIn.values)
          return { fieldId: 'stars', opId: 'not_in', value: { kind: 'stars', values } }
        }
        return null
      },
    },
    {
      id: 'filename',
      label: 'Filename',
      category: 'Attributes',
      operators: [
        { id: 'contains', label: 'contains' },
        { id: 'not_contains', label: 'does not contain' },
      ],
      valueKind: 'text',
      defaultOperator: 'contains',
      createValue: () => ({ kind: 'text', value: '' }),
      toClause: (row) => {
        if (row.value.kind !== 'text') return null
        const value = normalizeText(row.value.value)
        if (!value) return null
        if (row.opId === 'not_contains') return { nameNotContains: { value } }
        return { nameContains: { value } }
      },
      fromClause: (clause) => {
        if ('nameContains' in clause) {
          return { fieldId: 'filename', opId: 'contains', value: { kind: 'text', value: clause.nameContains.value } }
        }
        if ('nameNotContains' in clause) {
          return { fieldId: 'filename', opId: 'not_contains', value: { kind: 'text', value: clause.nameNotContains.value } }
        }
        return null
      },
    },
    {
      id: 'comments',
      label: 'Comments',
      category: 'Attributes',
      operators: [
        { id: 'contains', label: 'contains' },
        { id: 'not_contains', label: 'does not contain' },
      ],
      valueKind: 'text',
      defaultOperator: 'contains',
      createValue: () => ({ kind: 'text', value: '' }),
      toClause: (row) => {
        if (row.value.kind !== 'text') return null
        const value = normalizeText(row.value.value)
        if (!value) return null
        if (row.opId === 'not_contains') return { commentsNotContains: { value } }
        return { commentsContains: { value } }
      },
      fromClause: (clause) => {
        if ('commentsContains' in clause) {
          return { fieldId: 'comments', opId: 'contains', value: { kind: 'text', value: clause.commentsContains.value } }
        }
        if ('commentsNotContains' in clause) {
          return { fieldId: 'comments', opId: 'not_contains', value: { kind: 'text', value: clause.commentsNotContains.value } }
        }
        return null
      },
    },
    {
      id: 'url',
      label: 'URL',
      category: 'Attributes',
      operators: [
        { id: 'contains', label: 'contains' },
        { id: 'not_contains', label: 'does not contain' },
      ],
      valueKind: 'text',
      defaultOperator: 'contains',
      createValue: () => ({ kind: 'text', value: '' }),
      toClause: (row) => {
        if (row.value.kind !== 'text') return null
        const value = normalizeText(row.value.value)
        if (!value) return null
        if (row.opId === 'not_contains') return { urlNotContains: { value } }
        return { urlContains: { value } }
      },
      fromClause: (clause) => {
        if ('urlContains' in clause) {
          return { fieldId: 'url', opId: 'contains', value: { kind: 'text', value: clause.urlContains.value } }
        }
        if ('urlNotContains' in clause) {
          return { fieldId: 'url', opId: 'not_contains', value: { kind: 'text', value: clause.urlNotContains.value } }
        }
        return null
      },
    },
    {
      id: 'dateAdded',
      label: 'Date added',
      category: 'Date',
      operators: [{ id: 'between', label: 'between' }],
      valueKind: 'date',
      defaultOperator: 'between',
      createValue: () => ({ kind: 'date', from: undefined, to: undefined }),
      toClause: (row) => {
        if (row.value.kind !== 'date') return null
        const from = normalizeDate(row.value.from)
        const to = normalizeDate(row.value.to)
        if (!from && !to) return null
        return { dateRange: { ...(from ? { from } : {}), ...(to ? { to } : {}) } }
      },
      fromClause: (clause) => {
        if ('dateRange' in clause) {
          return {
            fieldId: 'dateAdded',
            opId: 'between',
            value: { kind: 'date', from: clause.dateRange.from, to: clause.dateRange.to },
          }
        }
        return null
      },
    },
    {
      id: 'width',
      label: 'Width',
      category: 'Dimensions',
      operators: compareOperators,
      valueKind: 'compare',
      defaultOperator: '>=',
      createValue: () => ({ kind: 'compare', value: undefined }),
      toClause: (row) => {
        if (row.value.kind !== 'compare') return null
        const value = toNumber(row.value.value)
        if (value == null || !isCompareOp(row.opId)) return null
        return { widthCompare: { op: row.opId, value } }
      },
      fromClause: (clause) => {
        if ('widthCompare' in clause) {
          return {
            fieldId: 'width',
            opId: clause.widthCompare.op,
            value: { kind: 'compare', value: clause.widthCompare.value },
          }
        }
        return null
      },
    },
    {
      id: 'height',
      label: 'Height',
      category: 'Dimensions',
      operators: compareOperators,
      valueKind: 'compare',
      defaultOperator: '>=',
      createValue: () => ({ kind: 'compare', value: undefined }),
      toClause: (row) => {
        if (row.value.kind !== 'compare') return null
        const value = toNumber(row.value.value)
        if (value == null || !isCompareOp(row.opId)) return null
        return { heightCompare: { op: row.opId, value } }
      },
      fromClause: (clause) => {
        if ('heightCompare' in clause) {
          return {
            fieldId: 'height',
            opId: clause.heightCompare.op,
            value: { kind: 'compare', value: clause.heightCompare.value },
          }
        }
        return null
      },
    },
    {
      id: 'metric',
      label: 'Metric',
      category: 'Metrics',
      operators: [{ id: 'between', label: 'between' }],
      valueKind: 'metric',
      defaultOperator: 'between',
      createValue: () => ({ kind: 'metric', key: metricKeys[0] ?? '', min: undefined, max: undefined }),
      toClause: (row) => {
        if (row.value.kind !== 'metric') return null
        const key = row.value.key?.trim() ?? ''
        const min = toNumber(row.value.min)
        const max = toNumber(row.value.max)
        if (!key || min == null || max == null) return null
        if (min > max) return null
        return { metricRange: { key, min, max } }
      },
      fromClause: (clause) => {
        if ('metricRange' in clause) {
          return {
            fieldId: 'metric',
            opId: 'between',
            value: {
              kind: 'metric',
              key: clause.metricRange.key,
              min: clause.metricRange.min,
              max: clause.metricRange.max,
            },
          }
        }
        return null
      },
      isDisabled: (keys) => keys.length === 0,
    },
  ]
}

function normalizeText(value: string): string {
  return value.trim()
}

function normalizeDate(value?: string): string | undefined {
  if (!value) return undefined
  const trimmed = value.trim()
  return trimmed ? trimmed : undefined
}

function normalizeStarValues(values: number[]): number[] {
  const out: number[] = []
  for (const raw of values) {
    if (!Number.isInteger(raw) || raw < 0 || raw > 5) continue
    if (!out.includes(raw)) out.push(raw)
  }
  return out
}

function isCompareOp(op: OperatorId): op is CompareOp {
  return op === '<' || op === '<=' || op === '>' || op === '>='
}

function toNumber(value: unknown): number | null {
  if (typeof value === 'number' && Number.isFinite(value)) return value
  if (typeof value === 'string') {
    const num = Number(value)
    if (Number.isFinite(num)) return num
  }
  return null
}
