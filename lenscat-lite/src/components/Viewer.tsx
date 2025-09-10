import React, { useEffect, useRef, useState } from 'react'
import { api } from '../api/client'

export default function Viewer({ path, onClose, onNavigate }:{ path: string; onClose:()=>void; onNavigate?:(delta:number)=>void }){
  const [url, setUrl] = useState<string | null>(null)
  const [scale, setScale] = useState<number>(1)
  const [tx, setTx] = useState<number>(0)
  const [ty, setTy] = useState<number>(0)
  const [base, setBase] = useState<number>(1) // fit-to-container scale
  const [dragging, setDragging] = useState<boolean>(false)
  const containerRef = useRef<HTMLDivElement | null>(null)
  const imgRef = useRef<HTMLImageElement | null>(null)

  useEffect(() => {
    let alive = true
    api.getFile(path).then(b => { if (!alive) return; setUrl(URL.createObjectURL(b)) }).catch(()=>{})
    setScale(1)
    setTx(0); setTy(0)
    setBase(1)
    const onKey = (e: KeyboardEvent) => {
      if (e.key === 'Escape') onClose()
      else if ((e.key === 'ArrowRight' || e.key === 'd') && onNavigate) onNavigate(1)
      else if ((e.key === 'ArrowLeft' || e.key === 'a') && onNavigate) onNavigate(-1)
    }
    window.addEventListener('keydown', onKey)
    return () => { alive = false; window.removeEventListener('keydown', onKey); if (url) URL.revokeObjectURL(url) }
  }, [path])

  // Constrain viewer to the main gallery area (between resizers)
  return (
    <div
      ref={containerRef}
      className={`viewer${scale>1?' grabbable':''}${dragging?' dragging':''}`}
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
        // start drag only if clicking within the viewer area and when zoomed in beyond base
        const cont = containerRef.current
        if (!cont || scale <= 1) return
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
      <button className="viewer-back" onClick={(e)=>{ e.stopPropagation(); onClose() }}>← Back</button>
      {url && (
        <img
          ref={imgRef}
          src={url}
          alt="viewer"
          className="viewer-img"
          onLoad={(ev)=>{
            const cont = containerRef.current
            const im = ev.currentTarget
            if (!cont) return
            const r = cont.getBoundingClientRect()
            const bw = r.width / im.naturalWidth
            const bh = r.height / im.naturalHeight
            const b = Math.min(bw, bh)
            setBase(b)
            // center at base
            const imgW = im.naturalWidth * b
            const imgH = im.naturalHeight * b
            setTx((r.width - imgW)/2)
            setTy((r.height - imgH)/2)
          }}
          onClick={(e)=> e.stopPropagation()}
          style={{ transform: `translate(${tx}px, ${ty}px) scale(${base * scale})`, transformOrigin: `0 0` }}
        />
      )}
    </div>
  )
}


