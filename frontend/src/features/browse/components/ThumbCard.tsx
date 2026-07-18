import React, { useCallback, useEffect, useRef, useState } from 'react'
import { markFirstThumbnailRendered } from '../../../lib/browseHotpath'
import { mediaErrorSummary } from '../../../lib/mediaResourceState'
import { useThumbnailResource } from '../hooks/useThumbnailResource'
import { decodeThumbnailBeforeReveal } from '../model/thumbnailReveal'

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
  fit?: 'contain'
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
  fit,
  ioRoot,
  isScrolling,
  priority,
}: ThumbCardProps) {
  const hostRef = useRef<HTMLDivElement>(null)
  const [inView, setInView] = useState(false)
  const [loaded, setLoaded] = useState(false)
  const [requestedPath, setRequestedPath] = useState<string | null>(() => (priority ? path : null))

  const resource = useThumbnailResource(path, requestedPath === path)
  const url = resource.status === 'ready' ? resource.url : null
  const decoded = resource.status === 'ready' ? resource.decoded : false
  const imageVisible = loaded || decoded
  const markDecoded = resource.status === 'ready' ? resource.markDecoded : null
  const error = resource.status === 'error' ? resource.error : null
  const retry = resource.status === 'error' ? resource.retry : null
  const revealDecodedImage = useCallback((image: HTMLImageElement) => {
    void decodeThumbnailBeforeReveal(image)
      .catch(() => undefined)
      .then(() => {
        if (!hostRef.current?.contains(image)) return
        if ((image.currentSrc || image.src) !== url) return
        setLoaded(true)
        markDecoded?.()
        markFirstThumbnailRendered(path)
      })
  }, [markDecoded, path, url])

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

  useEffect(() => {
    if (!url) {
      setLoaded(false)
      return
    }

    if (decoded) {
      setLoaded(true)
      markFirstThumbnailRendered(path)
      return
    }

    // Cached network bytes still wait for browser decode before the card reveals them.
    const imgEl = hostRef.current?.querySelector('img') as HTMLImageElement | null
    if (imgEl && imgEl.complete && imgEl.naturalWidth > 0) {
      revealDecodedImage(imgEl)
    } else {
      setLoaded(false)
    }
  }, [decoded, path, revealDecodedImage, url])

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
      data-media-state={resource.status}
    >
      {selectionOrder !== null && (
        <div className="grid-selection-order-badge" aria-label={`Selection order ${selectionOrder}`}>
          {selectionOrder}
        </div>
      )}
      {url ? (
        <img
          className={`w-full h-full ${fit === 'contain' ? 'object-contain' : 'object-cover'} block pointer-events-none select-none opacity-0 transition-opacity duration-[160ms] ${imageVisible ? 'opacity-100' : ''}`}
          src={url}
          alt={name}
          loading="lazy"
          decoding="async"
          data-thumbnail-reveal={imageVisible ? 'decoded' : 'pending'}
          onLoad={(event) => revealDecodedImage(event.currentTarget)}
          width={displayW ? Math.round(displayW) : undefined}
          height={displayH ? Math.round(displayH) : undefined}
        />
      ) : null}
      {error && (
        <div className="media-error-overlay media-error-overlay-thumb" onClick={(event) => event.stopPropagation()}>
          <div className="media-error-title">Thumbnail failed</div>
          <div className="media-error-message">{mediaErrorSummary(error)}</div>
          {error.retryable && retry && (
            <button
              type="button"
              className="btn btn-xs"
              onClick={(event) => {
                event.preventDefault()
                event.stopPropagation()
                retry()
              }}
            >
              Retry
            </button>
          )}
        </div>
      )}
    </div>
  )
}
