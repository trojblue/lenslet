export interface CompareMetadataColumn {
  path: string
  label: string
}

export interface CompareMetadataMatrixRow {
  key: string
  values: string[]
  missingCount: number
}

export interface CompareMetadataMatrixSummary {
  differingRows: number
  missingValues: number
  totalRows: number
}

export interface CompareMetadataMatrixResult {
  columns: CompareMetadataColumn[]
  rows: CompareMetadataMatrixRow[]
  summary: CompareMetadataMatrixSummary
  truncatedRowCount: number
}

export interface CompareMetadataMatrixInput {
  path: string
  label: string
  meta: Record<string, unknown> | null
}

export interface CompareMetadataNormalizedMatrixInput {
  path: string
  label: string
  normalizedMeta: unknown | null
}

export interface BuildCompareMetadataMatrixOptions {
  includePilInfo: boolean
  limit: number
  maxDepth: number
  maxArray: number
}

export type MetadataPathSegment = string | number

export interface JsonRenderNullNode {
  kind: 'null'
  text: 'null'
}

export interface JsonRenderUndefinedNode {
  kind: 'undefined'
  text: 'undefined'
}

export interface JsonRenderStringNode {
  kind: 'string'
  text: string
}

export interface JsonRenderNumberNode {
  kind: 'number'
  text: string
}

export interface JsonRenderBooleanNode {
  kind: 'boolean'
  text: 'true' | 'false'
}

export interface JsonRenderFallbackNode {
  kind: 'fallback'
  text: string
}

export interface JsonRenderArrayNode {
  kind: 'array'
  items: JsonRenderNode[]
}

export interface JsonRenderObjectEntry {
  key: string
  path: MetadataPathSegment[]
  value: JsonRenderNode
}

export interface JsonRenderObjectNode {
  kind: 'object'
  entries: JsonRenderObjectEntry[]
}

export type JsonRenderNode =
  | JsonRenderNullNode
  | JsonRenderUndefinedNode
  | JsonRenderStringNode
  | JsonRenderNumberNode
  | JsonRenderBooleanNode
  | JsonRenderFallbackNode
  | JsonRenderArrayNode
  | JsonRenderObjectNode

function isPlainObject(value: unknown): value is Record<string, unknown> {
  return !!value && typeof value === 'object' && !Array.isArray(value)
}

function isPilInfoPath(path: string): boolean {
  return path === 'pil_info' || path.startsWith('pil_info.') || path.startsWith('pil_info[')
}

function appendPath(base: string, key: string | number): string {
  if (typeof key === 'number') {
    return base ? `${base}[${key}]` : `[${key}]`
  }
  const safe = /^[A-Za-z0-9_$-]+$/.test(key)
  if (!base) return safe ? key : `["${key}"]`
  return safe ? `${base}.${key}` : `${base}["${key}"]`
}

function toComparableString(value: unknown): string {
  if (value == null) return String(value)
  if (typeof value === 'string') return value
  if (typeof value === 'number' || typeof value === 'boolean') return String(value)
  if (Array.isArray(value)) {
    return `[${value.map(toComparableString).join(',')}]`
  }
  if (typeof value === 'object') {
    const entries = Object.entries(value as Record<string, unknown>)
      .sort(([a], [b]) => a.localeCompare(b))
      .map(([key, val]) => `${key}:${toComparableString(val)}`)
    return `{${entries.join(',')}}`
  }
  return String(value)
}

function formatMetaValue(value: unknown): string {
  if (value == null) return '—'
  if (typeof value === 'string') return value
  if (typeof value === 'number' || typeof value === 'boolean') return String(value)
  try {
    return JSON.stringify(value, null, 1)
  } catch {
    return String(value)
  }
}

function flattenMeta(
  value: unknown,
  basePath: string,
  out: Map<string, unknown>,
  depth: number,
  opts: { maxDepth: number; maxArray: number; skipPilInfo: boolean }
): void {
  if (opts.skipPilInfo && isPilInfoPath(basePath)) return

  const rootKey = basePath || '(root)'

  if (depth >= opts.maxDepth) {
    out.set(rootKey, value)
    return
  }

  if (Array.isArray(value)) {
    if (!value.length) {
      out.set(rootKey, [])
      return
    }
    if (value.length > opts.maxArray) {
      out.set(rootKey, value)
      return
    }
    value.forEach((item, idx) => flattenMeta(item, appendPath(basePath, idx), out, depth + 1, opts))
    return
  }

  if (isPlainObject(value)) {
    const keys = Object.keys(value).sort((a, b) => a.localeCompare(b))
    if (!keys.length) {
      out.set(basePath || '(root)', {})
      return
    }
    for (const key of keys) {
      if (opts.skipPilInfo && !basePath && key === 'pil_info') continue
      flattenMeta(value[key], appendPath(basePath, key), out, depth + 1, opts)
    }
    return
  }

  out.set(rootKey, value)
}

// Try to turn JSON-looking strings (common in PNG text chunks) back into objects.
export function normalizeMetadata(value: unknown): unknown {
  if (Array.isArray(value)) return value.map(normalizeMetadata)
  if (value && typeof value === 'object') {
    return Object.fromEntries(
      Object.entries(value as Record<string, unknown>).map(([k, v]) => [k, normalizeMetadata(v)]),
    )
  }
  if (typeof value === 'string') {
    const trimmed = value.trim()
    const looksJson =
      (trimmed.startsWith('{') && trimmed.endsWith('}')) ||
      (trimmed.startsWith('[') && trimmed.endsWith(']')) ||
      (trimmed.startsWith('"') && trimmed.endsWith('"'))

    if (looksJson) {
      try {
        const parsed = JSON.parse(trimmed)
        return normalizeMetadata(parsed)
      } catch {
        return value
      }
    }
  }
  return value
}

export function normalizeMetadataRecord(meta: Record<string, unknown> | null): unknown | null {
  if (!meta) return null
  return normalizeMetadata(meta)
}

export function buildDisplayMetadataFromNormalized(
  normalizedMeta: unknown | null,
  showPilInfo: boolean,
): unknown | null {
  if (!normalizedMeta) return null
  if (!showPilInfo && isPlainObject(normalizedMeta) && 'pil_info' in normalizedMeta) {
    const ordered: Record<string, unknown> = {}
    for (const [key, value] of Object.entries(normalizedMeta)) {
      ordered[key] = key === 'pil_info'
        ? 'Hidden (toggle Show PIL info to expand)'
        : value
    }
    return ordered
  }
  return normalizedMeta
}

export function buildDisplayMetadata(
  meta: Record<string, unknown> | null,
  showPilInfo: boolean,
): unknown | null {
  return buildDisplayMetadataFromNormalized(normalizeMetadataRecord(meta), showPilInfo)
}

export function buildJsonRenderNode(
  value: unknown,
  path: MetadataPathSegment[] = [],
): JsonRenderNode {
  if (value === null) return { kind: 'null', text: 'null' }
  if (value === undefined) return { kind: 'undefined', text: 'undefined' }
  if (typeof value === 'string') {
    return { kind: 'string', text: JSON.stringify(value) }
  }
  if (typeof value === 'number') {
    return { kind: 'number', text: String(value) }
  }
  if (typeof value === 'boolean') {
    return { kind: 'boolean', text: value ? 'true' : 'false' }
  }
  if (Array.isArray(value)) {
    return {
      kind: 'array',
      items: value.map((item, idx) => buildJsonRenderNode(item, [...path, idx])),
    }
  }
  if (isPlainObject(value)) {
    return {
      kind: 'object',
      entries: Object.keys(value).map((key) => {
        const nextPath = [...path, key]
        return {
          key,
          path: nextPath,
          value: buildJsonRenderNode(value[key], nextPath),
        }
      }),
    }
  }
  return { kind: 'fallback', text: String(value) }
}

export function formatPathLabel(path: Array<string | number>): string {
  let current = ''
  for (const segment of path) {
    current = appendPath(current, segment)
  }
  return current || '(root)'
}

export function getValueAtPath(root: unknown, path: Array<string | number>): unknown {
  let current: unknown = root
  for (const segment of path) {
    if (typeof segment === 'number') {
      if (!Array.isArray(current)) return undefined
      current = current[segment]
      continue
    }
    if (!isPlainObject(current)) return undefined
    current = current[segment]
  }
  return current
}

export function formatCopyValue(value: unknown): string {
  if (value === undefined) return 'undefined'
  if (value === null) return 'null'
  if (typeof value === 'string') return value
  try {
    return JSON.stringify(value, null, 1)
  } catch {
    return String(value)
  }
}

export interface MetadataPathCopyPayload {
  pathLabel: string
  copyText: string
}

export function buildMetadataPathCopyPayload(
  root: unknown,
  path: MetadataPathSegment[],
): MetadataPathCopyPayload {
  const value = getValueAtPath(root, path)
  return {
    pathLabel: formatPathLabel(path),
    copyText: formatCopyValue(value),
  }
}

export function hasPilInfoMetadata(meta: Record<string, unknown> | null): boolean {
  return !!meta && isPlainObject(meta) && 'pil_info' in meta
}

export function buildCompareMetadataMatrix(
  entries: CompareMetadataMatrixInput[],
  options: BuildCompareMetadataMatrixOptions,
): CompareMetadataMatrixResult | null {
  return buildCompareMetadataMatrixFromNormalized(
    entries.map((entry) => ({
      path: entry.path,
      label: entry.label,
      normalizedMeta: normalizeMetadataRecord(entry.meta),
    })),
    options,
  )
}

export function buildCompareMetadataMatrixFromNormalized(
  entries: CompareMetadataNormalizedMatrixInput[],
  options: BuildCompareMetadataMatrixOptions,
): CompareMetadataMatrixResult | null {
  if (entries.length < 2) return null

  const columns: CompareMetadataColumn[] = entries.map((entry) => ({
    path: entry.path,
    label: entry.label,
  }))
  const flattenOptions = {
    maxDepth: options.maxDepth,
    maxArray: options.maxArray,
    skipPilInfo: !options.includePilInfo,
  }
  const maps: Array<Map<string, unknown>> = entries.map((entry) => {
    const out = new Map<string, unknown>()
    if (entry.normalizedMeta != null) {
      flattenMeta(entry.normalizedMeta, '', out, 0, flattenOptions)
    }
    return out
  })
  const allKeys = new Set<string>()
  for (const map of maps) {
    for (const key of map.keys()) {
      allKeys.add(key)
    }
  }
  const sortedKeys = Array.from(allKeys).sort((a, b) => a.localeCompare(b))

  const allRows: CompareMetadataMatrixRow[] = []
  let missingValues = 0
  for (const key of sortedKeys) {
    if (flattenOptions.skipPilInfo && isPilInfoPath(key)) continue
    const values = maps.map((map) => (map.has(key) ? map.get(key) : undefined))
    let missingCount = 0
    for (const value of values) {
      if (value === undefined) {
        missingCount += 1
      }
    }
    const comparableValues = values
      .filter((value): value is unknown => value !== undefined)
      .map((value) => toComparableString(value))
    const uniqueComparable = new Set(comparableValues)
    const differs = uniqueComparable.size > 1 || (missingCount > 0 && uniqueComparable.size > 0)
    if (!differs) continue
    allRows.push({
      key,
      values: values.map((value) => (value === undefined ? '—' : formatMetaValue(value))),
      missingCount,
    })
    missingValues += missingCount
  }

  const differingRows = allRows.length
  const truncatedRowCount = Math.max(0, differingRows - options.limit)
  const rows = truncatedRowCount > 0 ? allRows.slice(0, options.limit) : allRows
  return {
    columns,
    rows,
    summary: {
      differingRows,
      missingValues,
      totalRows: differingRows,
    },
    truncatedRowCount,
  }
}
