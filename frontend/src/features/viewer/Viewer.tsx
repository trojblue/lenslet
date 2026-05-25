import React, { useEffect, useCallback, useRef, useState } from 'react'
import { api } from '../../api/client'
import { useBlobUrl } from '../../shared/hooks/useBlobUrl'
import { useModalFocusTrap } from '../../shared/hooks/useModalFocusTrap'
import { useZoomPan } from './hooks/useZoomPan'

interface ViewerProps {
  path: string
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
    setScale,
    tx,
    setTx,
    ty,
    setTy,
    base,
    ready,
    setReady,
    dragging,
    visible,
    setVisible,
    containerRef,
    imgRef,
    resetView,
    handleWheel,
    handlePointerDown,
    handlePointerMove,
    handlePointerUp,
    handlePointerCancel,
    consumeClickSuppression,
  } = useZoomPan()
  const url = useBlobUrl(() => api.getFile(path), [path])
  const thumbUrl = useBlobUrl(() => api.getThumb(path), [path])
  const [loadedPath, setLoadedPath] = useState<string | null>(null)
  const urlPathRef = useRef<string | null>(null)
  const closeViewer = useCallback(() => {
    setVisible(false)
    window.setTimeout(onClose, 110)
  }, [onClose, setVisible])
  const handleClickCapture = useCallback((event: React.MouseEvent<HTMLDivElement>) => {
    if (!consumeClickSuppression()) return
    event.preventDefault()
    event.stopPropagation()
  }, [consumeClickSuppression])
  const handleBackdropClick = useCallback((event: React.MouseEvent<HTMLDivElement>) => {
    if (event.target !== event.currentTarget) return
    closeViewer()
  }, [closeViewer])
  const handleDialogKeyDown = useModalFocusTrap(containerRef, { onEscape: closeViewer })
  const markImageReady = useCallback(() => {
    const image = imgRef.current
    if (!url || urlPathRef.current !== path || !image || (image.currentSrc || image.src) !== url) return
    resetView()
    setLoadedPath(path)
    try {
      requestAnimationFrame(() => setReady(true))
    } catch {
      setReady(true)
    }
  }, [imgRef, path, resetView, setReady, url])

  // Load image and thumbnail when path changes
  useEffect(() => {
    // Fade in after the overlay mounts.
    requestAnimationFrame(() => {
      setVisible(true)
    })
  }, [path])

  // Keyboard navigation
  useEffect(() => {
    const onKey = (e: KeyboardEvent) => {
      const normalized = e.key.toLowerCase()
      if ((e.key === 'ArrowRight' || normalized === 'd') && onNavigate) {
        e.preventDefault()
        onNavigate(1)
      } else if ((e.key === 'ArrowLeft' || normalized === 'a') && onNavigate) {
        e.preventDefault()
        onNavigate(-1)
      }
    }

    window.addEventListener('keydown', onKey)
    return () => window.removeEventListener('keydown', onKey)
  }, [onNavigate])

  useEffect(() => {
    setReady(false)
    setLoadedPath(null)
  }, [path, setReady])

  // Reconcile cached/completed image loads with the URL-change readiness reset.
  useEffect(() => {
    if (!url) {
      urlPathRef.current = null
      setReady(false)
      setLoadedPath(null)
      return
    }
    urlPathRef.current = path
    const image = imgRef.current
    if (image?.complete && image.naturalWidth > 0) {
      markImageReady()
      return
    }
    setReady(false)
  // URL changes bind the blob URL to the current path; path-only renders with
  // the previous URL must stay hidden until a new URL arrives.
  // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [url])

  useEffect(() => { if (onZoomChange) onZoomChange((base * scale) * 100) }, [base, scale, onZoomChange])

  useEffect(() => {
    if (requestedZoomPercent == null) return
    const cont = containerRef.current
    if (!cont) { onZoomRequestConsumed && onZoomRequestConsumed(); return }
    const targetScale = Math.max(0.05, Math.min(8, (requestedZoomPercent / 100) / Math.max(1e-6, base)))
    const rect = cont.getBoundingClientRect()
    const cx = rect.width / 2
    const cy = rect.height / 2
    setScale(s => {
      const ratio = targetScale / s
      setTx(prevTx => cx - ratio * (cx - prevTx))
      setTy(prevTy => cy - ratio * (cy - prevTy))
      return Number(targetScale.toFixed(4))
    })
    onZoomRequestConsumed && onZoomRequestConsumed()
  }, [requestedZoomPercent, base, onZoomRequestConsumed])

  return (
    <div
      ref={containerRef}
      role="dialog"
      aria-modal={true}
      aria-label="Image viewer"
      data-current-path={path}
      tabIndex={-1}
      className={`toolbar-offset touch-none absolute inset-0 left-[var(--overlay-left)] right-[var(--overlay-right)] flex items-start justify-start bg-panel z-viewer overflow-hidden transition-opacity duration-[110ms] ease-out cursor-grab focus:outline-none focus-visible:outline-none ${dragging ? 'cursor-grabbing select-none' : ''} ${visible ? 'opacity-100' : 'opacity-0'}`}
      style={{ outline: 'none' }}
      onClickCapture={handleClickCapture}
      onClick={handleBackdropClick}
      onWheel={handleWheel}
      onPointerDown={handlePointerDown}
      onPointerMove={handlePointerMove}
      onPointerUp={handlePointerUp}
      onPointerCancel={handlePointerCancel}
      onKeyDown={handleDialogKeyDown}
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
      {thumbUrl && (
        <img
          src={thumbUrl}
          alt="thumb"
          className="absolute top-0 left-0 max-w-none max-h-none object-contain pointer-events-none transition-opacity duration-[110ms] ease-out"
          draggable={false}
          onDragStart={(e)=> e.preventDefault()}
          style={{ transform: `translate(${tx}px, ${ty}px) scale(${base})`, transformOrigin: `0 0`, opacity: ready ? 0 : 0.5, filter: 'blur(0.25px)' }}
        />
      )}
      {url && (
        <img
          ref={imgRef}
          src={url}
          alt="viewer"
          data-current-path={loadedPath ?? undefined}
          className="max-w-none max-h-none object-contain transition-opacity duration-[110ms] ease-out will-change-transform select-none"
          draggable={false}
          onDragStart={(e)=>{ e.preventDefault() }}
          onLoad={markImageReady}
          onClick={(e)=> e.stopPropagation()}
          style={{ transform: `translate(${tx}px, ${ty}px) scale(${base * scale})`, transformOrigin: `0 0`, opacity: ready ? 0.99 : 0, WebkitUserDrag: 'none' } as React.CSSProperties}
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
