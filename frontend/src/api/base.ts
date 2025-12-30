// Single source of truth for API base URL
export function computeApiBase(): string {
  const envBase = (import.meta as any).env?.VITE_API_BASE as string | undefined
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

export const BASE = computeApiBase()

try {
  if ((import.meta as any).env?.DEV) {
    // Helpful during local dev to see which API origin is used
    console.info('[lenslet] API BASE:', BASE || '(same-origin)')
  }
} catch {}

