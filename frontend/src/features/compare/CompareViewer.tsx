import React, { useCallback, useEffect, useRef, useState } from 'react'
import { api } from '../../api/client'
import { useBlobUrl } from '../../shared/hooks/useBlobUrl'
import { useModalFocusTrap } from '../../shared/hooks/useModalFocusTrap'
import { getHorizontalNavigationDelta, shouldHandleDialogNavigationKey } from '../../lib/keyboard'
import type { BrowseItemPayload } from '../../lib/types'
import { buildComparePairKey, shouldAutoFitComparePair } from './compareAutoFit'
import { useCompareZoomPan } from './hooks/useCompareZoomPan'

interface CompareViewerProps {
  aItem: BrowseItemPayload | null
  bItem: BrowseItemPayload | null
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
  const [loadedAPath, setLoadedAPath] = useState<string | null>(null)
  const [loadedBPath, setLoadedBPath] = useState<string | null>(null)
  const aUrlPathRef = useRef<string | null>(null)
  const bUrlPathRef = useRef<string | null>(null)
  const fittedPairKeyRef = useRef<string | null>(null)
  const userInteractedPairKeyRef = useRef<string | null>(null)
  const aPath = aItem?.path ?? null
  const bPath = bItem?.path ?? null
  const pairKey = buildComparePairKey(aPath, bPath)
  const markCompareUserInteraction = useCallback(() => {
    userInteractedPairKeyRef.current = pairKey
  }, [pairKey])
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
  } = useCompareZoomPan({ onUserInteraction: markCompareUserInteraction })

  const aLabel = aItem?.name ?? aPath ?? 'Select an image'
  const bLabel = bItem?.name ?? bPath ?? 'Select another image'
  const handleDialogKeyDown = useModalFocusTrap(overlayRef, { onEscape: onClose })

  useEffect(() => {
    resetView()
    setReadyA(false)
    setReadyB(false)
    setLoadedAPath(null)
    setLoadedBPath(null)
    fittedPairKeyRef.current = null
    userInteractedPairKeyRef.current = null
  }, [aPath, bPath, resetView])

  useEffect(() => {
    const onKey = (e: KeyboardEvent) => {
      if (!shouldHandleDialogNavigationKey(e, overlayRef.current)) return
      const delta = getHorizontalNavigationDelta(e)
      if (delta === 1 && canNext) {
        e.preventDefault()
        onNavigate(delta)
        return
      }
      if (delta === -1 && canPrev) {
        e.preventDefault()
        onNavigate(delta)
      }
    }

    window.addEventListener('keydown', onKey)
    return () => window.removeEventListener('keydown', onKey)
  }, [onNavigate, canPrev, canNext])

  const aUrl = useBlobUrl(aPath ? () => api.getFile(aPath) : null, [aPath])
  const bUrl = useBlobUrl(bPath ? () => api.getFile(bPath) : null, [bPath])
  const aThumb = useBlobUrl(aPath ? () => api.getThumb(aPath) : null, [aPath])
  const bThumb = useBlobUrl(bPath ? () => api.getThumb(bPath) : null, [bPath])
  const markImageAReady = useCallback(() => {
    const image = imgARef.current
    if (!aPath || !aUrl || aUrlPathRef.current !== aPath || !image || (image.currentSrc || image.src) !== aUrl) {
      return
    }
    setLoadedAPath(aPath)
    try {
      requestAnimationFrame(() => setReadyA(true))
    } catch {
      setReadyA(true)
    }
  }, [aPath, aUrl, imgARef])
  const markImageBReady = useCallback(() => {
    const image = imgBRef.current
    if (!bPath || !bUrl || bUrlPathRef.current !== bPath || !image || (image.currentSrc || image.src) !== bUrl) {
      return
    }
    setLoadedBPath(bPath)
    try {
      requestAnimationFrame(() => setReadyB(true))
    } catch {
      setReadyB(true)
    }
  }, [bPath, bUrl, imgBRef])

  useEffect(() => {
    if (!shouldAutoFitComparePair({
      aPath,
      bPath,
      loadedAPath,
      loadedBPath,
      fittedPairKey: fittedPairKeyRef.current,
      userInteracted: userInteractedPairKeyRef.current === pairKey,
    })) return
    if (fitAndCenter()) {
      fittedPairKeyRef.current = pairKey
    }
  }, [aPath, bPath, fitAndCenter, loadedAPath, loadedBPath, pairKey])

  useEffect(() => {
    if (!aUrl) {
      aUrlPathRef.current = null
      setReadyA(false)
      setLoadedAPath(null)
      return
    }
    aUrlPathRef.current = aPath
    const image = imgARef.current
    if (image?.complete && image.naturalWidth > 0) {
      markImageAReady()
    }
  // URL changes bind the blob URL to the current path; path-only renders with
  // the previous URL must stay hidden until a new URL arrives.
  // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [aUrl])

  useEffect(() => {
    if (!bUrl) {
      bUrlPathRef.current = null
      setReadyB(false)
      setLoadedBPath(null)
      return
    }
    bUrlPathRef.current = bPath
    const image = imgBRef.current
    if (image?.complete && image.naturalWidth > 0) {
      markImageBReady()
    }
  // URL changes bind the blob URL to the current path; path-only renders with
  // the previous URL must stay hidden until a new URL arrives.
  // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [bUrl])

  const clampSplit = useCallback((value: number) => Math.min(95, Math.max(5, value)), [])

  const handleStagePointerDown = useCallback((e: React.PointerEvent<HTMLDivElement>) => {
    const target = e.target as HTMLElement | null
    if (target?.closest('.compare-label') || target?.closest('.compare-divider-hit')) return
    handlePointerDown(e)
  }, [handlePointerDown])

  const handleStageWheel = useCallback((e: React.WheelEvent<HTMLDivElement>) => {
    markCompareUserInteraction()
    handleWheel(e)
  }, [handleWheel, markCompareUserInteraction])

  const handleStagePointerMove = useCallback((e: React.PointerEvent<HTMLDivElement>) => {
    if (e.buttons !== 0) markCompareUserInteraction()
    handlePointerMove(e)
  }, [handlePointerMove, markCompareUserInteraction])

  const handleDividerPointerDown = useCallback((e: React.PointerEvent<HTMLDivElement>) => {
    const stage = containerRef.current
    if (!stage) return
    e.preventDefault()
    e.stopPropagation()
    const rect = stage.getBoundingClientRect()
    const target = e.currentTarget
    markCompareUserInteraction()
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
  }, [clampSplit, markCompareUserInteraction])

  return (
    <div
      ref={overlayRef}
      role="dialog"
      aria-modal={true}
      aria-label="Compare images"
      data-compare-a-path={aPath ?? undefined}
      data-compare-b-path={bPath ?? undefined}
      tabIndex={-1}
      className="toolbar-offset absolute inset-0 left-[var(--overlay-left)] right-[var(--overlay-right)] bg-panel z-viewer flex flex-col overflow-hidden"
      onKeyDown={handleDialogKeyDown}
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
          onWheel={handleStageWheel}
          onPointerDown={handleStagePointerDown}
          onPointerMove={handleStagePointerMove}
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
                    alt=""
                    aria-hidden={true}
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
                    alt={`Compare image A: ${aLabel}`}
                    data-compare-image="a"
                    data-current-path={loadedAPath ?? undefined}
                    className="compare-image"
                    draggable={false}
                    onDragStart={(e)=> e.preventDefault()}
                    onLoad={markImageAReady}
                    style={{ transform: `translate(${txA}px, ${tyA}px) scale(${baseA * scale})`, transformOrigin: '0 0', opacity: readyA ? 0.99 : 0 }}
                  />
                )}
              </div>
              <div className="compare-layer" style={{ clipPath: `inset(0 0 0 ${splitPct}%)` }}>
                {bThumb && (
                  <img
                    src={bThumb}
                    alt=""
                    aria-hidden={true}
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
                    alt={`Compare image B: ${bLabel}`}
                    data-compare-image="b"
                    data-current-path={loadedBPath ?? undefined}
                    className="compare-image"
                    draggable={false}
                    onDragStart={(e)=> e.preventDefault()}
                    onLoad={markImageBReady}
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
