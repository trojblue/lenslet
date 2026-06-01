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

function parseBodyText(text: string, contentType: string): unknown {
  if (!text) return null
  if (contentType.includes('application/json') || looksLikeJson(text)) {
    try {
      return JSON.parse(text)
    } catch {
      return text
    }
  }
  return text
}

async function readResponseBody(res: Response): Promise<unknown> {
  const text = await res.text().catch(() => '')
  return parseBodyText(text, res.headers.get('content-type') || '')
}

function formatValidationDetail(detail: unknown): string | null {
  if (!Array.isArray(detail)) return null
  const messages = detail.flatMap((entry) => {
    if (!entry || typeof entry !== 'object') return []
    const item = entry as Record<string, unknown>
    const msg = typeof item.msg === 'string' ? item.msg : null
    if (!msg) return []
    const loc = Array.isArray(item.loc) ? item.loc.map(String).join('.') : null
    return loc ? [`${loc}: ${msg}`] : [msg]
  })
  if (messages.length === 0) return null
  const suffix = messages.length > 3 ? `; +${messages.length - 3} more` : ''
  return `validation failed: ${messages.slice(0, 3).join('; ')}${suffix}`
}

function buildMessage(status: number, body: unknown, url: string): string {
  if (body && typeof body === 'object') {
    const maybe = body as Record<string, unknown>
    const err = typeof maybe.error === 'string' ? maybe.error : null
    const msg = typeof maybe.message === 'string' ? maybe.message : null
    if (err && msg) return `${err}: ${msg}`
    if (err) return err
    if (msg) return msg
    if (typeof maybe.detail === 'string') return maybe.detail
    const validationMessage = formatValidationDetail(maybe.detail)
    if (validationMessage) return validationMessage
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
    const body = await readResponseBody(res)
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
      const body = await readResponseBody(res)
      throw new FetchError(res.status, buildMessage(res.status, body, url), url, body)
    }
    return res.blob()
  }).finally(() => {
    if (timeoutId) window.clearTimeout(timeoutId)
  })

  return { promise, abort: () => ctrl.abort() }
}
