/** Allowed characters in paths - alphanumeric, slashes, dots, underscores, hyphens, @ */
export const ALLOWED_PATH = /^[\/@a-zA-Z0-9._\-\/]{1,512}$/

/**
 * Normalize and sanitize a path string.
 * - Decodes URI encoding
 * - Ensures leading slash
 * - Collapses multiple slashes
 * - Validates against allowed characters
 * - Falls back to '/' on invalid input
 */
export function sanitizePath(raw: string): string {
  try {
    const decoded = decodeURI(raw || '')
    const withLeading = decoded.startsWith('/') ? decoded : `/${decoded}`
    const squashed = withLeading.replace(/\/{2,}/g, '/')
    // Remove trailing slash except for root
    const trimmed = squashed.length > 1 ? squashed.replace(/\/$/, '') : squashed
    if (!ALLOWED_PATH.test(trimmed)) return '/'
    return trimmed
  } catch {
    return '/'
  }
}

/**
 * Read the current hash from window.location, stripping the leading '#'.
 * Returns raw (not decoded) string for sanitizePath to handle.
 */
export function readHash(): string {
  return (window.location.hash || '').replace(/^#/, '')
}

/**
 * Write a path to the URL hash, encoding properly.
 * Only updates if the hash would actually change.
 */
export function writeHash(p: string): void {
  const normalized = sanitizePath(p)
  const h = `#${encodeURI(normalized)}`
  if (window.location.hash !== h) {
    window.location.hash = h
  }
}

/**
 * Join two path segments safely.
 * Handles leading/trailing slashes and ensures result starts with '/'.
 */
export function joinPath(a: string, b: string): string {
  const cleanA = a.replace(/\/+$/, '')
  const cleanB = b.replace(/^\/+/, '')
  const joined = [cleanA, cleanB].filter(Boolean).join('/')
  return joined.startsWith('/') ? joined : `/${joined}`
}

/**
 * Get the parent path of a given path.
 * Returns '/' for root or single-segment paths.
 */
export function getParentPath(path: string): string {
  const normalized = sanitizePath(path)
  const parts = normalized.split('/').filter(Boolean)
  if (parts.length <= 1) return '/'
  return '/' + parts.slice(0, -1).join('/')
}

/**
 * Get the final segment (filename or folder name) of a path.
 */
export function getPathName(path: string): string {
  const normalized = sanitizePath(path)
  return normalized.split('/').filter(Boolean).pop() || ''
}

/**
 * Check if a path is the trash folder.
 */
export function isTrashPath(path: string): boolean {
  return path.endsWith('/_trash_')
}


