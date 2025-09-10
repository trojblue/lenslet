// Simple in-memory LRU cache for Blobs with a total byte limit.
// Shared by hover preview, viewer, and prefetchers.

type CacheEntry = { blob: Blob; size: number }

export class BlobLRUCache {
  private store: Map<string, CacheEntry> = new Map()
  private inflight: Map<string, Promise<Blob>> = new Map()
  private totalBytes = 0
  constructor(private maxBytes: number) {}

  getMaxBytes(): number { return this.maxBytes }
  getTotalBytes(): number { return this.totalBytes }
  has(key: string): boolean { return this.store.has(key) }

  get(key: string): Blob | undefined {
    const hit = this.store.get(key)
    if (!hit) return undefined
    // refresh LRU position
    this.store.delete(key)
    this.store.set(key, hit)
    return hit.blob
  }

  private evictIfNeeded(extraBytes: number) {
    while (this.totalBytes + extraBytes > this.maxBytes && this.store.size) {
      const oldestKey = this.store.keys().next().value as string | undefined
      if (oldestKey == null) break
      const old = this.store.get(oldestKey)
      if (old) {
        this.totalBytes -= old.size
        this.store.delete(oldestKey)
      } else {
        this.store.delete(oldestKey)
      }
    }
  }

  set(key: string, blob: Blob) {
    const size = blob.size || 0
    if (this.store.has(key)) {
      const prev = this.store.get(key)!
      this.totalBytes -= prev.size
      this.store.delete(key)
    }
    this.evictIfNeeded(size)
    this.store.set(key, { blob, size })
    this.totalBytes += size
  }

  async getOrFetch(key: string, fetcher: () => Promise<Blob>): Promise<Blob> {
    const cached = this.get(key)
    if (cached) return cached
    const existing = this.inflight.get(key)
    if (existing) return existing
    const p = fetcher()
      .then(b => { this.set(key, b); return b })
      .finally(() => { this.inflight.delete(key) })
    this.inflight.set(key, p)
    return p
  }

  prefetch(key: string, fetcher: () => Promise<Blob>) {
    if (this.store.has(key) || this.inflight.has(key)) return
    this.inflight.set(key, fetcher().then(b => { this.set(key, b); return b }).finally(()=> this.inflight.delete(key)))
  }
}

// Separate caches for full images and thumbnails
export const fileCache = new BlobLRUCache(60 * 1024 * 1024) // ~60MB
export const thumbCache = new BlobLRUCache(20 * 1024 * 1024) // ~20MB


