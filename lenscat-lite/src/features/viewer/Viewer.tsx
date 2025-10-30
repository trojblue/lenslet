import React, { useEffect, useState } from 'react'
import { api } from '../../shared/api/client'
import { useZoomPan } from './hooks/useZoomPan'

export default function Viewer({ path, onClose, onNavigate, onZoomChange, requestedZoomPercent, onZoomRequestConsumed }:{ path: string; onClose:()=>void; onNavigate?:(delta:number)=>void; onZoomChange?:(p:number)=>void; requestedZoomPercent?: number | null; onZoomRequestConsumed?: ()=>void }){
  const [url, setUrl] = useState<string | null>(null)
  const [thumbUrl, setThumbUrl] = useState<string | null>(null)
  const { scale, setScale, tx, setTx, ty, setTy, base, setBase, ready, setReady, dragging, visible, setVisible, containerRef, imgRef, fitAndCenter, handleWheel, handleMouseDown } = useZoomPan()

  useEffect(() => {
    let alive = true
    api.getFile(path).then(b => { if (!alive) return; setUrl(URL.createObjectURL(b)) }).catch(()=>{})
    api.getThumb(path).then(b => { if (!alive) return; setThumbUrl(URL.createObjectURL(b)) }).catch(()=>{})
    const onKey = (e: KeyboardEvent) => {
      if (e.key === 'Escape') { setVisible(false); window.setTimeout(() => onClose(), 110) }
      else if ((e.key === 'ArrowRight' || e.key === 'd') && onNavigate) onNavigate(1)
      else if ((e.key === 'ArrowLeft' || e.key === 'a') && onNavigate) onNavigate(-1)
    }
    window.addEventListener('keydown', onKey)
    try { requestAnimationFrame(() => setVisible(true)) } catch { setVisible(true) }
    return () => { alive = false; window.removeEventListener('keydown', onKey); if (url) URL.revokeObjectURL(url); if (thumbUrl) URL.revokeObjectURL(thumbUrl) }
  }, [path])

  useEffect(() => { return () => { if (url) { try { URL.revokeObjectURL(url) } catch {} } } }, [url])
  useEffect(() => { return () => { if (thumbUrl) { try { URL.revokeObjectURL(thumbUrl) } catch {} } } }, [thumbUrl])
  useEffect(() => { setReady(false) }, [url])

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
      className={`viewer grabbable${dragging?' dragging':''}${visible?' is-visible':''}`}
      onClick={() => { setVisible(false); window.setTimeout(() => onClose(), 110) }}
      onWheel={handleWheel}
      onMouseDown={handleMouseDown}
    >
      {thumbUrl && (
        <img
          src={thumbUrl}
          alt="thumb"
          className="viewer-thumb"
          draggable={false}
          onDragStart={(e)=> e.preventDefault()}
          style={{ transform: `translate(${tx}px, ${ty}px) scale(${base})`, transformOrigin: `0 0`, opacity: ready ? 0 : 0.5 }}
        />
      )}
      {url && (
        <img
          ref={imgRef}
          src={url}
          alt="viewer"
          className="viewer-img"
          draggable={false}
          onDragStart={(e)=>{ e.preventDefault() }}
          onLoad={(ev)=>{ fitAndCenter(); setScale(1); try { requestAnimationFrame(()=> setReady(true)) } catch { setReady(true) } }}
          onClick={(e)=> e.stopPropagation()}
          style={{ transform: `translate(${tx}px, ${ty}px) scale(${base * scale})`, transformOrigin: `0 0`, opacity: ready ? 0.99 : 0 }}
        />
      )}
    </div>
  )
}


