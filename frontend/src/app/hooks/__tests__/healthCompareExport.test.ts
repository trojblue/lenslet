import { describe, expect, it } from 'vitest'
import {
  compareExportCapabilityEquals,
  normalizeHealthCompareExport,
} from '../healthCompareExport'

describe('health compare export contracts', () => {
  it('falls back to v1-only when compare export capability is absent', () => {
    const capability = normalizeHealthCompareExport(undefined)
    expect(capability).toEqual({
      supportedVersions: [1],
      maxPathsV2: null,
      supportsV2: false,
    })
  })

  it('enables v2 only when server declares version 2 and a >2 path limit', () => {
    const capability = normalizeHealthCompareExport({
      supported_versions: [1, 2],
      max_paths_v2: 12,
    })
    expect(capability).toEqual({
      supportedVersions: [1, 2],
      maxPathsV2: 12,
      supportsV2: true,
    })
  })

  it('keeps v2 disabled when capability payload is incomplete or invalid', () => {
    const noMax = normalizeHealthCompareExport({
      supported_versions: [1, 2],
    })
    expect(noMax.supportsV2).toBe(false)

    const pairOnly = normalizeHealthCompareExport({
      supported_versions: [1, 2],
      max_paths_v2: 2,
    })
    expect(pairOnly.supportsV2).toBe(false)

    const invalid = normalizeHealthCompareExport({
      supported_versions: [1, 2, -7, 2.8, Number.NaN],
      max_paths_v2: Number.NaN,
    })
    expect(invalid).toEqual({
      supportedVersions: [1, 2],
      maxPathsV2: null,
      supportsV2: false,
    })
  })

  it('compares capability snapshots by semantic fields', () => {
    const a = normalizeHealthCompareExport({
      supported_versions: [1, 2],
      max_paths_v2: 12,
    })
    const b = normalizeHealthCompareExport({
      supported_versions: [1, 2],
      max_paths_v2: 12,
    })
    const c = normalizeHealthCompareExport({
      supported_versions: [1],
      max_paths_v2: null,
    })

    expect(compareExportCapabilityEquals(a, b)).toBe(true)
    expect(compareExportCapabilityEquals(a, c)).toBe(false)
  })
})
