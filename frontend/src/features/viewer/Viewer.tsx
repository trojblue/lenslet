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
  key: string
  path: string
  url: string
  source: 'direct' | 'proxy'
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
  resourceKey: string | null | undefined,
  presentedKey: string | null | undefined,
): { isPresented: boolean; opacity: number } {
  const isPresented = Boolean(resourceKey && resourceKey === presentedKey)
  return {
    isPresented,
    opacity: isPresented ? 1 : 0,
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
    prepareImagePromotion,
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
    { source: 'proxy', unsupportedReason, identity: path },
  )
  const blobStateIsCurrent = blobResource.identity === path
  const blobUrl = blobStateIsCurrent && blobResource.status === 'ready' ? blobResource.url : null
  const url = directUrl ?? blobUrl
  const resourceIdentity = url ? `${path}\n${url}` : null
  const [elementError, setElementError] = useState<{ path: string; error: MediaResourceError } | null>(null)
  const [presentedResource, setPresentedResource] = useState<ViewerImageResource | null>(null)
  const [candidateResource, setCandidateResource] = useState<ViewerImageResource | null>(null)
  const [readyPath, setReadyPath] = useState<string | null>(null)
  const [showDelayedLoader, setShowDelayedLoader] = useState(false)
  const requestedPathRef = useRef(path)
  const candidateResourceRef = useRef<ViewerImageResource | null>(null)
  const readyPathRef = useRef<string | null>(null)
  requestedPathRef.current = path
  const targetElementError = elementError?.path === path ? elementError.error : null
  const loadError = targetElementError
    ?? (blobStateIsCurrent && blobResource.status === 'error' ? blobResource.error : null)
  const retryLoad = blobStateIsCurrent && blobResource.status === 'error' ? blobResource.retry : null
  const unsupported = blobStateIsCurrent && blobResource.status === 'unsupported'
    ? blobResource.reason
    : unsupportedReason
  const imageReady = ready && readyPath === path && presentedResource?.path === path && !loadError && !unsupported
  const showDisplayedResource = shouldRenderViewerImageResource(
    presentedResource?.path,
    Boolean(loadError || unsupported),
  )
  const viewerLoadingState = unsupported ? 'unsupported' : loadError ? 'error' : imageReady ? 'ready' : showDelayedLoader ? 'loading' : 'pending'
  const imageResources = presentedResource
    ? [
        presentedResource,
        ...(candidateResource && candidateResource.key !== presentedResource.key ? [candidateResource] : []),
      ]
    : candidateResource ? [candidateResource] : []
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
  const handleImageError = useCallback((resource: ViewerImageResource) => {
    if (candidateResourceRef.current?.key !== resource.key || requestedPathRef.current !== resource.path) return
    candidateResourceRef.current = null
    setCandidateResource(null)
    if (resource.source === 'direct') {
      markDirectImageFailed()
      return
    }
    setElementError({ path: resource.path, error: browserDecodeMediaError() })
    setShowDelayedLoader(false)
  }, [markDirectImageFailed])
  const retryFailedLoad = useCallback(() => {
    setElementError(null)
    retryLoad?.()
  }, [retryLoad])
  const decodeAndPromote = useCallback((image: HTMLImageElement, resource: ViewerImageResource) => {
    void image.decode().then(() => {
      if (
        candidateResourceRef.current?.key !== resource.key
        || requestedPathRef.current !== resource.path
        || !image.isConnected
        || (image.currentSrc || image.src) !== resource.url
      ) return
      if (!prepareImagePromotion(image)) return
      candidateResourceRef.current = null
      readyPathRef.current = resource.path
      imgRef.current = image
      setCandidateResource(null)
      setPresentedResource(resource)
      setReadyPath(resource.path)
      setReady(true)
      setElementError(null)
      setShowDelayedLoader(false)
    }).catch(() => handleImageError(resource))
  }, [handleImageError, imgRef, prepareImagePromotion, setReady])

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
    setElementError(null)
    setShowDelayedLoader(false)
    candidateResourceRef.current = null
    setCandidateResource(null)

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
  }, [path])

  // Stage only a URL tagged with the current request identity. The previously
  // presented node remains independently owned until this candidate decodes.
  useEffect(() => {
    if (!url || !resourceIdentity || targetElementError) return
    const resource: ViewerImageResource = {
      key: resourceIdentity,
      path,
      url,
      source: directUrl ? 'direct' : 'proxy',
    }
    if (presentedResource?.key === resource.key) return
    candidateResourceRef.current = resource
    setCandidateResource(resource)
    setElementError(null)
  }, [directUrl, path, presentedResource?.key, resourceIdentity, targetElementError, url])

  useEffect(() => {
    if (!loadError && !unsupported) return
    candidateResourceRef.current = null
    readyPathRef.current = null
    setCandidateResource(null)
    setPresentedResource(null)
    setReadyPath(null)
    setReady(false)
  }, [loadError, setReady, unsupported])

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
      data-presented-path={presentedResource?.path ?? ''}
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
      {imageResources.map((resource) => {
        const presentation = getViewerImagePresentation(resource.key, presentedResource?.key)
        const displayed = presentation.isPresented && showDisplayedResource
        return (
          <img
            key={resource.key}
            ref={(node) => {
              if (displayed) imgRef.current = node
              else if (!node && imgRef.current?.getAttribute('data-resource-key') === resource.key) {
                imgRef.current = null
              }
            }}
            src={resource.url}
            alt={`Image viewer: ${getImageLabel(resource.path)}`}
            data-viewer-image={displayed ? 'full' : 'candidate'}
            data-current-path={resource.path}
            data-resource-key={resource.key}
            data-viewer-image-current={resource.path === path ? 'true' : 'false'}
            aria-hidden={displayed ? undefined : true}
            className={`${displayed ? '' : 'absolute left-0 top-0 invisible pointer-events-none'} max-w-none max-h-none object-contain will-change-transform select-none`}
            draggable={false}
            onDragStart={(e)=>{ e.preventDefault() }}
            onLoad={(event) => decodeAndPromote(event.currentTarget, resource)}
            onError={() => handleImageError(resource)}
            onClick={(e)=> e.stopPropagation()}
            style={{
              transform: displayed ? `translate(${tx}px, ${ty}px) scale(${base * scale})` : undefined,
              transformOrigin: `0 0`,
              opacity: displayed ? presentation.opacity : 0,
              WebkitUserDrag: 'none',
            } as React.CSSProperties}
          />
        )
      })}
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
