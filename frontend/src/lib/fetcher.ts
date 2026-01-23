type FetchOpts = RequestInit & { timeoutMs?: number }

export class FetchError extends Error {
  status: number
  url: string
  body: unknown

  constructor(status: number, message: string, url: string, body?: unknown) {
    super(message)
    this.name = 'FetchError'
    this.status = status
    this.url = url
    this.body = body
  }
}

function looksLikeJson(text: string): boolean {
  const trimmed = text.trim()
  return trimmed.startsWith('{') || trimmed.startsWith('[')
}

function buildMessage(status: number, body: unknown, url: string): string {
  if (body && typeof body === 'object') {
    const maybe = body as Record<string, unknown>
    const err = typeof maybe.error === 'string' ? maybe.error : null
    const msg = typeof maybe.message === 'string' ? maybe.message : null
    if (err && msg) return `${err}: ${msg}`
    if (err) return err
    if (msg) return msg
  }
  if (typeof body === 'string' && body) return body
  return `HTTP ${status} for ${url}`
}

export function fetchJSON<T>(url: string, opts: FetchOpts = {}) {
  const { timeoutMs, ...init } = opts
  const ctrl = new AbortController()
  let timeoutId: number | undefined
  if (timeoutMs) {
    timeoutId = window.setTimeout(() => ctrl.abort(), timeoutMs)
  }

  const promise = fetch(url, { ...init, signal: ctrl.signal }).then(async (res) => {
    let body: unknown = null
    const text = await res.text().catch(() => '')
    if (text) {
      const contentType = res.headers.get('content-type') || ''
      if (contentType.includes('application/json') || looksLikeJson(text)) {
        try {
          body = JSON.parse(text)
        } catch {
          body = text
        }
      } else {
        body = text
      }
    }
    if (!res.ok) {
      throw new FetchError(res.status, buildMessage(res.status, body, url), url, body)
    }
    return body as T
  }).finally(() => {
    if (timeoutId) window.clearTimeout(timeoutId)
  })

  return { promise, abort: () => ctrl.abort() }
}

export function fetchBlob(url: string, opts: FetchOpts = {}) {
  const { timeoutMs, ...init } = opts
  const ctrl = new AbortController()
  let timeoutId: number | undefined
  if (timeoutMs) {
    timeoutId = window.setTimeout(() => ctrl.abort(), timeoutMs)
  }

  const promise = fetch(url, { ...init, signal: ctrl.signal }).then(async (res) => {
    if (!res.ok) {
      const text = await res.text().catch(() => '')
      const body = text ? text : null
      throw new FetchError(res.status, buildMessage(res.status, body, url), url, body)
    }
    return res.blob()
  }).finally(() => {
    if (timeoutId) window.clearTimeout(timeoutId)
  })

  return { promise, abort: () => ctrl.abort() }
}
