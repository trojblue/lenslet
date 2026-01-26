import { useCallback, useEffect, useRef, useState } from 'react'

const ZOOM_BASE = 1.2
const MIN_SCALE = 0.05
const MAX_SCALE = 8.0

export function useCompareZoomPan() {
  const [scale, setScale] = useState<number>(1)
  const [txA, setTxA] = useState<number>(0)
  const [tyA, setTyA] = useState<number>(0)
  const [txB, setTxB] = useState<number>(0)
  const [tyB, setTyB] = useState<number>(0)
  const [baseA, setBaseA] = useState<number>(1)
  const [baseB, setBaseB] = useState<number>(1)
  const [dragging, setDragging] = useState<boolean>(false)
  const containerRef = useRef<HTMLDivElement | null>(null)
  const imgARef = useRef<HTMLImageElement | null>(null)
  const imgBRef = useRef<HTMLImageElement | null>(null)

  const fitAndCenter = useCallback(() => {
    const cont = containerRef.current
    if (!cont) return
    const r = cont.getBoundingClientRect()

    const fitImage = (
      img: HTMLImageElement | null,
      setBase: (v: number) => void,
      setTx: (v: number) => void,
      setTy: (v: number) => void
    ) => {
      if (!img || !img.naturalWidth || !img.naturalHeight) return
      const bw = r.width / img.naturalWidth
      const bh = r.height / img.naturalHeight
      const base = Math.min(1, Math.min(bw, bh))
      const imgW = img.naturalWidth * base
      const imgH = img.naturalHeight * base
      setBase(base)
      setTx((r.width - imgW) / 2)
      setTy((r.height - imgH) / 2)
    }

    fitImage(imgARef.current, setBaseA, setTxA, setTyA)
    fitImage(imgBRef.current, setBaseB, setTxB, setTyB)
  }, [])

  useEffect(() => {
    const el = containerRef.current
    if (!el) return
    const ro = new ResizeObserver(() => {
      try { requestAnimationFrame(() => fitAndCenter()) } catch { fitAndCenter() }
    })
    ro.observe(el)
    return () => ro.disconnect()
  }, [fitAndCenter])

  const resetView = useCallback(() => {
    setScale(1)
    fitAndCenter()
  }, [fitAndCenter])

  const handleWheel = useCallback((e: React.WheelEvent) => {
    e.preventDefault()
    const dir = e.deltaY > 0 ? -1 : 1
    const cont = containerRef.current
    if (!cont) return
    const crect = cont.getBoundingClientRect()
    const cx = e.clientX - crect.left
    const cy = e.clientY - crect.top
    setScale((s) => {
      const next = Math.min(MAX_SCALE, Math.max(MIN_SCALE, s * Math.pow(ZOOM_BASE, dir)))
      const ratio = next / s
      setTxA((prev) => cx - ratio * (cx - prev))
      setTyA((prev) => cy - ratio * (cy - prev))
      setTxB((prev) => cx - ratio * (cx - prev))
      setTyB((prev) => cy - ratio * (cy - prev))
      return Number(next.toFixed(4))
    })
  }, [])

  const handlePointerDown = useCallback((e: React.PointerEvent) => {
    if (e.button !== 0) return
    const cont = containerRef.current
    if (!cont) return
    e.preventDefault()
    setDragging(true)
    const startX = e.clientX
    const startY = e.clientY
    const startTxA = txA
    const startTyA = tyA
    const startTxB = txB
    const startTyB = tyB
    const onMove = (ev: PointerEvent) => {
      const dx = ev.clientX - startX
      const dy = ev.clientY - startY
      setTxA(startTxA + dx)
      setTyA(startTyA + dy)
      setTxB(startTxB + dx)
      setTyB(startTyB + dy)
    }
    const onUp = () => {
      window.removeEventListener('pointermove', onMove)
      window.removeEventListener('pointerup', onUp)
      setDragging(false)
    }
    window.addEventListener('pointermove', onMove)
    window.addEventListener('pointerup', onUp)
  }, [txA, tyA, txB, tyB])

  return {
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
  }
}
