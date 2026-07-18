export type ThumbnailObjectUrlLease = {
  readonly url: string
  readonly decoded: boolean
  markDecoded: () => void
  release: () => void
}

type ObjectUrlApi = {
  createObjectURL: (blob: Blob) => string
  revokeObjectURL: (url: string) => void
}

type CacheEntry = {
  key: string
  blob: Blob
  url: string
  bytes: number
  refs: number
  decoded: boolean
  retired: boolean
  revoked: boolean
}

function normalizedPathPrefix(prefix: string): string {
  const value = prefix ? `/${prefix.replace(/^\/+/, '')}` : '/'
  return value === '/' ? value : value.replace(/\/+$/, '')
}

function pathMatchesPrefix(path: string, prefix: string): boolean {
  const normalizedPath = path.startsWith('/')
    ? path.replace(/\/+$/, '')
    : `/${path.replace(/\/+$/, '')}`
  return prefix === '/' || normalizedPath === prefix || normalizedPath.startsWith(`${prefix}/`)
}

export class ThumbnailObjectUrlCache {
  private readonly entries = new Map<string, CacheEntry>()
  private totalBytes = 0

  constructor(
    private readonly limits: { maxEntries: number; maxBytes: number },
    private readonly objectUrls: ObjectUrlApi,
  ) {}

  peekExisting(key: string): { url: string; decoded: boolean } | null {
    const entry = this.entries.get(key)
    return entry ? { url: entry.url, decoded: entry.decoded } : null
  }

  acquireExisting(key: string): ThumbnailObjectUrlLease | null {
    const entry = this.entries.get(key)
    if (!entry) return null
    this.touch(entry)
    return this.lease(entry)
  }

  acquire(key: string, blob: Blob): ThumbnailObjectUrlLease {
    const current = this.entries.get(key)
    if (current?.blob === blob) {
      this.touch(current)
      return this.lease(current)
    }
    if (current) this.retire(current)

    const entry: CacheEntry = {
      key,
      blob,
      url: this.objectUrls.createObjectURL(blob),
      bytes: blob.size,
      refs: 0,
      decoded: false,
      retired: false,
      revoked: false,
    }
    this.entries.set(key, entry)
    this.totalBytes += entry.bytes
    const lease = this.lease(entry)
    this.trim()
    return lease
  }

  evictPrefix(prefix: string): void {
    const normalizedPrefix = normalizedPathPrefix(prefix)
    for (const [key, entry] of Array.from(this.entries.entries())) {
      if (pathMatchesPrefix(key, normalizedPrefix)) this.retire(entry)
    }
  }

  clear(): void {
    for (const entry of Array.from(this.entries.values())) this.retire(entry)
  }

  getSize(): number {
    return this.entries.size
  }

  private lease(entry: CacheEntry): ThumbnailObjectUrlLease {
    entry.refs += 1
    let released = false
    return {
      url: entry.url,
      get decoded() {
        return entry.decoded
      },
      markDecoded: () => {
        if (!entry.revoked) entry.decoded = true
      },
      release: () => {
        if (released) return
        released = true
        entry.refs = Math.max(0, entry.refs - 1)
        if (entry.retired && entry.refs === 0) this.finalize(entry)
        this.trim()
      },
    }
  }

  private touch(entry: CacheEntry): void {
    if (this.entries.get(entry.key) !== entry) return
    this.entries.delete(entry.key)
    this.entries.set(entry.key, entry)
  }

  private retire(entry: CacheEntry): void {
    if (entry.retired) return
    entry.retired = true
    if (this.entries.get(entry.key) === entry) this.entries.delete(entry.key)
    if (entry.refs === 0) this.finalize(entry)
  }

  private finalize(entry: CacheEntry): void {
    if (entry.revoked) return
    entry.revoked = true
    this.totalBytes = Math.max(0, this.totalBytes - entry.bytes)
    try {
      this.objectUrls.revokeObjectURL(entry.url)
    } catch {
      // The browser owns object URL teardown; revocation failures are non-fatal.
    }
  }

  private trim(): void {
    while (
      this.entries.size > this.limits.maxEntries
      || this.totalBytes > this.limits.maxBytes
    ) {
      const candidate = Array.from(this.entries.values()).find((entry) => entry.refs === 0)
      if (!candidate) return
      this.retire(candidate)
    }
  }
}

export const thumbnailObjectUrlCache = new ThumbnailObjectUrlCache(
  { maxEntries: 400, maxBytes: 20 * 1024 * 1024 },
  {
    createObjectURL: (blob) => URL.createObjectURL(blob),
    revokeObjectURL: (url) => URL.revokeObjectURL(url),
  },
)
