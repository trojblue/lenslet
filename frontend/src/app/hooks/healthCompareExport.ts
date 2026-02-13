import type { HealthResponse } from '../../lib/types'

export type CompareExportCapability = {
  supportedVersions: number[]
  maxPathsV2: number | null
  supportsV2: boolean
}

const DEFAULT_SUPPORTED_VERSIONS: number[] = [1]

export const DEFAULT_COMPARE_EXPORT_CAPABILITY: CompareExportCapability = {
  supportedVersions: [...DEFAULT_SUPPORTED_VERSIONS],
  maxPathsV2: null,
  supportsV2: false,
}

function coerceVersion(value: unknown): number | null {
  if (typeof value !== 'number' || !Number.isFinite(value)) return null
  const whole = Math.trunc(value)
  return whole > 0 ? whole : null
}

function coerceMaxPathsV2(value: unknown): number | null {
  if (typeof value !== 'number' || !Number.isFinite(value)) return null
  const whole = Math.trunc(value)
  return whole >= 2 ? whole : null
}

export function normalizeHealthCompareExport(
  compareExport: HealthResponse['compare_export'],
): CompareExportCapability {
  let supportedVersions = [...DEFAULT_SUPPORTED_VERSIONS]
  const rawVersions = compareExport?.supported_versions
  if (Array.isArray(rawVersions)) {
    const normalized = Array.from(
      new Set(rawVersions.map((value) => coerceVersion(value)).filter((value): value is number => value !== null)),
    ).sort((a, b) => a - b)
    if (normalized.length > 0) {
      supportedVersions = normalized
    }
  }

  const maxPathsV2 = coerceMaxPathsV2(compareExport?.max_paths_v2)
  const supportsV2 = supportedVersions.includes(2) && maxPathsV2 !== null && maxPathsV2 > 2
  return {
    supportedVersions,
    maxPathsV2,
    supportsV2,
  }
}

export function compareExportCapabilityEquals(
  a: CompareExportCapability,
  b: CompareExportCapability,
): boolean {
  if (a === b) return true
  if (a.supportsV2 !== b.supportsV2) return false
  if (a.maxPathsV2 !== b.maxPathsV2) return false
  if (a.supportedVersions.length !== b.supportedVersions.length) return false
  for (let i = 0; i < a.supportedVersions.length; i += 1) {
    if (a.supportedVersions[i] !== b.supportedVersions[i]) {
      return false
    }
  }
  return true
}
