import React, { useEffect, useCallback, useRef, useState } from 'react'
import { api } from '../../api/client'
import { useBlobResource } from '../../shared/hooks/useBlobUrl'
import {
  getHorizontalNavigationDelta,
  isInputElement,
  shouldHandleViewerNavigationKey,
} from '../../lib/keyboard'
import { useZoomPan } from './hooks/useZoomPan'
import { directOriginalImageUrl, originalMediaUnsupportedReason } from '../media/originalImageResource'
import { browserDecodeMediaError, mediaErrorSummary, type MediaResourceError } from '../../lib/mediaResourceState'
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

export function getViewerImagePresentation(
  resourcePath: string | null | undefined,
  currentPath: string,
  imageReady: boolean,
): { isCurrent: boolean; isTransitioning: boolean; opacity: number } {
  const isCurrent = resourcePath === currentPath
  const isTransitioning = Boolean(resourcePath && !isCurrent)
  return {
    isCurrent,
    isTransitioning,
    opacity: imageReady ? 1 : (isTransitioning ? 0.42 : 0),
  }
}

export function shouldRenderViewerImageResource(
  resourcePath: string | null | undefined,
  hasBlockingTargetState: boolean,
): boolean {
  return Boolean(resourcePath) && !hasBlockingTargetState
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
  const unsupportedReason = directUrl ? null : originalMediaUnsupportedReason(item)
  const blobResource = useBlobResource(
    directUrl || unsupportedReason ? null : () => api.getFile(path),
    [path, directUrl, unsupportedReason],
    { source: 'proxy', unsupportedReason },
  )
  const blobUrl = blobResource.status === 'ready' ? blobResource.url : null
  const url = directUrl ?? blobUrl
  const resourceIdentity = directUrl ? `${path}\n${directUrl}` : url
  const [elementError, setElementError] = useState<MediaResourceError | null>(null)
  const [imageResource, setImageResource] = useState<ViewerImageResource | null>(null)
  const [readyPath, setReadyPath] = useState<string | null>(null)
  const [showDelayedLoader, setShowDelayedLoader] = useState(false)
  const readyPathRef = useRef<string | null>(null)
  const activeResource = imageResource?.path === path ? imageResource : null
  const loadError = elementError ?? (blobResource.status === 'error' ? blobResource.error : null)
  const retryLoad = blobResource.status === 'error' ? blobResource.retry : null
  const unsupported = blobResource.status === 'unsupported' ? blobResource.reason : null
  const imageReady = ready && readyPath === path && activeResource !== null && !loadError && !unsupported
  const imagePresentation = getViewerImagePresentation(imageResource?.path, path, imageReady)
  const showDisplayedResource = shouldRenderViewerImageResource(
    imageResource?.path,
    Boolean(loadError || unsupported),
  )
  const imageLabel = getImageLabel(path)
  const viewerLoadingState = unsupported ? 'unsupported' : loadError ? 'error' : imageReady ? 'ready' : showDelayedLoader ? 'loading' : 'pending'
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
  const handleImageError = useCallback(() => {
    const resource = activeResource
    const image = imgRef.current
    if (!resource || !image || (image.currentSrc || image.src) !== resource.url) return
    if (directUrl) {
      markDirectImageFailed()
      return
    }
    setElementError(browserDecodeMediaError())
    setShowDelayedLoader(false)
  }, [activeResource, directUrl, imgRef, markDirectImageFailed])
  const retryFailedLoad = useCallback(() => {
    setElementError(null)
    retryLoad?.()
  }, [retryLoad])
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
    setElementError(null)
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
      readyPathRef.current = null
      setReady(false)
      setReadyPath(null)
      return
    }
    setImageResource({ path, url })
    readyPathRef.current = null
    setElementError(null)
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
      {showDelayedLoader && !imageReady && !loadError && !unsupported && (
        <div
          data-viewer-loader="neutral"
          className="absolute inset-0 flex items-center justify-center pointer-events-none"
          aria-hidden="true"
        >
          <div className="h-8 w-8 rounded-full border border-border border-t-accent animate-spin" />
        </div>
      )}
      {(loadError || unsupported) && (
        <div className="media-error-overlay media-error-overlay-viewer">
          <div className="media-error-title">{unsupported ? 'Original unsupported' : 'Image failed'}</div>
          <div className="media-error-message">{unsupported ?? (loadError ? mediaErrorSummary(loadError) : '')}</div>
          {loadError?.retryable && retryLoad && (
            <button type="button" className="btn btn-sm" onClick={retryFailedLoad}>
              Retry
            </button>
          )}
        </div>
      )}
      {showDisplayedResource && imageResource && (
        <img
          ref={imgRef}
          src={imageResource.url}
          alt={`Image viewer: ${imageLabel}`}
          data-viewer-image="full"
          data-current-path={imageResource.path}
          data-viewer-image-current={imagePresentation.isCurrent ? 'true' : 'false'}
          className="max-w-none max-h-none object-contain will-change-transform select-none"
          draggable={false}
          onDragStart={(e)=>{ e.preventDefault() }}
          onLoad={markImageReady}
          onError={handleImageError}
          onClick={(e)=> e.stopPropagation()}
          style={{
            transform: `translate(${tx}px, ${ty}px) scale(${base * scale})`,
            transformOrigin: `0 0`,
            opacity: imagePresentation.opacity,
            filter: imagePresentation.isTransitioning ? 'saturate(0.72)' : undefined,
            transition: 'opacity 120ms ease',
            WebkitUserDrag: 'none',
          } as React.CSSProperties}
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
