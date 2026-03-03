import type {
  ExportComparisonOutputFormat,
  ExportComparisonRequest,
  ExportComparisonRequestV2,
} from '../../lib/types'

export const MAX_EXPORT_COMPARISON_PATHS_V2 = 12
export const MAX_EXPORT_COMPARISON_PATHS_V2_GIF = 24
export const MAX_EXPORT_COMPARISON_LABEL_CHARS = 120
export const DEFAULT_EXPORT_COMPARISON_EMBED_METADATA = true
export const EXPORT_COMPARISON_MIN_SELECTIONS_MESSAGE =
  'Comparison export requires at least 2 selected images.'

export function buildExportComparisonV2MaxPathsMessage(maxPaths: number, selectedCount: number): string {
  return `Comparison export supports up to ${maxPaths} selections (selected ${selectedCount}).`
}

function maxExportComparisonPathsForFormat(outputFormat: ExportComparisonOutputFormat): number {
  if (outputFormat === 'gif') return MAX_EXPORT_COMPARISON_PATHS_V2_GIF
  return MAX_EXPORT_COMPARISON_PATHS_V2
}

export type ExportComparisonPayloadV2Args = {
  paths: string[]
  labelsText: string
  embedMetadata: boolean
  reverseOrder: boolean
  outputFormat: ExportComparisonOutputFormat
  highQualityGif: boolean
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

function normalizeExportPaths(paths: string[]): string[] {
  return paths.map((path) => path.trim()).filter((path) => path.length > 0)
}

function validateLabelLines(
  labelsText: string,
  options: {
    maxLines: number
  },
): { ok: true; labels: string[] | undefined } | { ok: false; message: string } {
  const { maxLines } = options
  const lines = normalizeLabelLines(labelsText)
  if (lines.length > maxLines) {
    return {
      ok: false,
      message: `Enter at most ${maxLines} label lines (one per selected image).`,
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

  if (!sanitized.some((line) => line.length > 0)) {
    return { ok: true, labels: undefined }
  }
  return { ok: true, labels: sanitized }
}

function toV2Paths(paths: [string, string, ...string[]]): [string, string, ...string[]] {
  return paths
}

export function buildExportComparisonPayload(
  args: ExportComparisonPayloadV2Args,
): ExportComparisonPayloadResult {
  const { paths, labelsText, embedMetadata, reverseOrder, outputFormat, highQualityGif } = args
  const normalizedPaths = normalizeExportPaths(paths)
  if (normalizedPaths.length !== paths.length || normalizedPaths.length < 2) {
    return { ok: false, message: EXPORT_COMPARISON_MIN_SELECTIONS_MESSAGE }
  }

  const maxPaths = maxExportComparisonPathsForFormat(outputFormat)
  if (normalizedPaths.length > maxPaths) {
    return {
      ok: false,
      message: buildExportComparisonV2MaxPathsMessage(maxPaths, normalizedPaths.length),
    }
  }

  const labelsResult = validateLabelLines(labelsText, {
    maxLines: normalizedPaths.length,
  })
  if (!labelsResult.ok) {
    return labelsResult
  }

  const payload: ExportComparisonRequestV2 = {
    v: 2,
    paths: toV2Paths(normalizedPaths as [string, string, ...string[]]),
    embed_metadata: embedMetadata,
    reverse_order: reverseOrder,
    output_format: outputFormat,
    high_quality_gif: highQualityGif,
  }
  if (labelsResult.labels) {
    payload.labels = labelsResult.labels
  }
  return { ok: true, payload }
}

function pad2(value: number): string {
  return String(value).padStart(2, '0')
}

export function buildComparisonExportFilename(
  reverseOrder: boolean,
  outputFormat: ExportComparisonOutputFormat,
  now: Date = new Date(),
): string {
  const y = now.getUTCFullYear()
  const m = pad2(now.getUTCMonth() + 1)
  const d = pad2(now.getUTCDate())
  const h = pad2(now.getUTCHours())
  const min = pad2(now.getUTCMinutes())
  const s = pad2(now.getUTCSeconds())
  const suffix = reverseOrder ? '_reverse' : ''
  const extension = outputFormat === 'gif' ? 'gif' : 'png'
  return `comparison${suffix}_${y}${m}${d}_${h}${min}${s}.${extension}`
}
