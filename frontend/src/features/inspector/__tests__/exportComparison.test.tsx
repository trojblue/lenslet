import { describe, expect, it } from 'vitest'
import {
  DEFAULT_EXPORT_COMPARISON_EMBED_METADATA,
  EXPORT_COMPARISON_PAIR_ONLY_MESSAGE,
  EXPORT_COMPARISON_V2_PATH_RANGE_MESSAGE,
  buildComparisonExportFilename,
  buildExportComparisonPayload,
  buildExportComparisonPayloadV2,
} from '../exportComparison'

describe('comparison export helpers', () => {
  it('keeps metadata embedding enabled by default', () => {
    expect(DEFAULT_EXPORT_COMPARISON_EMBED_METADATA).toBe(true)
  })

  it('maps textarea line 1 to A and line 2 to B', () => {
    const result = buildExportComparisonPayload({
      pathA: '/a.png',
      pathB: '/b.png',
      labelsText: 'Prompt A\nPrompt B',
      embedMetadata: true,
      reverseOrder: false,
    })

    expect(result.ok).toBe(true)
    if (!result.ok) return
    expect(result.payload.paths).toEqual(['/a.png', '/b.png'])
    expect(result.payload.labels).toEqual(['Prompt A', 'Prompt B'])
    expect(result.payload.reverse_order).toBe(false)
    expect(result.payload.embed_metadata).toBe(true)
  })

  it('preserves second-line mapping when first line is blank', () => {
    const result = buildExportComparisonPayload({
      pathA: '/a.png',
      pathB: '/b.png',
      labelsText: '\nPrompt B',
      embedMetadata: true,
      reverseOrder: false,
    })

    expect(result.ok).toBe(true)
    if (!result.ok) return
    expect(result.payload.labels).toEqual(['', 'Prompt B'])
  })

  it('returns a client-side validation error for more than two lines', () => {
    const result = buildExportComparisonPayload({
      pathA: '/a.png',
      pathB: '/b.png',
      labelsText: 'A\nB\nC',
      embedMetadata: true,
      reverseOrder: false,
    })

    expect(result.ok).toBe(false)
    if (result.ok) return
    expect(result.message).toContain('at most 2 label lines')
  })

  it('returns explicit pair-only guidance when compare paths are incomplete', () => {
    const result = buildExportComparisonPayload({
      pathA: '/a.png',
      pathB: '',
      labelsText: '',
      embedMetadata: true,
      reverseOrder: false,
    })

    expect(result.ok).toBe(false)
    if (result.ok) return
    expect(result.message).toBe(EXPORT_COMPARISON_PAIR_ONLY_MESSAGE)
  })

  it('sets reverse_order when reverse export is requested', () => {
    const result = buildExportComparisonPayload({
      pathA: '/a.png',
      pathB: '/b.png',
      labelsText: 'A\nB',
      embedMetadata: false,
      reverseOrder: true,
    })

    expect(result.ok).toBe(true)
    if (!result.ok) return
    expect(result.payload.reverse_order).toBe(true)
    expect(result.payload.paths).toEqual(['/a.png', '/b.png'])
    expect(result.payload.labels).toEqual(['A', 'B'])
  })

  it('builds ASCII-safe timestamped filenames', () => {
    const at = new Date('2026-02-08T03:54:37Z')
    expect(buildComparisonExportFilename(false, at)).toBe('comparison_20260208_035437.png')
    expect(buildComparisonExportFilename(true, at)).toBe('comparison_reverse_20260208_035437.png')
  })

  it('builds v2 payloads for multi-image exports', () => {
    const result = buildExportComparisonPayloadV2({
      paths: ['/a.png', '/b.png', '/c.png'],
      labelsText: 'A\nB\nC',
      embedMetadata: false,
      reverseOrder: true,
    })

    expect(result.ok).toBe(true)
    if (!result.ok) return
    expect(result.payload.v).toBe(2)
    expect(result.payload.paths).toEqual(['/a.png', '/b.png', '/c.png'])
    expect(result.payload.labels).toEqual(['A', 'B', 'C'])
    expect(result.payload.embed_metadata).toBe(false)
    expect(result.payload.reverse_order).toBe(true)
  })

  it('rejects v2 payloads outside the supported path range', () => {
    const tooFew = buildExportComparisonPayloadV2({
      paths: ['/a.png'],
      labelsText: '',
      embedMetadata: true,
      reverseOrder: false,
    })
    expect(tooFew.ok).toBe(false)
    if (tooFew.ok) return
    expect(tooFew.message).toBe(EXPORT_COMPARISON_V2_PATH_RANGE_MESSAGE)

    const hasBlank = buildExportComparisonPayloadV2({
      paths: ['/a.png', '   ', '/c.png'],
      labelsText: '',
      embedMetadata: true,
      reverseOrder: false,
    })
    expect(hasBlank.ok).toBe(false)
    if (hasBlank.ok) return
    expect(hasBlank.message).toBe(EXPORT_COMPARISON_V2_PATH_RANGE_MESSAGE)
  })

  it('rejects v2 label input when line count exceeds selected paths', () => {
    const result = buildExportComparisonPayloadV2({
      paths: ['/a.png', '/b.png', '/c.png'],
      labelsText: 'A\nB\nC\nD',
      embedMetadata: true,
      reverseOrder: false,
    })

    expect(result.ok).toBe(false)
    if (result.ok) return
    expect(result.message).toContain('at most 3 label lines')
  })
})
