import type { ExportComparisonRequest } from '../../lib/types'

export const MAX_EXPORT_COMPARISON_LINES = 2
export const MAX_EXPORT_COMPARISON_LABEL_CHARS = 120
export const DEFAULT_EXPORT_COMPARISON_EMBED_METADATA = true

export type ExportComparisonPayloadArgs = {
  pathA: string
  pathB: string
  labelsText: string
  embedMetadata: boolean
  reverseOrder: boolean
}

export type ExportComparisonPayloadResult =
  | { ok: true; payload: ExportComparisonRequest }
  | { ok: false; message: string }

function sanitizeLabelLine(value: string): string {
  return value.replace(/[\u0000-\u001f\u007f]/g, '').trim()
}

function normalizeLabelLines(text: string): string[] {
  const normalized = text.replace(/\r\n?/g, '\n')
  const withoutTrailingEmptyLines = normalized.replace(/\n+$/g, '')
  if (!withoutTrailingEmptyLines) return []
  return withoutTrailingEmptyLines.split('\n')
}

export function buildExportComparisonPayload(args: ExportComparisonPayloadArgs): ExportComparisonPayloadResult {
  const { pathA, pathB, labelsText, embedMetadata, reverseOrder } = args
  if (!pathA || !pathB) {
    return { ok: false, message: 'Comparison export requires both A and B image paths.' }
  }

  const lines = normalizeLabelLines(labelsText)
  if (lines.length > MAX_EXPORT_COMPARISON_LINES) {
    return {
      ok: false,
      message: `Enter at most ${MAX_EXPORT_COMPARISON_LINES} label lines (line 1 = A, line 2 = B).`,
    }
  }

  const sanitized = lines.map((line) => sanitizeLabelLine(line))
  const hasTooLongLabel = sanitized.some((label) => label.length > MAX_EXPORT_COMPARISON_LABEL_CHARS)
  if (hasTooLongLabel) {
    return {
      ok: false,
      message: `Each label must be at most ${MAX_EXPORT_COMPARISON_LABEL_CHARS} characters.`,
    }
  }

  const labels = sanitized.some((line) => line.length > 0) ? sanitized : undefined

  const payload: ExportComparisonRequest = {
    v: 1,
    paths: [pathA, pathB],
    embed_metadata: embedMetadata,
    reverse_order: reverseOrder,
  }
  if (labels) {
    payload.labels = labels
  }
  return { ok: true, payload }
}

function pad2(value: number): string {
  return String(value).padStart(2, '0')
}

export function buildComparisonExportFilename(reverseOrder: boolean, now: Date = new Date()): string {
  const y = now.getUTCFullYear()
  const m = pad2(now.getUTCMonth() + 1)
  const d = pad2(now.getUTCDate())
  const h = pad2(now.getUTCHours())
  const min = pad2(now.getUTCMinutes())
  const s = pad2(now.getUTCSeconds())
  const suffix = reverseOrder ? '_reverse' : ''
  return `comparison${suffix}_${y}${m}${d}_${h}${min}${s}.png`
}
