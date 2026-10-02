// Shared by hover preview, viewer, compare, and prefetch flows so cache
// eviction, request deduplication, and abort ownership stay centralized.

interface CacheEntry {
  blob: Blob
  size: number
}

interface InflightEntry {
  promise: Promise<Blob>
  abort?: () => void
}

type AbortableBlobFetchResult = {
  promise: Promise<Blob>
  abort?: () => void
}

type BlobFetchResult = Promise<Blob> | AbortableBlobFetchResult
type BlobFetcher = () => BlobFetchResult

function isAbortableBlobFetchResult(result: BlobFetchResult): result is AbortableBlobFetchResult {
  return typeof result === 'object' && result !== null && 'promise' in result
}

function inflightEntryFromFetchResult(result: BlobFetchResult): InflightEntry {
  if (isAbortableBlobFetchResult(result)) {
    return {
      promise: result.promise,
      abort: result.abort,
    }
  }
  return { promise: result }
}

export class BlobLRUCache {
  private readonly store = new Map<string, CacheEntry>()
  private readonly inflight = new Map<string, InflightEntry>()
  private totalBytes = 0

  constructor(private readonly maxBytes: number) {}

  getMaxBytes(): number {
    return this.maxBytes
  }

  getTotalBytes(): number {
    return this.totalBytes
  }

  getSize(): number {
    return this.store.size
  }

  has(key: string): boolean {
    return this.store.has(key)
  }

  isInflight(key: string): boolean {
    return this.inflight.has(key)
  }

  get(key: string): Blob | undefined {
    const hit = this.store.get(key)
    if (!hit) return undefined
    this.store.delete(key)
    this.store.set(key, hit)
    return hit.blob
  }

  private evictIfNeeded(extraBytes: number): void {
    while (this.totalBytes + extraBytes > this.maxBytes && this.store.size > 0) {
      const oldestKey = this.store.keys().next().value as string | undefined
      if (oldestKey == null) break
      
      const old = this.store.get(oldestKey)
      if (old) {
        this.totalBytes -= old.size
      }
      this.store.delete(oldestKey)
    }
  }

  set(key: string, blob: Blob): void {
    const size = blob.size || 0
    
    if (size > this.maxBytes) {
      return
    }
    
    if (this.store.has(key)) {
      const prev = this.store.get(key)!
      this.totalBytes -= prev.size
      this.store.delete(key)
    }
    
    this.evictIfNeeded(size)
    this.store.set(key, { blob, size })
    this.totalBytes += size
  }

  getOrFetch(
    key: string,
    fetcher: BlobFetcher,
    maxCacheEntryBytes = this.maxBytes,
  ): Promise<Blob> {
    const cached = this.get(key)
    if (cached) return Promise.resolve(cached)

    const existing = this.inflight.get(key)
    if (existing) return existing.promise

    let fetchResult: BlobFetchResult
    try {
      fetchResult = fetcher()
    } catch (error) {
      return Promise.reject(error)
    }
    const { promise, abort } = inflightEntryFromFetchResult(fetchResult)

    const entry: InflightEntry = { promise, abort }
    const wrappedPromise = promise
      .then((blob: Blob) => {
        if (this.inflight.get(key) === entry && blob.size <= maxCacheEntryBytes) {
          this.set(key, blob)
        }
        return blob
      })
      .finally(() => {
        if (this.inflight.get(key) === entry) this.inflight.delete(key)
      })

    entry.promise = wrappedPromise
    this.inflight.set(key, entry)
    return wrappedPromise
  }

  prefetch(
    key: string,
    fetcher: BlobFetcher
  ): void {
    if (this.store.has(key) || this.inflight.has(key)) return

    // Handle background errors without replacing the shared result with a
    // successful empty Blob for foreground callers joining this request.
    void this.getOrFetch(key, fetcher).catch(() => {})
  }

  private abortEntry(entry: InflightEntry): void {
    try {
      entry.abort?.()
    } catch {
      // Cancellation remains best-effort; ownership was already invalidated.
    }
  }

  cancelPrefetch(key: string): void {
    const entry = this.inflight.get(key)
    this.inflight.delete(key)
    if (entry) this.abortEntry(entry)
  }

  clear(): void {
    const entries = Array.from(this.inflight.values())
    this.inflight.clear()
    this.store.clear()
    this.totalBytes = 0
    for (const entry of entries) this.abortEntry(entry)
  }

  evictPrefix(prefix: string): void {
    const norm = (() => {
      const p = prefix ? `/${prefix.replace(/^\/+/, '')}` : '/'
      if (p === '/') return '/'
      return p.replace(/\/+$/, '')
    })()

    const matches = (key: string): boolean => {
      const k = key.startsWith('/') ? key.replace(/\/+$/, '') : `/${key.replace(/\/+$/, '')}`
      if (norm === '/') return true
      return k === norm || k.startsWith(`${norm}/`)
    }

    for (const [key, entry] of Array.from(this.store.entries())) {
      if (matches(key)) {
        this.totalBytes -= entry.size
        this.store.delete(key)
      }
    }

    const canceled: InflightEntry[] = []
    for (const [key, entry] of this.inflight) {
      if (matches(key)) {
        this.inflight.delete(key)
        canceled.push(entry)
      }
    }
    for (const entry of canceled) this.abortEntry(entry)

    if (this.totalBytes < 0) {
      this.totalBytes = 0
    }
  }
}

export const fileCache = new BlobLRUCache(60 * 1024 * 1024)

export const thumbCache = new BlobLRUCache(20 * 1024 * 1024)
