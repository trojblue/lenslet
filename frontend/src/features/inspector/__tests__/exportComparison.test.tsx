import { describe, expect, it } from 'vitest'
import {
  DEFAULT_EXPORT_COMPARISON_EMBED_METADATA,
  EXPORT_COMPARISON_MIN_SELECTIONS_MESSAGE,
  MAX_EXPORT_COMPARISON_PATHS_V2,
  MAX_EXPORT_COMPARISON_PATHS_V2_GIF,
  buildComparisonExportFilename,
  buildExportComparisonPayload,
  buildExportComparisonV2MaxPathsMessage,
} from '../compareExportBoundary'
import { buildInspectorComparisonExportPayload } from '../hooks/useInspectorCompareExport'
import { getSelectionExportDisabledReason } from '../sections/SelectionExportSection'

describe('comparison export helpers', () => {
  it('keeps metadata embedding enabled by default', () => {
    expect(DEFAULT_EXPORT_COMPARISON_EMBED_METADATA).toBe(true)
  })

  it('builds v2 payloads for 2-path exports', () => {
    const result = buildExportComparisonPayload({
      paths: ['/a.png', '/b.png'],
      labelsText: 'Prompt A\nPrompt B',
      embedMetadata: true,
      reverseOrder: false,
      outputFormat: 'png',
      highQualityGif: false,
    })

    expect(result.ok).toBe(true)
    if (!result.ok) return
    expect(result.payload.v).toBe(2)
    expect(result.payload.paths).toEqual(['/a.png', '/b.png'])
    expect(result.payload.labels).toEqual(['Prompt A', 'Prompt B'])
    expect(result.payload.reverse_order).toBe(false)
    expect(result.payload.embed_metadata).toBe(true)
    expect(result.payload.output_format).toBe('png')
  })

  it('preserves second-line mapping when first line is blank', () => {
    const result = buildExportComparisonPayload({
      paths: ['/a.png', '/b.png'],
      labelsText: '\nPrompt B',
      embedMetadata: true,
      reverseOrder: false,
      outputFormat: 'png',
      highQualityGif: false,
    })

    expect(result.ok).toBe(true)
    if (!result.ok) return
    expect(result.payload.labels).toEqual(['', 'Prompt B'])
  })

  it('validates label count against selected paths', () => {
    const result = buildExportComparisonPayload({
      paths: ['/a.png', '/b.png'],
      labelsText: 'A\nB\nC',
      embedMetadata: true,
      reverseOrder: false,
      outputFormat: 'png',
      highQualityGif: false,
    })

    expect(result.ok).toBe(false)
    if (result.ok) return
    expect(result.message).toContain('at most 2 label lines')
  })

  it('rejects payloads with fewer than 2 valid paths', () => {
    const tooFew = buildExportComparisonPayload({
      paths: ['/a.png'],
      labelsText: '',
      embedMetadata: true,
      reverseOrder: false,
      outputFormat: 'png',
      highQualityGif: false,
    })
    expect(tooFew.ok).toBe(false)
    if (!tooFew.ok) {
      expect(tooFew.message).toContain(EXPORT_COMPARISON_MIN_SELECTIONS_MESSAGE)
    }

    const hasBlank = buildExportComparisonPayload({
      paths: ['/a.png', '   ', '/c.png'],
      labelsText: '',
      embedMetadata: true,
      reverseOrder: false,
      outputFormat: 'png',
      highQualityGif: false,
    })
    expect(hasBlank.ok).toBe(false)
    if (!hasBlank.ok) {
      expect(hasBlank.message).toContain(EXPORT_COMPARISON_MIN_SELECTIONS_MESSAGE)
    }
  })

  it('sets reverse_order when reverse export is requested', () => {
    const result = buildExportComparisonPayload({
      paths: ['/a.png', '/b.png'],
      labelsText: 'A\nB',
      embedMetadata: false,
      reverseOrder: true,
      outputFormat: 'png',
      highQualityGif: false,
    })

    expect(result.ok).toBe(true)
    if (!result.ok) return
    expect(result.payload.reverse_order).toBe(true)
    expect(result.payload.paths).toEqual(['/a.png', '/b.png'])
    expect(result.payload.labels).toEqual(['A', 'B'])
    expect(result.payload.output_format).toBe('png')
  })

  it('builds ASCII-safe timestamped filenames', () => {
    const at = new Date('2026-02-08T03:54:37Z')
    expect(buildComparisonExportFilename(false, 'png', at)).toBe('comparison_20260208_035437.png')
    expect(buildComparisonExportFilename(true, 'png', at)).toBe('comparison_reverse_20260208_035437.png')
    expect(buildComparisonExportFilename(false, 'gif', at)).toBe('comparison_20260208_035437.gif')
  })

  it('allows GIF payloads above the PNG path limit', () => {
    const paths = Array.from({ length: MAX_EXPORT_COMPARISON_PATHS_V2 + 1 }, (_, idx) => `/f${idx}.png`)
    const labelsText = Array.from({ length: MAX_EXPORT_COMPARISON_PATHS_V2 + 1 }, (_, idx) => `L${idx}`).join('\n')
    const result = buildExportComparisonPayload({
      paths,
      labelsText,
      embedMetadata: true,
      reverseOrder: false,
      outputFormat: 'gif',
      highQualityGif: false,
    })

    expect(result.ok).toBe(true)
    if (!result.ok) return
    expect(result.payload.paths).toHaveLength(MAX_EXPORT_COMPARISON_PATHS_V2 + 1)
    expect(result.payload.output_format).toBe('gif')
  })

  it('rejects payloads above format-specific max paths', () => {
    const pngTooMany = buildExportComparisonPayload({
      paths: Array.from({ length: MAX_EXPORT_COMPARISON_PATHS_V2 + 1 }, (_, idx) => `/f${idx}.png`),
      labelsText: '',
      embedMetadata: true,
      reverseOrder: false,
      outputFormat: 'png',
      highQualityGif: false,
    })
    expect(pngTooMany.ok).toBe(false)
    if (!pngTooMany.ok) {
      expect(pngTooMany.message).toBe(
        buildExportComparisonV2MaxPathsMessage(MAX_EXPORT_COMPARISON_PATHS_V2, MAX_EXPORT_COMPARISON_PATHS_V2 + 1),
      )
    }

    const gifTooMany = buildExportComparisonPayload({
      paths: Array.from({ length: MAX_EXPORT_COMPARISON_PATHS_V2_GIF + 1 }, (_, idx) => `/f${idx}.png`),
      labelsText: '',
      embedMetadata: true,
      reverseOrder: false,
      outputFormat: 'gif',
      highQualityGif: false,
    })
    expect(gifTooMany.ok).toBe(false)
    if (!gifTooMany.ok) {
      expect(gifTooMany.message).toBe(
        buildExportComparisonV2MaxPathsMessage(MAX_EXPORT_COMPARISON_PATHS_V2_GIF, MAX_EXPORT_COMPARISON_PATHS_V2_GIF + 1),
      )
    }
  })

  it('builds inspector export payloads directly from selected paths', () => {
    const result = buildInspectorComparisonExportPayload({
      selectedPaths: ['/a.png', '/b.png'],
      labelsText: '',
      embedMetadata: true,
      reverseOrder: false,
      outputFormat: 'png',
      highQualityGif: false,
    })

    expect(result.ok).toBe(true)
    if (!result.ok) return
    expect(result.payload.v).toBe(2)
    expect(result.payload.paths).toEqual(['/a.png', '/b.png'])
  })

  it('computes selection export disabled reason from fixed max paths', () => {
    expect(getSelectionExportDisabledReason({ selectedCount: 2, maxPaths: MAX_EXPORT_COMPARISON_PATHS_V2 })).toBeNull()

    expect(getSelectionExportDisabledReason({ selectedCount: 1, maxPaths: MAX_EXPORT_COMPARISON_PATHS_V2 })).toContain(
      EXPORT_COMPARISON_MIN_SELECTIONS_MESSAGE,
    )

    expect(
      getSelectionExportDisabledReason({
        selectedCount: MAX_EXPORT_COMPARISON_PATHS_V2 + 1,
        maxPaths: MAX_EXPORT_COMPARISON_PATHS_V2,
      }),
    ).toBe(buildExportComparisonV2MaxPathsMessage(MAX_EXPORT_COMPARISON_PATHS_V2, MAX_EXPORT_COMPARISON_PATHS_V2 + 1))
  })
})
