import React, { useEffect, useCallback, useRef, useState } from 'react'
import { api } from '../../api/client'
import { useBlobUrl } from '../../shared/hooks/useBlobUrl'
import {
  getHorizontalNavigationDelta,
  isInputElement,
  shouldHandleViewerNavigationKey,
} from '../../lib/keyboard'
import { useZoomPan } from './hooks/useZoomPan'
import { directOriginalImageUrl } from '../media/originalImageResource'
import type { BrowseItemPayload } from '../../lib/types'

const VIEWER_LOADER_DELAY_MS = 150

type ViewerImageResource = {
  path: string
  url: string
}

function isViewerControlTarget(target: EventTarget | null): boolean {
  return target instanceof Element
    && target.closest('button, a, input, select, textarea, [role="button"]') !== null
}

function getImageLabel(path: string): string {
  const label = path.split(/[\\/]/).filter(Boolean).pop()
  return label || path
}

interface ViewerProps {
  path: string
  item?: BrowseItemPayload | null
  proxyHttpOriginals?: boolean
  onClose: () => void
  onNavigate?: (delta: number) => void
  canPrev?: boolean
  canNext?: boolean
  onZoomChange?: (percent: number) => void
  requestedZoomPercent?: number | null
  onZoomRequestConsumed?: () => void
}

export default function Viewer({
  path,
  item = null,
  proxyHttpOriginals = false,
  onClose,
  onNavigate,
  canPrev = false,
  canNext = false,
  onZoomChange,
  requestedZoomPercent,
  onZoomRequestConsumed,
}: ViewerProps) {
  const {
    scale,
    tx,
    ty,
    base,
    geometryVersion,
    ready,
    setReady,
    dragging,
    containerRef,
    imgRef,
    resetView,
    zoomToPercent,
    handleWheel,
    handlePointerDown,
    handlePointerMove,
    handlePointerUp,
    handlePointerCancel,
    shouldSuppressSurfaceClick,
  } = useZoomPan()
  const [directFailures, setDirectFailures] = useState<Set<string>>(() => new Set())
  const directUrl = directOriginalImageUrl(item, proxyHttpOriginals, directFailures)
  const blobUrl = useBlobUrl(directUrl ? null : () => api.getFile(path), [path, directUrl])
  const url = directUrl ?? blobUrl
  const resourceIdentity = directUrl ? `${path}\n${directUrl}` : url
  const [imageResource, setImageResource] = useState<ViewerImageResource | null>(null)
  const [readyPath, setReadyPath] = useState<string | null>(null)
  const [showDelayedLoader, setShowDelayedLoader] = useState(false)
  const readyPathRef = useRef<string | null>(null)
  const activeResource = imageResource?.path === path ? imageResource : null
  const imageReady = ready && readyPath === path && activeResource !== null
  const imageLabel = getImageLabel(path)
  const viewerLoadingState = imageReady ? 'ready' : showDelayedLoader ? 'loading' : 'pending'
  const closeViewer = useCallback(() => {
    onClose()
  }, [onClose])
  const handleClickCapture = useCallback((event: React.MouseEvent<HTMLDivElement>) => {
    if (!shouldSuppressSurfaceClick()) return
    if (isViewerControlTarget(event.target)) return
    event.preventDefault()
    event.stopPropagation()
  }, [shouldSuppressSurfaceClick])
  const handleSurfaceDoubleClick = useCallback((event: React.MouseEvent<HTMLDivElement>) => {
    if (shouldSuppressSurfaceClick() || isViewerControlTarget(event.target)) {
      event.preventDefault()
      event.stopPropagation()
      return
    }
    event.preventDefault()
    event.stopPropagation()
    closeViewer()
  }, [closeViewer, shouldSuppressSurfaceClick])
  const markDirectImageFailed = useCallback(() => {
    if (!directUrl) return
    setDirectFailures((prev) => {
      if (prev.has(path)) return prev
      const next = new Set(prev)
      next.add(path)
      return next
    })
  }, [directUrl, path])
  const markImageReady = useCallback(() => {
    const resource = activeResource
    const image = imgRef.current
    if (!resource || resource.path !== path || !image || (image.currentSrc || image.src) !== resource.url) return
    if (readyPathRef.current === resource.path) return
    resetView()
    readyPathRef.current = resource.path
    setReadyPath(resource.path)
    setReady(true)
    setShowDelayedLoader(false)
  }, [activeResource, imgRef, path, resetView, setReady])

  useEffect(() => {
    const onKey = (e: KeyboardEvent) => {
      if (e.key === 'Escape' && !isInputElement(e.target)) {
        e.preventDefault()
        closeViewer()
        return
      }
      if (!onNavigate || !shouldHandleViewerNavigationKey(e)) return
      const delta = getHorizontalNavigationDelta(e)
      if (delta === 1 && canNext) {
        e.preventDefault()
        onNavigate(delta)
      } else if (delta === -1 && canPrev) {
        e.preventDefault()
        onNavigate(delta)
      }
    }

    window.addEventListener('keydown', onKey)
    return () => window.removeEventListener('keydown', onKey)
  }, [canNext, canPrev, closeViewer, onNavigate])

  useEffect(() => {
    readyPathRef.current = null
    setReady(false)
    setReadyPath(null)
    setImageResource(null)
    setShowDelayedLoader(false)

    let active = true
    const timeoutId = window.setTimeout(() => {
      if (active && readyPathRef.current !== path) {
        setShowDelayedLoader(true)
      }
    }, VIEWER_LOADER_DELAY_MS)

    return () => {
      active = false
      window.clearTimeout(timeoutId)
    }
  }, [path, setReady])

  // useBlobUrl preserves the previous URL while the next path fetch is in
  // flight. Only a URL change may bind a blob URL to the current viewer path.
  useEffect(() => {
    if (!url) {
      setImageResource(null)
      readyPathRef.current = null
      setReady(false)
      setReadyPath(null)
      return
    }
    setImageResource({ path, url })
    readyPathRef.current = null
    setReady(false)
    setReadyPath(null)
  // URL changes bind the blob URL to the current path; path-only renders with
  // the previous URL must not rebind or render that stale resource.
  // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [resourceIdentity])

  useEffect(() => {
    if (!activeResource) return
    const image = imgRef.current
    if (image?.complete && image.naturalWidth > 0) {
      markImageReady()
    }
  }, [activeResource, markImageReady])

  useEffect(() => { if (onZoomChange) onZoomChange((base * scale) * 100) }, [base, scale, onZoomChange])

  useEffect(() => {
    if (requestedZoomPercent == null) return
    if (!imageReady) return
    if (zoomToPercent(requestedZoomPercent)) {
      onZoomRequestConsumed && onZoomRequestConsumed()
    }
  }, [geometryVersion, imageReady, requestedZoomPercent, onZoomRequestConsumed, zoomToPercent])

  return (
    <div
      ref={containerRef}
      role="dialog"
      aria-modal={false}
      aria-label="Image viewer"
      data-current-path={path}
      data-viewer-loading-state={viewerLoadingState}
      aria-busy={imageReady ? undefined : true}
      tabIndex={-1}
      className={`toolbar-offset touch-none absolute inset-0 left-[var(--overlay-left)] right-[var(--overlay-right)] flex items-start justify-start bg-panel z-viewer overflow-hidden cursor-grab ${dragging ? 'cursor-grabbing select-none' : ''}`}
      onClickCapture={handleClickCapture}
      onDoubleClick={handleSurfaceDoubleClick}
      onWheel={handleWheel}
      onPointerDown={handlePointerDown}
      onPointerMove={handlePointerMove}
      onPointerUp={handlePointerUp}
      onPointerCancel={handlePointerCancel}
    >
      <button
        aria-label="Close"
        onClick={(e)=>{ e.stopPropagation(); closeViewer() }}
        className="btn btn-sm absolute top-3 right-3 z-10"
        title="Close (Esc)"
      >
        <svg width="12" height="12" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round" aria-hidden="true">
          <path d="M18 6 6 18" />
          <path d="M6 6l12 12" />
        </svg>
        Close
      </button>
      {showDelayedLoader && !imageReady && (
        <div
          data-viewer-loader="neutral"
          className="absolute inset-0 flex items-center justify-center pointer-events-none"
          aria-hidden="true"
        >
          <div className="h-8 w-8 rounded-full border border-border border-t-accent animate-spin" />
        </div>
      )}
      {activeResource && (
        <img
          ref={imgRef}
          src={activeResource.url}
          alt={`Image viewer: ${imageLabel}`}
          data-viewer-image="full"
          data-current-path={activeResource.path}
          className="max-w-none max-h-none object-contain will-change-transform select-none"
          draggable={false}
          onDragStart={(e)=>{ e.preventDefault() }}
          onLoad={markImageReady}
          onError={markDirectImageFailed}
          onClick={(e)=> e.stopPropagation()}
          style={{ transform: `translate(${tx}px, ${ty}px) scale(${base * scale})`, transformOrigin: `0 0`, opacity: imageReady ? 1 : 0, WebkitUserDrag: 'none' } as React.CSSProperties}
        />
      )}
      {onNavigate && (
        <div className="viewer-mobile-nav" onClick={(e) => e.stopPropagation()}>
          <button
            type="button"
            className={`viewer-mobile-nav-btn ${canPrev ? '' : 'is-disabled'}`}
            onClick={() => canPrev && onNavigate(-1)}
            aria-label="Previous image"
            aria-disabled={!canPrev}
            disabled={!canPrev}
          >
            Prev
          </button>
          <button
            type="button"
            className={`viewer-mobile-nav-btn ${canNext ? '' : 'is-disabled'}`}
            onClick={() => canNext && onNavigate(1)}
            aria-label="Next image"
            aria-disabled={!canNext}
            disabled={!canNext}
          >
            Next
          </button>
        </div>
      )}
    </div>
  )
}
