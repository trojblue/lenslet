export interface CompareMetadataDiffEntry {
  key: string
  kind: 'different' | 'onlyA' | 'onlyB'
  aText: string
  bText: string
}

export interface CompareMetadataDiffResult {
  entries: CompareMetadataDiffEntry[]
  onlyA: number
  onlyB: number
  different: number
  truncatedCount: number
}

export interface BuildCompareMetadataDiffOptions {
  includePilInfo: boolean
  limit: number
  maxDepth: number
  maxArray: number
}

const JSON_INDENT = 2

function escapeHtml(str: string): string {
  return str
    .replace(/&/g, '&amp;')
    .replace(/</g, '&lt;')
    .replace(/>/g, '&gt;')
    .replace(/"/g, '&quot;')
    .replace(/'/g, '&#39;')
}

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

export function renderJsonValue(value: unknown, path: Array<string | number>, indent: number): string {
  if (value === null) return '<span style="color:var(--json-literal)">null</span>'
  if (value === undefined) return '<span style="color:var(--json-fallback)">undefined</span>'
  if (typeof value === 'string') {
    return `<span style="color:var(--json-string)">${escapeHtml(JSON.stringify(value))}</span>`
  }
  if (typeof value === 'number') {
    return `<span style="color:var(--json-number)">${escapeHtml(String(value))}</span>`
  }
  if (typeof value === 'boolean') {
    return `<span style="color:var(--json-literal)">${value ? 'true' : 'false'}</span>`
  }
  if (Array.isArray(value)) {
    if (value.length === 0) return '[]'
    const pad = ' '.repeat(indent)
    const innerPad = ' '.repeat(indent + JSON_INDENT)
    let out = '[\n'
    value.forEach((item, idx) => {
      const rendered = renderJsonValue(item, [...path, idx], indent + JSON_INDENT)
      out += `${innerPad}${rendered}${idx < value.length - 1 ? ',' : ''}\n`
    })
    out += `${pad}]`
    return out
  }
  if (isPlainObject(value)) {
    const keys = Object.keys(value)
    if (!keys.length) return '{}'
    const pad = ' '.repeat(indent)
    const innerPad = ' '.repeat(indent + JSON_INDENT)
    let out = '{\n'
    keys.forEach((key, idx) => {
      const keyPath = escapeHtml(JSON.stringify([...path, key]))
      const keyLabel = escapeHtml(JSON.stringify(key))
      const keyHtml = `<span class="ui-json-key" data-json-path='${keyPath}' style="color:var(--json-key)">${keyLabel}</span>`
      const rendered = renderJsonValue(value[key], [...path, key], indent + JSON_INDENT)
      out += `${innerPad}${keyHtml}: ${rendered}${idx < keys.length - 1 ? ',' : ''}\n`
    })
    out += `${pad}}`
    return out
  }
  return `<span style="color:var(--json-fallback)">${escapeHtml(String(value))}</span>`
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

export function hasPilInfoMetadata(meta: Record<string, unknown> | null): boolean {
  return !!meta && isPlainObject(meta) && 'pil_info' in meta
}

export function buildCompareMetadataDiff(
  compareMetaA: Record<string, unknown> | null,
  compareMetaB: Record<string, unknown> | null,
  options: BuildCompareMetadataDiffOptions,
): CompareMetadataDiffResult | null {
  return buildCompareMetadataDiffFromNormalized(
    normalizeMetadataRecord(compareMetaA),
    normalizeMetadataRecord(compareMetaB),
    options,
  )
}

export function buildCompareMetadataDiffFromNormalized(
  normalizedA: unknown | null,
  normalizedB: unknown | null,
  options: BuildCompareMetadataDiffOptions,
): CompareMetadataDiffResult | null {
  if (normalizedA == null || normalizedB == null) return null
  const mapA = new Map<string, unknown>()
  const mapB = new Map<string, unknown>()
  const opts = {
    maxDepth: options.maxDepth,
    maxArray: options.maxArray,
    skipPilInfo: !options.includePilInfo,
  }
  flattenMeta(normalizedA, '', mapA, 0, opts)
  flattenMeta(normalizedB, '', mapB, 0, opts)
  const keys = new Set([...mapA.keys(), ...mapB.keys()])
  const entries: CompareMetadataDiffEntry[] = []
  let onlyA = 0
  let onlyB = 0
  let different = 0
  const sortedKeys = Array.from(keys).sort((a, b) => a.localeCompare(b))
  const skipPilInfo = !options.includePilInfo

  for (const key of sortedKeys) {
    if (skipPilInfo && isPilInfoPath(key)) continue
    const hasA = mapA.has(key)
    const hasB = mapB.has(key)
    if (!hasA && hasB) {
      onlyB += 1
      entries.push({ key, kind: 'onlyB', aText: '—', bText: formatMetaValue(mapB.get(key)) })
      continue
    }
    if (hasA && !hasB) {
      onlyA += 1
      entries.push({ key, kind: 'onlyA', aText: formatMetaValue(mapA.get(key)), bText: '—' })
      continue
    }
    const aVal = mapA.get(key)
    const bVal = mapB.get(key)
    const aCmp = toComparableString(aVal)
    const bCmp = toComparableString(bVal)
    if (aCmp !== bCmp) {
      different += 1
      entries.push({ key, kind: 'different', aText: formatMetaValue(aVal), bText: formatMetaValue(bVal) })
    }
  }

  const truncatedCount = Math.max(0, entries.length - options.limit)
  const entriesVisible = truncatedCount ? entries.slice(0, options.limit) : entries
  return {
    entries: entriesVisible,
    onlyA,
    onlyB,
    different,
    truncatedCount,
  }
}
