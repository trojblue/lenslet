import type { HealthMode } from '../lib/types'
import { isThemePresetId, type ThemePresetId } from './runtime'

const STORAGE_PREFIX = 'lenslet.v2.theme.'

function normalizeWorkspaceId(value: string | null | undefined): string | null {
  if (typeof value !== 'string') return null
  const trimmed = value.trim()
  return trimmed.length > 0 ? trimmed : null
}

function fallbackScopeSeed(mode: HealthMode | null | undefined, locationSeed?: string): string {
  const normalizedMode = typeof mode === 'string' && mode.length > 0 ? mode : 'browse'
  if (typeof locationSeed === 'string' && locationSeed.length > 0) {
    return `${normalizedMode}:${locationSeed}`
  }
  if (typeof window !== 'undefined' && window.location) {
    return `${normalizedMode}:${window.location.origin}${window.location.pathname}`
  }
  return `${normalizedMode}:server`
}

function hashSeed(seed: string): string {
  let hash = 0xcbf29ce484222325n
  const prime = 0x100000001b3n
  for (let index = 0; index < seed.length; index += 1) {
    hash ^= BigInt(seed.charCodeAt(index))
    hash = BigInt.asUintN(64, hash * prime)
  }
  return hash.toString(16).padStart(16, '0')
}

function getLocalStorage(): Storage | null {
  if (typeof window === 'undefined') return null
  try {
    return window.localStorage
  } catch {
    return null
  }
}

export function buildWorkspaceThemeStorageKey(
  workspaceId: string | null | undefined,
  mode: HealthMode | null | undefined,
  locationSeed?: string,
): string {
  const normalizedWorkspaceId = normalizeWorkspaceId(workspaceId)
  const seed = normalizedWorkspaceId
    ? `workspace:${normalizedWorkspaceId}`
    : `fallback:${fallbackScopeSeed(mode, locationSeed)}`
  return `${STORAGE_PREFIX}${hashSeed(seed)}`
}

export function readStoredThemePreset(
  workspaceId: string | null | undefined,
  mode: HealthMode | null | undefined,
): ThemePresetId | null {
  const storage = getLocalStorage()
  if (!storage) return null
  const key = buildWorkspaceThemeStorageKey(workspaceId, mode)
  try {
    const stored = storage.getItem(key)
    return isThemePresetId(stored) ? stored : null
  } catch {
    return null
  }
}

export function loadWorkspaceThemePreset(
  workspaceId: string | null | undefined,
  mode: HealthMode | null | undefined,
): ThemePresetId {
  return readStoredThemePreset(workspaceId, mode) ?? 'default'
}

export function writeStoredThemePreset(
  workspaceId: string | null | undefined,
  mode: HealthMode | null | undefined,
  themeId: ThemePresetId | null,
): void {
  const storage = getLocalStorage()
  if (!storage) return
  const key = buildWorkspaceThemeStorageKey(workspaceId, mode)
  try {
    if (themeId == null) {
      storage.removeItem(key)
      return
    }
    storage.setItem(key, themeId)
  } catch {
    // Ignore persistence errors.
  }
}
