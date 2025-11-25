/** Default timeout for fetch requests (30 seconds) */
const DEFAULT_TIMEOUT_MS = 30_000

/** Custom error class for fetch-related errors */
export class FetchError extends Error {
  constructor(
    message: string,
    public readonly status?: number,
    public readonly url?: string,
    public readonly isAborted?: boolean,
    public readonly isTimeout?: boolean
  ) {
    super(message)
    this.name = 'FetchError'
  }
}

/** Options for fetch operations */
export interface FetchOptions extends RequestInit {
  timeoutMs?: number
}

/** Return type for abortable fetch operations */
export interface AbortableFetch<T> {
  promise: Promise<T>
  abort: () => void
}

/**
 * Perform an abortable JSON fetch with optional timeout.
 * @param url - The URL to fetch
 * @param opts - Fetch options including optional timeoutMs
 * @returns Object with promise and abort function
 */
export function fetchJSON<T>(url: string, opts: FetchOptions = {}): AbortableFetch<T> {
  const { timeoutMs = DEFAULT_TIMEOUT_MS, ...fetchOpts } = opts
  const ctrl = new AbortController()
  
  let timeoutId: ReturnType<typeof setTimeout> | undefined
  
  const promise = new Promise<T>((resolve, reject) => {
    // Set up timeout
    if (timeoutMs > 0) {
      timeoutId = setTimeout(() => {
        ctrl.abort()
        reject(new FetchError(`Request timeout after ${timeoutMs}ms`, undefined, url, false, true))
      }, timeoutMs)
    }
    
    fetch(url, { ...fetchOpts, signal: ctrl.signal })
      .then(async (r) => {
        if (timeoutId) clearTimeout(timeoutId)
        if (!r.ok) {
          throw new FetchError(`HTTP ${r.status} for ${url}`, r.status, url)
        }
        return r.json() as Promise<T>
      })
      .then(resolve)
      .catch((err) => {
        if (timeoutId) clearTimeout(timeoutId)
        if (err instanceof FetchError) {
          reject(err)
        } else if (err.name === 'AbortError') {
          reject(new FetchError('Request aborted', undefined, url, true, false))
        } else {
          reject(new FetchError(err.message || 'Network error', undefined, url))
        }
      })
  })
  
  return {
    promise,
    abort: () => {
      if (timeoutId) clearTimeout(timeoutId)
      ctrl.abort()
    }
  }
}

/**
 * Perform an abortable blob fetch with optional timeout.
 * @param url - The URL to fetch
 * @param opts - Fetch options including optional timeoutMs
 * @returns Object with promise and abort function
 */
export function fetchBlob(url: string, opts: FetchOptions = {}): AbortableFetch<Blob> {
  const { timeoutMs = DEFAULT_TIMEOUT_MS, ...fetchOpts } = opts
  const ctrl = new AbortController()
  
  let timeoutId: ReturnType<typeof setTimeout> | undefined
  
  const promise = new Promise<Blob>((resolve, reject) => {
    // Set up timeout
    if (timeoutMs > 0) {
      timeoutId = setTimeout(() => {
        ctrl.abort()
        reject(new FetchError(`Request timeout after ${timeoutMs}ms`, undefined, url, false, true))
      }, timeoutMs)
    }
    
    fetch(url, { ...fetchOpts, signal: ctrl.signal })
      .then(async (r) => {
        if (timeoutId) clearTimeout(timeoutId)
        if (!r.ok) {
          throw new FetchError(`HTTP ${r.status} for ${url}`, r.status, url)
        }
        return r.blob()
      })
      .then(resolve)
      .catch((err) => {
        if (timeoutId) clearTimeout(timeoutId)
        if (err instanceof FetchError) {
          reject(err)
        } else if (err.name === 'AbortError') {
          reject(new FetchError('Request aborted', undefined, url, true, false))
        } else {
          reject(new FetchError(err.message || 'Network error', undefined, url))
        }
      })
  })
  
  return {
    promise,
    abort: () => {
      if (timeoutId) clearTimeout(timeoutId)
      ctrl.abort()
    }
  }
}

/**
 * Check if an error is a fetch abort (user-initiated or timeout).
 */
export function isAbortError(err: unknown): boolean {
  if (err instanceof FetchError) {
    return err.isAborted === true || err.isTimeout === true
  }
  if (err instanceof Error && err.name === 'AbortError') {
    return true
  }
  return false
}
