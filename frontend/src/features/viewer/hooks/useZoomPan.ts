import { useEffect, useRef, useState } from 'react'

export function useZoomPan() {
  const [scale, setScale] = useState<number>(1)
  const [tx, setTx] = useState<number>(0)
  const [ty, setTy] = useState<number>(0)
  const [base, setBase] = useState<number>(1)
  const [ready, setReady] = useState<boolean>(false)
  const [dragging, setDragging] = useState<boolean>(false)
  const [visible, setVisible] = useState<boolean>(false)
  const containerRef = useRef<HTMLDivElement | null>(null)
  const imgRef = useRef<HTMLImageElement | null>(null)

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
    const el = containerRef.current
    if (!el) return
    const ro = new ResizeObserver(() => { try { requestAnimationFrame(() => fitAndCenter()) } catch { fitAndCenter() } })
    ro.observe(el)
    return () => ro.disconnect()
  }, [])

  const handleWheel = (e: React.WheelEvent) => {
    e.preventDefault()
    const dir = e.deltaY > 0 ? -1 : 1
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
      setTx(prevTx => cx - ratio * (cx - prevTx))
      setTy(prevTy => cy - ratio * (cy - prevTy))
      return Number(next.toFixed(4))
    })
  }

  const handleMouseDown = (e: React.MouseEvent) => {
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
    const onMove = (ev: MouseEvent) => { setTx(startTx + (ev.clientX - startX)); setTy(startTy + (ev.clientY - startY)) }
    const onUp = () => { window.removeEventListener('mousemove', onMove); window.removeEventListener('mouseup', onUp); setDragging(false) }
    window.addEventListener('mousemove', onMove)
    window.addEventListener('mouseup', onUp)
  }

  return {
    // state
    scale, setScale, tx, setTx, ty, setTy, base, setBase, ready, setReady, dragging, setDragging, visible, setVisible,
    // refs
    containerRef, imgRef,
    // helpers/handlers
    fitAndCenter, handleWheel, handleMouseDown,
  }
}


