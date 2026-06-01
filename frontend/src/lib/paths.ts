export const ALLOWED_PATH = /^[\/@a-zA-Z0-9._\-\/]{1,512}$/

export function sanitizePath(raw: string): string {
  try {
    const decoded = decodeURI(raw || '')
    const withLeading = decoded.startsWith('/') ? decoded : `/${decoded}`
    const squashed = withLeading.replace(/\/{2,}/g, '/')
    const trimmed = squashed.length > 1 ? squashed.replace(/\/$/, '') : squashed
    if (!ALLOWED_PATH.test(trimmed)) return '/'
    return trimmed
  } catch {
    return '/'
  }
}

export function joinPath(a: string, b: string): string {
  const cleanA = a.replace(/\/+$/, '')
  const cleanB = b.replace(/^\/+/, '')
  const joined = [cleanA, cleanB].filter(Boolean).join('/')
  return joined.startsWith('/') ? joined : `/${joined}`
}
