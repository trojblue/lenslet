import React, { useEffect, useState, useCallback } from 'react'
import { api } from '../../shared/api/client'
import { useZoomPan } from './hooks/useZoomPan'

interface ViewerProps {
  path: string
  onClose: () => void
  onNavigate?: (delta: number) => void
  onZoomChange?: (percent: number) => void
  requestedZoomPercent?: number | null
  onZoomRequestConsumed?: () => void
}

export default function Viewer({
  path,
  onClose,
  onNavigate,
  onZoomChange,
  requestedZoomPercent,
  onZoomRequestConsumed,
}: ViewerProps) {
  const [url, setUrl] = useState<string | null>(null)
  const [thumbUrl, setThumbUrl] = useState<string | null>(null)
  const { scale, setScale, tx, setTx, ty, setTy, base, setBase, ready, setReady, dragging, visible, setVisible, containerRef, imgRef, fitAndCenter, handleWheel, handleMouseDown } = useZoomPan()

  // Load image and thumbnail when path changes
  useEffect(() => {
    let alive = true
    
    // Load full image
    api.getFile(path)
      .then((b) => {
        if (!alive) return
        setUrl(URL.createObjectURL(b))
      })
      .catch(() => {})
    
    // Load thumbnail for low-res preview
    api.getThumb(path)
      .then((b) => {
        if (!alive) return
        setThumbUrl(URL.createObjectURL(b))
      })
      .catch(() => {})
    
    // Fade in and focus
    requestAnimationFrame(() => {
      setVisible(true)
      containerRef.current?.focus()
    })
    
    return () => {
      alive = false
    }
  }, [path])

  // Keyboard navigation
  useEffect(() => {
    const onKey = (e: KeyboardEvent) => {
      if (e.key === 'Escape') {
        setVisible(false)
        setTimeout(onClose, 110)
      } else if ((e.key === 'ArrowRight' || e.key === 'd') && onNavigate) {
        onNavigate(1)
      } else if ((e.key === 'ArrowLeft' || e.key === 'a') && onNavigate) {
        onNavigate(-1)
      }
    }
    
    window.addEventListener('keydown', onKey)
    return () => window.removeEventListener('keydown', onKey)
  }, [onClose, onNavigate])

  // Clean up blob URLs
  useEffect(() => {
    return () => {
      if (url) URL.revokeObjectURL(url)
    }
  }, [url])
  
  useEffect(() => {
    return () => {
      if (thumbUrl) URL.revokeObjectURL(thumbUrl)
    }
  }, [thumbUrl])
  
  // Reset ready state when URL changes
  useEffect(() => {
    setReady(false)
  }, [url])

  // resize observer moved into hook

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
      tabIndex={-1}
      className={`absolute inset-0 top-12 left-[var(--left)] right-[var(--right)] flex items-start justify-start bg-panel z-viewer overflow-hidden transition-opacity duration-[110ms] ease-out cursor-grab focus:outline-none focus-visible:outline-none ${dragging ? 'cursor-grabbing select-none' : ''} ${visible ? 'opacity-100' : 'opacity-0'}`}
      style={{ outline: 'none' }}
      onClick={() => { setVisible(false); window.setTimeout(() => onClose(), 110) }}
      onWheel={handleWheel}
      onMouseDown={handleMouseDown}
      onKeyDown={(e)=>{ if (e.key === 'Tab') { e.preventDefault() } }}
    >
      <button
        aria-label="Close"
        onClick={(e)=>{ e.stopPropagation(); setVisible(false); window.setTimeout(() => onClose(), 110) }}
        className="btn absolute top-3 right-3 z-10"
      >
        ✕ Close
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
          className="max-w-none max-h-none object-contain transition-opacity duration-[110ms] ease-out will-change-transform select-none"
          draggable={false}
          onDragStart={(e)=>{ e.preventDefault() }}
          onLoad={(ev)=>{ fitAndCenter(); setScale(1); try { requestAnimationFrame(()=> setReady(true)) } catch { setReady(true) } }}
          onClick={(e)=> e.stopPropagation()}
          style={{ transform: `translate(${tx}px, ${ty}px) scale(${base * scale})`, transformOrigin: `0 0`, opacity: ready ? 0.99 : 0, WebkitUserDrag: 'none' } as React.CSSProperties}
        />
      )}
    </div>
  )
}
