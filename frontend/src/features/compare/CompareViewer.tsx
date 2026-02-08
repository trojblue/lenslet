import React, { useCallback, useEffect, useRef, useState } from 'react'
import { api } from '../../shared/api/client'
import { useBlobUrl } from '../../shared/hooks/useBlobUrl'
import { isInputElement } from '../../lib/keyboard'
import type { Item } from '../../lib/types'
import { useCompareZoomPan } from './hooks/useCompareZoomPan'

interface CompareViewerProps {
  aItem: Item | null
  bItem: Item | null
  index: number
  total: number
  canPrev: boolean
  canNext: boolean
  onNavigate: (delta: number) => void
  onClose: () => void
}

export default function CompareViewer({
  aItem,
  bItem,
  index,
  total,
  canPrev,
  canNext,
  onNavigate,
  onClose,
}: CompareViewerProps) {
  const overlayRef = useRef<HTMLDivElement | null>(null)
  const [splitPct, setSplitPct] = useState(50)
  const [readyA, setReadyA] = useState(false)
  const [readyB, setReadyB] = useState(false)
  const {
    scale,
    baseA,
    baseB,
    txA,
    tyA,
    txB,
    tyB,
    dragging,
    containerRef,
    imgARef,
    imgBRef,
    fitAndCenter,
    resetView,
    handleWheel,
    handlePointerDown,
    handlePointerMove,
    handlePointerUp,
    handlePointerCancel,
  } = useCompareZoomPan()

  const aPath = aItem?.path ?? null
  const bPath = bItem?.path ?? null
  const aLabel = aItem?.name ?? aPath ?? 'Select an image'
  const bLabel = bItem?.name ?? bPath ?? 'Select another image'

  useEffect(() => {
    requestAnimationFrame(() => overlayRef.current?.focus())
  }, [aPath, bPath])

  useEffect(() => {
    resetView()
    setReadyA(false)
    setReadyB(false)
  }, [aPath, bPath, resetView])

  useEffect(() => {
    const onKey = (e: KeyboardEvent) => {
      if (isInputElement(e.target)) return
      if (e.key === 'Escape') {
        e.preventDefault()
        onClose()
        return
      }
      if ((e.key === 'ArrowRight' || e.key === 'd') && canNext) {
        e.preventDefault()
        onNavigate(1)
        return
      }
      if ((e.key === 'ArrowLeft' || e.key === 'a') && canPrev) {
        e.preventDefault()
        onNavigate(-1)
      }
    }

    window.addEventListener('keydown', onKey)
    return () => window.removeEventListener('keydown', onKey)
  }, [onClose, onNavigate, canPrev, canNext])

  const aUrl = useBlobUrl(aPath ? () => api.getFile(aPath) : null, [aPath])
  const bUrl = useBlobUrl(bPath ? () => api.getFile(bPath) : null, [bPath])
  const aThumb = useBlobUrl(aPath ? () => api.getThumb(aPath) : null, [aPath])
  const bThumb = useBlobUrl(bPath ? () => api.getThumb(bPath) : null, [bPath])

  const clampSplit = useCallback((value: number) => Math.min(95, Math.max(5, value)), [])

  const handleStagePointerDown = useCallback((e: React.PointerEvent<HTMLDivElement>) => {
    const target = e.target as HTMLElement | null
    if (target?.closest('.compare-label') || target?.closest('.compare-divider-hit')) return
    handlePointerDown(e)
  }, [handlePointerDown])

  const handleDividerPointerDown = useCallback((e: React.PointerEvent<HTMLDivElement>) => {
    const stage = containerRef.current
    if (!stage) return
    e.preventDefault()
    e.stopPropagation()
    const rect = stage.getBoundingClientRect()
    const target = e.currentTarget
    target.setPointerCapture(e.pointerId)
    const onMove = (ev: PointerEvent) => {
      const pct = ((ev.clientX - rect.left) / rect.width) * 100
      setSplitPct(clampSplit(pct))
    }
    const onUp = (ev: PointerEvent) => {
      try {
        target.releasePointerCapture(ev.pointerId)
      } catch {
        // Ignore unsupported capture release.
      }
      window.removeEventListener('pointermove', onMove)
      window.removeEventListener('pointerup', onUp)
      window.removeEventListener('pointercancel', onUp)
    }
    window.addEventListener('pointermove', onMove)
    window.addEventListener('pointerup', onUp)
    window.addEventListener('pointercancel', onUp)
  }, [clampSplit])

  return (
    <div
      ref={overlayRef}
      role="dialog"
      aria-modal={true}
      aria-label="Compare images"
      tabIndex={-1}
      className="toolbar-offset absolute inset-0 left-[var(--left)] right-[var(--right)] bg-panel z-viewer flex flex-col overflow-hidden focus:outline-none"
      onKeyDown={(e)=>{ if (e.key === 'Tab') e.preventDefault() }}
    >
      <div className="compare-header flex items-center gap-3 px-3 py-2">
        <div className="text-[11px] uppercase tracking-wide text-muted">Compare</div>
        <div className="text-xs text-muted">
          {total >= 2 ? `${index + 1}-${Math.min(index + 2, total)} of ${total}` : 'Select 2 images'}
        </div>
        <div className="ml-auto flex items-center gap-2">
          <button className="btn btn-sm" onClick={() => onNavigate(-1)} disabled={!canPrev} title="Previous (Left Arrow or A)">
            <svg width="12" height="12" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round" aria-hidden="true">
              <path d="M15 18l-6-6 6-6" />
            </svg>
            Prev
          </button>
          <button className="btn btn-sm" onClick={() => onNavigate(1)} disabled={!canNext} title="Next (Right Arrow or D)">
            Next
            <svg width="12" height="12" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round" aria-hidden="true">
              <path d="M9 18l6-6-6-6" />
            </svg>
          </button>
          <button className="btn btn-sm" onClick={onClose} title="Close (Esc)">
            <svg width="12" height="12" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round" aria-hidden="true">
              <path d="M18 6 6 18" />
              <path d="M6 6l12 12" />
            </svg>
            Close
          </button>
        </div>
      </div>
      <div className="flex-1 min-h-0 p-3 bg-panel">
        <div
          ref={containerRef}
          className={`compare-stage ${dragging ? 'is-dragging' : ''}`}
          onWheel={handleWheel}
          onPointerDown={handleStagePointerDown}
          onPointerMove={handlePointerMove}
          onPointerUp={handlePointerUp}
          onPointerCancel={handlePointerCancel}
        >
          {!aItem || !bItem ? (
            <div className="absolute inset-0 flex items-center justify-center text-sm text-muted">
              Select 2 images to compare.
            </div>
          ) : (
            <>
              <div className="compare-label left-3">
                <span className="compare-label-tag">A</span>
                <span className="truncate" title={aItem.path}>{aLabel}</span>
              </div>
              <div className="compare-label right-3">
                <span className="compare-label-tag">B</span>
                <span className="truncate" title={bItem.path}>{bLabel}</span>
              </div>
              <div className="compare-layer" style={{ clipPath: `inset(0 ${100 - splitPct}% 0 0)` }}>
                {aThumb && (
                  <img
                    src={aThumb}
                    alt="thumb A"
                    className="compare-image compare-image-thumb"
                    draggable={false}
                    onDragStart={(e)=> e.preventDefault()}
                    style={{ transform: `translate(${txA}px, ${tyA}px) scale(${baseA})`, transformOrigin: '0 0', opacity: readyA ? 0 : 0.5 }}
                  />
                )}
                {aUrl && (
                  <img
                    ref={imgARef}
                    src={aUrl}
                    alt="compare A"
                    className="compare-image"
                    draggable={false}
                    onDragStart={(e)=> e.preventDefault()}
                    onLoad={() => {
                      fitAndCenter()
                      try { requestAnimationFrame(() => setReadyA(true)) } catch { setReadyA(true) }
                    }}
                    style={{ transform: `translate(${txA}px, ${tyA}px) scale(${baseA * scale})`, transformOrigin: '0 0', opacity: readyA ? 0.99 : 0 }}
                  />
                )}
              </div>
              <div className="compare-layer" style={{ clipPath: `inset(0 0 0 ${splitPct}%)` }}>
                {bThumb && (
                  <img
                    src={bThumb}
                    alt="thumb B"
                    className="compare-image compare-image-thumb"
                    draggable={false}
                    onDragStart={(e)=> e.preventDefault()}
                    style={{ transform: `translate(${txB}px, ${tyB}px) scale(${baseB})`, transformOrigin: '0 0', opacity: readyB ? 0 : 0.5 }}
                  />
                )}
                {bUrl && (
                  <img
                    ref={imgBRef}
                    src={bUrl}
                    alt="compare B"
                    className="compare-image"
                    draggable={false}
                    onDragStart={(e)=> e.preventDefault()}
                    onLoad={() => {
                      fitAndCenter()
                      try { requestAnimationFrame(() => setReadyB(true)) } catch { setReadyB(true) }
                    }}
                    style={{ transform: `translate(${txB}px, ${tyB}px) scale(${baseB * scale})`, transformOrigin: '0 0', opacity: readyB ? 0.99 : 0 }}
                  />
                )}
              </div>
              <div
                className="compare-divider-hit"
                style={{ left: `${splitPct}%` }}
                onPointerDown={handleDividerPointerDown}
              >
                <div className="compare-divider-line" />
                <div className="compare-divider-handle" />
              </div>
            </>
          )}
        </div>
      </div>
    </div>
  )
}
