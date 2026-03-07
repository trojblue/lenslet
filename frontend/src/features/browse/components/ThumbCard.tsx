import React, { useEffect, useRef, useState } from 'react'
import { api } from '../../../api/client'
import { markFirstThumbnailRendered } from '../../../lib/browseHotpath'
import { useBlobUrl } from '../../../shared/hooks/useBlobUrl'

interface ThumbCardProps {
  path: string
  name: string
  onClick: (e: React.MouseEvent) => void
  selected?: boolean
  highlighted?: boolean
  highlightKey?: string | null
  selectionOrder?: number | null
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
  selectionOrder = null,
  displayW,
  displayH,
  ioRoot,
  isScrolling,
  priority,
}: ThumbCardProps) {
  const hostRef = useRef<HTMLDivElement>(null)
  const [inView, setInView] = useState(false)
  const [loaded, setLoaded] = useState(false)
  const [requestedPath, setRequestedPath] = useState<string | null>(() => (priority ? path : null))

  const url = useBlobUrl(
    requestedPath === path ? () => api.getThumb(path) : null,
    [path, requestedPath],
  )

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

  useEffect(() => {
    setRequestedPath(priority ? path : null)
  }, [path, priority])

  useEffect(() => {
    if (requestedPath === path) return
    if ((inView && !isScrolling) || priority) {
      setRequestedPath(path)
    }
  }, [inView, isScrolling, path, priority, requestedPath])

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

  const cardClassName = [
    'absolute inset-0 bg-surface rounded-[10px] overflow-hidden select-none',
    'border border-border-subtle shadow-sm',
    selected
      ? 'ring-2 ring-accent border-transparent'
      : 'transition-[border-color,box-shadow] duration-150 hover:border-border-strong hover:shadow-md',
    highlighted ? 'thumb-updated-ring' : '',
  ].filter(Boolean).join(' ')

  return (
    <div 
      ref={hostRef} 
      data-highlight-key={highlightKey ?? undefined}
      className={cardClassName}
      onClick={onClick}
    >
      {selectionOrder !== null && (
        <div className="grid-selection-order-badge" aria-label={`Selection order ${selectionOrder}`}>
          {selectionOrder}
        </div>
      )}
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
