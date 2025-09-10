import React, { useEffect, useRef, useState } from 'react'
import { api } from '../api/client'

export default function Viewer({ path, onClose, onNavigate, onZoomChange, requestedZoomPercent, onZoomRequestConsumed }:{ path: string; onClose:()=>void; onNavigate?:(delta:number)=>void; onZoomChange?:(p:number)=>void; requestedZoomPercent?: number | null; onZoomRequestConsumed?: ()=>void }){
  const [url, setUrl] = useState<string | null>(null)
  const [scale, setScale] = useState<number>(1)
  const [tx, setTx] = useState<number>(0)
  const [ty, setTy] = useState<number>(0)
  const [base, setBase] = useState<number>(1) // fit-to-container scale
  const [dragging, setDragging] = useState<boolean>(false)
  const containerRef = useRef<HTMLDivElement | null>(null)
  const imgRef = useRef<HTMLImageElement | null>(null)

  // Compute base fit (no upscaling) and center within the container
  const fitAndCenter = () => {
    const cont = containerRef.current
    const im = imgRef.current
    if (!cont || !im || !im.naturalWidth || !im.naturalHeight) return
    const r = cont.getBoundingClientRect()
    const bw = r.width / im.naturalWidth
    const bh = r.height / im.naturalHeight
    const b = Math.min(1, Math.min(bw, bh))
    setBase(b)
    const imgW = im.naturalWidth * b
    const imgH = im.naturalHeight * b
    setTx((r.width - imgW)/2)
    setTy((r.height - imgH)/2)
  }

  useEffect(() => {
    let alive = true
    api.getFile(path).then(b => { if (!alive) return; setUrl(URL.createObjectURL(b)) }).catch(()=>{})
    // Prefetch neighbors (previous and next) optimistically
    try {
      // Neighbor list not available here; parent passes onNavigate only. We infer neighbors via list in App when navigating.
      // As a best effort, ask App to handle or attempt lightweight prefetch via path heuristics not available; keeping here minimal.
    } catch {}
    const onKey = (e: KeyboardEvent) => {
      if (e.key === 'Escape') onClose()
      else if ((e.key === 'ArrowRight' || e.key === 'd') && onNavigate) onNavigate(1)
      else if ((e.key === 'ArrowLeft' || e.key === 'a') && onNavigate) onNavigate(-1)
    }
    window.addEventListener('keydown', onKey)
    return () => { alive = false; window.removeEventListener('keydown', onKey); if (url) URL.revokeObjectURL(url) }
  }, [path])

  // Refit and re-center when the viewer container resizes
  useEffect(() => {
    const el = containerRef.current
    if (!el) return
    const ro = new ResizeObserver(() => {
      fitAndCenter()
    })
    ro.observe(el)
    return () => ro.disconnect()
  }, [])

  // Report zoom percent to parent
  useEffect(() => {
    if (onZoomChange) onZoomChange((base * scale) * 100)
  }, [base, scale, onZoomChange])

  // Apply external zoom requests centered in the container
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

  // Constrain viewer to the main gallery area (between resizers)
  return (
    <div
      ref={containerRef}
      className={`viewer grabbable${dragging?' dragging':''}`}
      onClick={onClose}
      onWheel={(e)=>{
        e.preventDefault()
        const dir = e.deltaY > 0 ? -1 : 1
        // Multiplicative zoom with cursor-anchored transform
        const BASE = 1.2
        const MIN = 0.05
        const MAX = 8.0
        const cont = containerRef.current
        if (!cont) return
        const crect = cont.getBoundingClientRect()
        const cx = e.clientX - crect.left
        const cy = e.clientY - crect.top
        setScale(s => {
          const next = Math.min(MAX, Math.max(MIN, s * Math.pow(BASE, dir)))
          const ratio = next / s
          // Adjust translation so the point under the cursor remains fixed
          setTx(prevTx => cx - ratio * (cx - prevTx))
          setTy(prevTy => cy - ratio * (cy - prevTy))
          return Number(next.toFixed(4))
        })
      }}
      onMouseDown={(e)=>{
        // Start drag only when pressing on the image (so background clicks still close)
        const cont = containerRef.current
        const im = imgRef.current
        if (!cont || !im) return
        const target = e.target as Node
        if (target !== im) return
        const rect = cont.getBoundingClientRect()
        if (e.clientX < rect.left || e.clientX > rect.right || e.clientY < rect.top || e.clientY > rect.bottom) return
        e.preventDefault()
        e.stopPropagation()
        setDragging(true)
        const startX = e.clientX
        const startY = e.clientY
        const startTx = tx
        const startTy = ty
        const onMove = (ev: MouseEvent) => {
          setTx(startTx + (ev.clientX - startX))
          setTy(startTy + (ev.clientY - startY))
        }
        const onUp = () => {
          window.removeEventListener('mousemove', onMove)
          window.removeEventListener('mouseup', onUp)
          setDragging(false)
        }
        window.addEventListener('mousemove', onMove)
        window.addEventListener('mouseup', onUp)
      }}
    >
      {/* Back button moved to toolbar while viewer is active */}
      {url && (
        <img
          ref={imgRef}
          src={url}
          alt="viewer"
          className="viewer-img"
          draggable={false}
          onDragStart={(e)=>{ e.preventDefault() }}
          onLoad={(ev)=>{ fitAndCenter(); setScale(1) }}
          onClick={(e)=> e.stopPropagation()}
          style={{ transform: `translate(${tx}px, ${ty}px) scale(${base * scale})`, transformOrigin: `0 0` }}
        />
      )}
    </div>
  )
}


