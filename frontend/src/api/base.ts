export function computeApiBase(): string {
  const envBase = import.meta.env.VITE_API_BASE
  const inBrowser = typeof window !== 'undefined'
  const pageOrigin = inBrowser ? window.location.origin : 'http://localhost'
  const pageHost = inBrowser ? window.location.hostname : 'localhost'

  const isLocalHostName = /^(localhost|127\.0\.0\.1|0\.0\.0\.0|\[::1\]|.+\.localhost)$/i.test(pageHost)

  if (!envBase) return '' // default to same-origin (single-port)

  // Normalize envBase against page origin if it's a relative path
  let envUrl: URL
  try { envUrl = new URL(envBase, pageOrigin) } catch { return '' }

  const envIsLocal = /^(localhost|127\.0\.0\.1|0\.0\.0\.0|\[::1\])$/i.test(envUrl.hostname)

  // In local dev, allow explicit override (e.g., Vite on 5173 -> API on 8000)
  if (isLocalHostName) return envUrl.origin

  // In production/tunnel, ignore localhost overrides to keep same-origin
  if (envIsLocal) return ''

  // Otherwise honor explicit non-local origin (e.g., separate API domain)
  return envUrl.origin
}

export function apiBase(): string {
  return computeApiBase()
}

export function apiUrl(path: string): string {
  const normalizedPath = path.startsWith('/') ? path : `/${path}`
  return `${apiBase()}${normalizedPath}`
}

export function logApiBaseForDev(): void {
  try {
    if (import.meta.env.DEV) {
      console.info('[lenslet] API BASE:', apiBase() || '(same-origin)')
    }
  } catch {}
}
