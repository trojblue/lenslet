/**
 * Simple in-memory LRU cache for Blobs with a total byte limit.
 * Shared by hover preview, viewer, and prefetchers.
 * 
 * Features:
 * - LRU eviction when byte limit is reached
 * - Deduplication of in-flight requests
 * - Safe prefetching that doesn't block or throw
 */

interface CacheEntry {
  blob: Blob
  size: number
}

interface InflightEntry {
  promise: Promise<Blob>
  abort?: () => void
}

export class BlobLRUCache {
  private readonly store = new Map<string, CacheEntry>()
  private readonly inflight = new Map<string, InflightEntry>()
  private totalBytes = 0

  constructor(private readonly maxBytes: number) {}

  /** Get the maximum byte limit for this cache */
  getMaxBytes(): number {
    return this.maxBytes
  }

  /** Get the current total bytes stored */
  getTotalBytes(): number {
    return this.totalBytes
  }

  /** Get the number of cached entries */
  getSize(): number {
    return this.store.size
  }

  /** Check if a key is cached (not in-flight) */
  has(key: string): boolean {
    return this.store.has(key)
  }

  /** Check if a key is currently being fetched */
  isInflight(key: string): boolean {
    return this.inflight.has(key)
  }

  /**
   * Get a cached blob, refreshing its LRU position.
   * Returns undefined if not cached.
   */
  get(key: string): Blob | undefined {
    const hit = this.store.get(key)
    if (!hit) return undefined
    // Refresh LRU position by re-inserting
    this.store.delete(key)
    this.store.set(key, hit)
    return hit.blob
  }

  /**
   * Evict oldest entries until there's room for extraBytes.
   */
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

  /**
   * Store a blob in the cache, evicting old entries if needed.
   */
  set(key: string, blob: Blob): void {
    const size = blob.size || 0
    
    // Skip blobs larger than the entire cache
    if (size > this.maxBytes) {
      return
    }
    
    // Remove existing entry if present
    if (this.store.has(key)) {
      const prev = this.store.get(key)!
      this.totalBytes -= prev.size
      this.store.delete(key)
    }
    
    this.evictIfNeeded(size)
    this.store.set(key, { blob, size })
    this.totalBytes += size
  }

  /**
   * Get a cached blob or fetch it, deduplicating concurrent requests.
   * @param key - Cache key
   * @param fetcher - Function that returns { promise, abort? }
   */
  async getOrFetch(
    key: string,
    fetcher: () => Promise<Blob> | { promise: Promise<Blob>; abort?: () => void }
  ): Promise<Blob> {
    // Return cached value immediately
    const cached = this.get(key)
    if (cached) return cached

    // Return existing in-flight request
    const existing = this.inflight.get(key)
    if (existing) return existing.promise

    // Start new fetch
    const fetchResult = fetcher()
    const isAbortable = typeof fetchResult === 'object' && 'promise' in fetchResult
    const promise = isAbortable ? fetchResult.promise : fetchResult
    const abort = isAbortable ? fetchResult.abort : undefined

    const wrappedPromise = promise
      .then((b) => {
        this.set(key, b)
        return b
      })
      .finally(() => {
        this.inflight.delete(key)
      })

    this.inflight.set(key, { promise: wrappedPromise, abort })
    return wrappedPromise
  }

  /**
   * Prefetch a blob in the background. Does not throw on error.
   * @param key - Cache key
   * @param fetcher - Function that returns { promise, abort? }
   */
  prefetch(
    key: string,
    fetcher: () => Promise<Blob> | { promise: Promise<Blob>; abort?: () => void }
  ): void {
    // Already cached or in-flight, skip
    if (this.store.has(key) || this.inflight.has(key)) return

    const fetchResult = fetcher()
    const isAbortable = typeof fetchResult === 'object' && 'promise' in fetchResult
    const promise = isAbortable ? fetchResult.promise : fetchResult
    const abort = isAbortable ? fetchResult.abort : undefined

    const wrappedPromise = promise
      .then((b) => {
        this.set(key, b)
        return b
      })
      .catch(() => {
        // Silently ignore prefetch errors - they're non-critical
        return new Blob()
      })
      .finally(() => {
        this.inflight.delete(key)
      })

    this.inflight.set(key, { promise: wrappedPromise, abort })
  }

  /**
   * Cancel an in-flight prefetch if possible.
   */
  cancelPrefetch(key: string): void {
    const entry = this.inflight.get(key)
    if (entry?.abort) {
      try {
        entry.abort()
      } catch {
        // Ignore abort errors
      }
    }
    this.inflight.delete(key)
  }

  /**
   * Clear the entire cache and cancel all in-flight requests.
   */
  clear(): void {
    // Cancel all in-flight requests
    for (const [key, entry] of this.inflight) {
      if (entry.abort) {
        try {
          entry.abort()
        } catch {
          // Ignore abort errors
        }
      }
    }
    this.inflight.clear()
    this.store.clear()
    this.totalBytes = 0
  }
}

/** Cache for full-size images (~60MB) */
export const fileCache = new BlobLRUCache(60 * 1024 * 1024)

/** Cache for thumbnails (~20MB) */
export const thumbCache = new BlobLRUCache(20 * 1024 * 1024)


