export type QuickViewPathSegment = string | number

export interface QuickViewRow {
  id: string
  label: string
  value: string
  sourcePath: string
}

export type QuickViewPathParseResult =
  | {
      ok: true
      path: string
      segments: QuickViewPathSegment[]
    }
  | {
      ok: false
      error: string
    }

export type QuickViewCustomPathsParseResult = {
  paths: string[]
  error: string | null
}

export type QuickViewStoredPathsResult = {
  paths: string[]
  shouldRewrite: boolean
}

export type ShouldShowQuickViewSectionParams = {
  multi: boolean
  autoloadMetadata: boolean
  meta: Record<string, unknown> | null
}

interface QuickViewDefaults {
  prompt: string
  model: string
  lora: string
}

const QUICK_VIEW_DEFAULT_ROW_DEFINITIONS = [
  { key: 'prompt', label: 'Prompt' },
  { key: 'model', label: 'Model' },
  { key: 'lora', label: 'LoRA' },
] as const

const QUICK_VIEW_IDENTIFIER_START = /[A-Za-z_]/
const QUICK_VIEW_IDENTIFIER_CONTINUE = /[A-Za-z0-9_]/

function isObjectRecord(value: unknown): value is Record<string, unknown> {
  return typeof value === 'object' && value !== null && !Array.isArray(value)
}

function toQuickViewDisplayString(value: unknown): string {
  if (value === null || value === undefined) return ''
  if (typeof value === 'string') return value.trim()
  if (typeof value === 'number' || typeof value === 'boolean') return String(value)
  try {
    return JSON.stringify(value)
  } catch {
    return String(value)
  }
}

function consumeIdentifier(path: string, startIdx: number): { value: string; nextIdx: number } | null {
  if (startIdx >= path.length || !QUICK_VIEW_IDENTIFIER_START.test(path[startIdx])) {
    return null
  }
  let idx = startIdx + 1
  while (idx < path.length && QUICK_VIEW_IDENTIFIER_CONTINUE.test(path[idx])) {
    idx += 1
  }
  return {
    value: path.slice(startIdx, idx),
    nextIdx: idx,
  }
}

function resolveQuickViewPathValue(
  root: Record<string, unknown> | null,
  segments: readonly QuickViewPathSegment[],
): unknown {
  let current: unknown = root
  for (const segment of segments) {
    if (typeof segment === 'number') {
      if (!Array.isArray(current) || segment < 0 || segment >= current.length) return undefined
      current = current[segment]
      continue
    }
    if (!isObjectRecord(current) || !(segment in current)) return undefined
    current = current[segment]
  }
  return current
}

export function parseQuickViewPath(rawPath: string): QuickViewPathParseResult {
  const path = rawPath.trim()
  if (!path) {
    return { ok: false, error: 'Path is empty.' }
  }
  if (/\s/.test(path)) {
    return { ok: false, error: 'Whitespace is not allowed in quick-view paths.' }
  }

  const segments: QuickViewPathSegment[] = []
  const firstIdentifier = consumeIdentifier(path, 0)
  if (!firstIdentifier) {
    return {
      ok: false,
      error: 'Path must start with an identifier and only use dot / [index] syntax.',
    }
  }

  segments.push(firstIdentifier.value)
  let cursor = firstIdentifier.nextIdx

  while (cursor < path.length) {
    const currentChar = path[cursor]
    if (currentChar === '.') {
      const nextIdentifier = consumeIdentifier(path, cursor + 1)
      if (!nextIdentifier) {
        return {
          ok: false,
          error: `Expected identifier after '.' at character ${cursor + 1}.`,
        }
      }
      segments.push(nextIdentifier.value)
      cursor = nextIdentifier.nextIdx
      continue
    }

    if (currentChar === '[') {
      const closeIdx = path.indexOf(']', cursor + 1)
      if (closeIdx < 0) {
        return {
          ok: false,
          error: "Missing closing ']' for array index segment.",
        }
      }
      const indexRaw = path.slice(cursor + 1, closeIdx)
      if (!/^\d+$/.test(indexRaw)) {
        return {
          ok: false,
          error: 'Array index segments must be non-negative integers like [0].',
        }
      }
      segments.push(Number(indexRaw))
      cursor = closeIdx + 1
      continue
    }

    return {
      ok: false,
      error: `Unsupported token '${currentChar}'. Use only dot and [index] syntax.`,
    }
  }

  return {
    ok: true,
    path,
    segments,
  }
}

export function parseQuickViewCustomPathsInput(rawText: string): QuickViewCustomPathsParseResult {
  const lines = rawText.split('\n')
  const seen = new Set<string>()
  const paths: string[] = []

  for (let lineIdx = 0; lineIdx < lines.length; lineIdx += 1) {
    const candidate = lines[lineIdx].trim()
    if (!candidate) continue

    const parsed = parseQuickViewPath(candidate)
    if (!parsed.ok) {
      return {
        paths: [],
        error: `Line ${lineIdx + 1}: ${parsed.error}`,
      }
    }
    if (seen.has(parsed.path)) continue
    seen.add(parsed.path)
    paths.push(parsed.path)
  }

  return {
    paths,
    error: null,
  }
}

export function parseStoredQuickViewCustomPaths(raw: string | null): QuickViewStoredPathsResult {
  if (raw === null) {
    return {
      paths: [],
      shouldRewrite: false,
    }
  }

  let parsed: unknown
  try {
    parsed = JSON.parse(raw)
  } catch {
    return {
      paths: [],
      shouldRewrite: true,
    }
  }

  if (!Array.isArray(parsed)) {
    return {
      paths: [],
      shouldRewrite: true,
    }
  }

  const seen = new Set<string>()
  const sanitized: string[] = []
  let shouldRewrite = false

  for (const candidate of parsed) {
    if (typeof candidate !== 'string') {
      shouldRewrite = true
      continue
    }
    const normalized = candidate.trim()
    if (!normalized) {
      shouldRewrite = true
      continue
    }
    const parsedPath = parseQuickViewPath(normalized)
    if (!parsedPath.ok) {
      shouldRewrite = true
      continue
    }
    if (seen.has(parsedPath.path)) {
      shouldRewrite = true
      continue
    }
    if (candidate !== parsedPath.path) {
      shouldRewrite = true
    }
    seen.add(parsedPath.path)
    sanitized.push(parsedPath.path)
  }

  if (parsed.length !== sanitized.length) {
    shouldRewrite = true
  }

  return {
    paths: sanitized,
    shouldRewrite,
  }
}

function readQuickViewDefaults(meta: Record<string, unknown> | null): QuickViewDefaults | null {
  if (!isObjectRecord(meta)) return null
  const defaults = meta.quick_view_defaults
  if (!isObjectRecord(defaults)) return null

  return {
    prompt: toQuickViewDisplayString(defaults.prompt),
    model: toQuickViewDisplayString(defaults.model),
    lora: toQuickViewDisplayString(defaults.lora),
  }
}

export function shouldShowQuickViewSection({
  multi,
  autoloadMetadata,
  meta,
}: ShouldShowQuickViewSectionParams): boolean {
  if (multi || !autoloadMetadata) return false
  const defaults = readQuickViewDefaults(meta)
  if (!defaults) return false
  return Object.values(defaults).some((value) => value.trim().length > 0)
}

export function buildQuickViewRows(
  meta: Record<string, unknown> | null,
  customPaths: readonly string[],
): QuickViewRow[] {
  const defaults = readQuickViewDefaults(meta)
  if (!defaults) return []

  const defaultRows: QuickViewRow[] = QUICK_VIEW_DEFAULT_ROW_DEFINITIONS.map(({ key, label }) => ({
    id: `default:${key}`,
    label,
    value: defaults[key],
    sourcePath: `quick_view_defaults.${key}`,
  }))

  const customRows: QuickViewRow[] = []
  for (const customPath of customPaths) {
    const parsed = parseQuickViewPath(customPath)
    if (!parsed.ok) continue
    const resolvedValue = resolveQuickViewPathValue(meta, parsed.segments)
    customRows.push({
      id: `custom:${parsed.path}`,
      label: parsed.path,
      value: toQuickViewDisplayString(resolvedValue),
      sourcePath: parsed.path,
    })
  }

  return [...defaultRows, ...customRows]
}
