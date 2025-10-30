export const ALLOWED_PATH = /^[\/@a-zA-Z0-9._\-\/]{1,512}$/

export function sanitizePath(raw: string): string {
  try {
    const decoded = decodeURI(raw || '')
    const withLeading = decoded.startsWith('/') ? decoded : `/${decoded}`
    const squashed = withLeading.replace(/\/{2,}/g, '/')
    if (!ALLOWED_PATH.test(squashed)) return '/'
    return squashed
  } catch {
    return '/'
  }
}

export function readHash(): string {
  const h = (window.location.hash || '').replace(/^#/, '')
  return h
}

export function writeHash(p: string) {
  const h = `#${encodeURI(p)}`
  if (window.location.hash !== h) window.location.hash = h
}


