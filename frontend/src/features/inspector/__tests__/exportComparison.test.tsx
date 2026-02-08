import { describe, expect, it } from 'vitest'
import {
  DEFAULT_EXPORT_COMPARISON_EMBED_METADATA,
  buildComparisonExportFilename,
  buildExportComparisonPayload,
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
})
