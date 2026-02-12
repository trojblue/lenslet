import type {
  ExportComparisonLabelsV1,
  ExportComparisonRequest,
  ExportComparisonRequestV1,
  ExportComparisonRequestV2,
} from '../../lib/types'

export const MAX_EXPORT_COMPARISON_LINES = 2
export const MAX_EXPORT_COMPARISON_PATHS_V2 = 12
export const MAX_EXPORT_COMPARISON_LABEL_CHARS = 120
export const DEFAULT_EXPORT_COMPARISON_EMBED_METADATA = true
export const EXPORT_COMPARISON_PAIR_ONLY_MESSAGE = 'Comparison export (v1) requires exactly 2 selected images.'
export const EXPORT_COMPARISON_V2_PATH_RANGE_MESSAGE = `Comparison export (v2) requires between 2 and ${MAX_EXPORT_COMPARISON_PATHS_V2} selected images.`

export type ExportComparisonPayloadArgs = {
  pathA: string
  pathB: string
  labelsText: string
  embedMetadata: boolean
  reverseOrder: boolean
}

export type ExportComparisonPayloadV2Args = {
  paths: string[]
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

function toExportComparisonLabelsV1(lines: string[]): ExportComparisonLabelsV1 | undefined {
  if (lines.length === 0) return undefined
  if (lines.length === 1) return [lines[0]]
  return [lines[0], lines[1]]
}

function normalizeExportPaths(paths: string[]): string[] {
  return paths.map((path) => path.trim()).filter((path) => path.length > 0)
}

function validateLabelLines(
  labelsText: string,
  options: {
    maxLines: number
    tooManyLinesMessage: string
  },
): { ok: true; labels: string[] | undefined } | { ok: false; message: string } {
  const { maxLines, tooManyLinesMessage } = options
  const lines = normalizeLabelLines(labelsText)
  if (lines.length > maxLines) {
    return { ok: false, message: tooManyLinesMessage }
  }

  const sanitized = lines.map((line) => sanitizeLabelLine(line))
  const hasTooLongLabel = sanitized.some((label) => label.length > MAX_EXPORT_COMPARISON_LABEL_CHARS)
  if (hasTooLongLabel) {
    return {
      ok: false,
      message: `Each label must be at most ${MAX_EXPORT_COMPARISON_LABEL_CHARS} characters.`,
    }
  }

  if (!sanitized.some((line) => line.length > 0)) {
    return { ok: true, labels: undefined }
  }
  return { ok: true, labels: sanitized }
}

function toV2Paths(paths: [string, string, ...string[]]): [string, string, ...string[]] {
  return paths
}

export function buildExportComparisonPayload(args: ExportComparisonPayloadArgs): ExportComparisonPayloadResult {
  const { pathA, pathB, labelsText, embedMetadata, reverseOrder } = args
  if (!pathA || !pathB) {
    return { ok: false, message: EXPORT_COMPARISON_PAIR_ONLY_MESSAGE }
  }

  const labelsResult = validateLabelLines(labelsText, {
    maxLines: MAX_EXPORT_COMPARISON_LINES,
    tooManyLinesMessage: `Enter at most ${MAX_EXPORT_COMPARISON_LINES} label lines (line 1 = A, line 2 = B).`,
  })
  if (!labelsResult.ok) {
    return labelsResult
  }

  const payload: ExportComparisonRequestV1 = {
    v: 1,
    paths: [pathA, pathB],
    embed_metadata: embedMetadata,
    reverse_order: reverseOrder,
  }
  if (labelsResult.labels) {
    payload.labels = toExportComparisonLabelsV1(labelsResult.labels)
  }
  return { ok: true, payload }
}

export function buildExportComparisonPayloadV2(
  args: ExportComparisonPayloadV2Args,
): ExportComparisonPayloadResult {
  const { paths, labelsText, embedMetadata, reverseOrder } = args
  const normalizedPaths = normalizeExportPaths(paths)
  if (
    normalizedPaths.length !== paths.length
    || normalizedPaths.length < 2
    || normalizedPaths.length > MAX_EXPORT_COMPARISON_PATHS_V2
  ) {
    return { ok: false, message: EXPORT_COMPARISON_V2_PATH_RANGE_MESSAGE }
  }

  const labelsResult = validateLabelLines(labelsText, {
    maxLines: normalizedPaths.length,
    tooManyLinesMessage: `Enter at most ${normalizedPaths.length} label lines (one per selected image).`,
  })
  if (!labelsResult.ok) {
    return labelsResult
  }

  const payload: ExportComparisonRequestV2 = {
    v: 2,
    paths: toV2Paths(normalizedPaths as [string, string, ...string[]]),
    embed_metadata: embedMetadata,
    reverse_order: reverseOrder,
  }
  if (labelsResult.labels) {
    payload.labels = labelsResult.labels
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
