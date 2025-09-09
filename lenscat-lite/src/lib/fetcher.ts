export function fetchJSON<T>(url: string, opts: RequestInit = {}) {
  const ctrl = new AbortController()
  const promise = fetch(url, { ...opts, signal: ctrl.signal }).then(r => {
    if (!r.ok) throw new Error(`HTTP ${r.status} for ${url}`)
    return r.json() as Promise<T>
  })
  return { promise, abort: () => ctrl.abort() }
}

export function fetchBlob(url: string, opts: RequestInit = {}) {
  const ctrl = new AbortController()
  const promise = fetch(url, { ...opts, signal: ctrl.signal }).then(r => {
    if (!r.ok) throw new Error(`HTTP ${r.status} for ${url}`)
    return r.blob()
  })
  return { promise, abort: () => ctrl.abort() }
}
