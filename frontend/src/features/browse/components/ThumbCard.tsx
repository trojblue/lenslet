import React, { useEffect, useRef, useState } from 'react'
import { api } from '../../../shared/api/client'
import { markFirstThumbnailRendered } from '../../../lib/browseHotpath'

/**
 * LRU cache for blob URLs to prevent memory leaks.
 * Automatically revokes old URLs when the cache exceeds MAX_BLOBS.
 */
class BlobUrlCache {
  private cache = new Map<string, string>()
  private readonly maxSize: number
  
  constructor(maxSize: number = 400) {
    this.maxSize = maxSize
    
    // Clean up on page unload
    if (typeof window !== 'undefined') {
      window.addEventListener('beforeunload', () => this.clear(), { once: true })
    }
  }
  
  get(key: string): string | undefined {
    const url = this.cache.get(key)
    if (url) {
      // Refresh LRU position
      this.cache.delete(key)
      this.cache.set(key, url)
    }
    return url
  }
  
  set(key: string, url: string): void {
    // Remove existing entry if present
    if (this.cache.has(key)) {
      this.cache.delete(key)
    }
    
    // Evict oldest entries if at capacity
    while (this.cache.size >= this.maxSize) {
      const oldest = this.cache.keys().next().value
      if (oldest === undefined) break
      const oldUrl = this.cache.get(oldest)
      this.cache.delete(oldest)
      if (oldUrl) {
        try { URL.revokeObjectURL(oldUrl) } catch {}
      }
    }
    
    this.cache.set(key, url)
  }
  
  clear(): void {
    for (const url of this.cache.values()) {
      try { URL.revokeObjectURL(url) } catch {}
    }
    this.cache.clear()
  }
}

const blobUrlCache = new BlobUrlCache(400)

interface ThumbCardProps {
  path: string
  name: string
  onClick: (e: React.MouseEvent) => void
  selected?: boolean
  highlighted?: boolean
  highlightKey?: string | null
  displayW?: number
  displayH?: number
  ioRoot?: Element | null
  isScrolling?: boolean
  priority?: boolean
}

export default function ThumbCard({
  path,
  name,
  onClick,
  selected,
  highlighted,
  highlightKey,
  displayW,
  displayH,
  ioRoot,
  isScrolling,
  priority,
}: ThumbCardProps) {
  const hostRef = useRef<HTMLDivElement>(null)
  const [url, setUrl] = useState<string | null>(() => blobUrlCache.get(path) ?? null)
  const [inView, setInView] = useState(false)
  const [loaded, setLoaded] = useState(() => !!url)

  // Intersection observer for lazy loading
  useEffect(() => {
    const host = hostRef.current
    if (!host) return
    
    const observer = new IntersectionObserver(
      (entries) => {
        for (const entry of entries) {
          if (entry.target === host) {
            setInView(entry.isIntersecting || entry.intersectionRatio > 0)
          }
        }
      },
      { root: ioRoot ?? null, rootMargin: '200px 0px', threshold: 0.01 }
    )
    
    observer.observe(host)
    return () => {
      observer.unobserve(host)
      observer.disconnect()
    }
  }, [ioRoot])

  // Load thumbnail when visible and not scrolling
  useEffect(() => {
    // Already have URL
    if (url) return
    
    // Not ready to load
    if (!((inView && !isScrolling) || priority)) return
    
    let alive = true
    
    api.getThumb(path)
      .then((blob) => {
        if (!alive) return
        const newUrl = URL.createObjectURL(blob)
        blobUrlCache.set(path, newUrl)
        setUrl(newUrl)
      })
      .catch(() => {
        // Ignore thumbnail load errors
      })
    
    return () => {
      alive = false
    }
  }, [path, url, inView, isScrolling, priority])

  // Reset loaded state when URL changes
  useEffect(() => {
    if (!url) {
      setLoaded(false)
      return
    }

    // If the image is already cached, mark it loaded to avoid flicker (e.g. after browser zoom/layout shifts).
    const imgEl = hostRef.current?.querySelector('img') as HTMLImageElement | null
    if (imgEl && imgEl.complete && imgEl.naturalWidth > 0) {
      setLoaded(true)
      markFirstThumbnailRendered(path)
    } else {
      setLoaded(false)
    }
  }, [url])
  
  // Reset URL when path changes
  useEffect(() => {
    setUrl(blobUrlCache.get(path) ?? null)
  }, [path])

  const cardClassName = [
    'absolute inset-0 relative bg-hover border border-border rounded-lg overflow-hidden select-none',
    selected ? 'outline-2 outline-accent' : '',
    highlighted ? 'thumb-updated-ring' : '',
    'hover:outline hover:outline-1 hover:outline-accent',
  ].filter(Boolean).join(' ')

  return (
    <div 
      ref={hostRef} 
      data-highlight-key={highlightKey ?? undefined}
      className={cardClassName}
      onClick={onClick}
    >
      {url ? (
        <img
          className={`w-full h-full object-cover block pointer-events-none select-none opacity-0 transition-opacity duration-[160ms] ${loaded ? 'opacity-100' : ''}`}
          src={url}
          alt={name}
          loading="lazy"
          decoding="async"
          onLoad={() => {
            setLoaded(true)
            markFirstThumbnailRendered(path)
          }}
          width={displayW ? Math.round(displayW) : undefined}
          height={displayH ? Math.round(displayH) : undefined}
        />
      ) : null}
    </div>
  )
}
