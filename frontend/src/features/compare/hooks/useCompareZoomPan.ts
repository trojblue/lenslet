import { useCallback, useEffect, useRef, useState } from 'react'

const ZOOM_BASE = 1.2
const MIN_SCALE = 0.05
const MAX_SCALE = 8.0

type PointerPoint = {
  x: number
  y: number
}

type PanState = {
  pointerId: number
  startX: number
  startY: number
  startTxA: number
  startTyA: number
  startTxB: number
  startTyB: number
}

type PinchState = {
  pointerIds: [number, number]
  startDistance: number
  startCenter: PointerPoint
  startScale: number
  startTxA: number
  startTyA: number
  startTxB: number
  startTyB: number
}

function clampScale(value: number): number {
  return Number(Math.min(MAX_SCALE, Math.max(MIN_SCALE, value)).toFixed(4))
}

function getDistance(a: PointerPoint, b: PointerPoint): number {
  return Math.hypot(a.x - b.x, a.y - b.y)
}

function getCenter(a: PointerPoint, b: PointerPoint): PointerPoint {
  return { x: (a.x + b.x) / 2, y: (a.y + b.y) / 2 }
}

function trySetPointerCapture(target: HTMLDivElement, pointerId: number): void {
  try {
    target.setPointerCapture(pointerId)
  } catch {
    // Ignore browsers that reject pointer capture here.
  }
}

function tryReleasePointerCapture(target: HTMLDivElement, pointerId: number): void {
  try {
    target.releasePointerCapture(pointerId)
  } catch {
    // Ignore browsers that reject pointer capture release.
  }
}

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
  const scaleRef = useRef(1)
  const txARef = useRef(0)
  const tyARef = useRef(0)
  const txBRef = useRef(0)
  const tyBRef = useRef(0)
  const pointersRef = useRef<Map<number, PointerPoint>>(new Map())
  const panRef = useRef<PanState | null>(null)
  const pinchRef = useRef<PinchState | null>(null)

  const setOffsets = useCallback((next: {
    txA: number
    tyA: number
    txB: number
    tyB: number
  }) => {
    txARef.current = next.txA
    tyARef.current = next.tyA
    txBRef.current = next.txB
    tyBRef.current = next.tyB
    setTxA(next.txA)
    setTyA(next.tyA)
    setTxB(next.txB)
    setTyB(next.tyB)
  }, [])

  const setScaleValue = useCallback((value: number) => {
    const next = clampScale(value)
    scaleRef.current = next
    setScale(next)
  }, [])

  const startPanFromPointer = useCallback((pointerId: number, point: PointerPoint) => {
    panRef.current = {
      pointerId,
      startX: point.x,
      startY: point.y,
      startTxA: txARef.current,
      startTyA: tyARef.current,
      startTxB: txBRef.current,
      startTyB: tyBRef.current,
    }
    pinchRef.current = null
    setDragging(true)
  }, [])

  const startPinchFromPointers = useCallback(() => {
    const entries = Array.from(pointersRef.current.entries())
    if (entries.length < 2) return
    const [first, second] = entries
    const [idA, pointA] = first
    const [idB, pointB] = second
    const distance = getDistance(pointA, pointB)
    if (!Number.isFinite(distance) || distance <= 2) return
    pinchRef.current = {
      pointerIds: [idA, idB],
      startDistance: distance,
      startCenter: getCenter(pointA, pointB),
      startScale: scaleRef.current,
      startTxA: txARef.current,
      startTyA: tyARef.current,
      startTxB: txBRef.current,
      startTyB: tyBRef.current,
    }
    panRef.current = null
    setDragging(true)
  }, [])

  const endPointer = useCallback((pointerId: number, target: HTMLDivElement) => {
    const pointers = pointersRef.current
    if (!pointers.has(pointerId)) return
    pointers.delete(pointerId)
    tryReleasePointerCapture(target, pointerId)
    if (pointers.size === 0) {
      panRef.current = null
      pinchRef.current = null
      setDragging(false)
      return
    }
    if (pointers.size >= 2) {
      startPinchFromPointers()
      return
    }
    const [nextPointerId, point] = pointers.entries().next().value as [number, PointerPoint]
    startPanFromPointer(nextPointerId, point)
  }, [startPanFromPointer, startPinchFromPointers])

  const fitAndCenter = useCallback(() => {
    const cont = containerRef.current
    if (!cont) return
    const r = cont.getBoundingClientRect()

    const fitImage = (img: HTMLImageElement | null) => {
      if (!img || !img.naturalWidth || !img.naturalHeight) return
      const bw = r.width / img.naturalWidth
      const bh = r.height / img.naturalHeight
      const base = Math.min(1, Math.min(bw, bh))
      const imgW = img.naturalWidth * base
      const imgH = img.naturalHeight * base
      return {
        base,
        tx: (r.width - imgW) / 2,
        ty: (r.height - imgH) / 2,
      }
    }

    const fittedA = fitImage(imgARef.current)
    if (fittedA) {
      setBaseA(fittedA.base)
      txARef.current = fittedA.tx
      tyARef.current = fittedA.ty
      setTxA(fittedA.tx)
      setTyA(fittedA.ty)
    }

    const fittedB = fitImage(imgBRef.current)
    if (fittedB) {
      setBaseB(fittedB.base)
      txBRef.current = fittedB.tx
      tyBRef.current = fittedB.ty
      setTxB(fittedB.tx)
      setTyB(fittedB.ty)
    }
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
    setScaleValue(1)
    fitAndCenter()
  }, [fitAndCenter, setScaleValue])

  useEffect(() => {
    scaleRef.current = scale
    txARef.current = txA
    tyARef.current = tyA
    txBRef.current = txB
    tyBRef.current = tyB
  }, [scale, txA, tyA, txB, tyB])

  useEffect(() => {
    return () => {
      pointersRef.current.clear()
      panRef.current = null
      pinchRef.current = null
    }
  }, [])

  const handleWheel = useCallback((e: React.WheelEvent) => {
    e.preventDefault()
    const dir = e.deltaY > 0 ? -1 : 1
    const cont = containerRef.current
    if (!cont) return
    const crect = cont.getBoundingClientRect()
    const cx = e.clientX - crect.left
    const cy = e.clientY - crect.top
    const currentScale = scaleRef.current
    const nextScale = clampScale(currentScale * Math.pow(ZOOM_BASE, dir))
    if (nextScale === currentScale) return
    const ratio = nextScale / currentScale
    setScaleValue(nextScale)
    setOffsets({
      txA: cx - ratio * (cx - txARef.current),
      tyA: cy - ratio * (cy - tyARef.current),
      txB: cx - ratio * (cx - txBRef.current),
      tyB: cy - ratio * (cy - tyBRef.current),
    })
  }, [setOffsets, setScaleValue])

  const handlePointerDown = useCallback((e: React.PointerEvent<HTMLDivElement>) => {
    const pointerType = e.pointerType ?? 'mouse'
    if (pointerType === 'mouse' && e.button !== 0) return
    const target = e.currentTarget
    e.preventDefault()
    pointersRef.current.set(e.pointerId, { x: e.clientX, y: e.clientY })
    trySetPointerCapture(target, e.pointerId)
    if (pointersRef.current.size >= 2) {
      startPinchFromPointers()
      return
    }
    startPanFromPointer(e.pointerId, { x: e.clientX, y: e.clientY })
  }, [startPanFromPointer, startPinchFromPointers])

  const handlePointerMove = useCallback((e: React.PointerEvent<HTMLDivElement>) => {
    const pointers = pointersRef.current
    if (!pointers.has(e.pointerId)) return
    pointers.set(e.pointerId, { x: e.clientX, y: e.clientY })

    const pinch = pinchRef.current
    if (pinch) {
      const pointA = pointers.get(pinch.pointerIds[0])
      const pointB = pointers.get(pinch.pointerIds[1])
      if (pointA && pointB) {
        const distance = getDistance(pointA, pointB)
        if (distance > 2) {
          const center = getCenter(pointA, pointB)
          const nextScale = clampScale(pinch.startScale * (distance / pinch.startDistance))
          const ratio = nextScale / pinch.startScale
          setScaleValue(nextScale)
          setOffsets({
            txA: center.x - ratio * (pinch.startCenter.x - pinch.startTxA),
            tyA: center.y - ratio * (pinch.startCenter.y - pinch.startTyA),
            txB: center.x - ratio * (pinch.startCenter.x - pinch.startTxB),
            tyB: center.y - ratio * (pinch.startCenter.y - pinch.startTyB),
          })
        }
      }
      return
    }

    const pan = panRef.current
    if (!pan || pan.pointerId !== e.pointerId) return
    const dx = e.clientX - pan.startX
    const dy = e.clientY - pan.startY
    setOffsets({
      txA: pan.startTxA + dx,
      tyA: pan.startTyA + dy,
      txB: pan.startTxB + dx,
      tyB: pan.startTyB + dy,
    })
  }, [setOffsets, setScaleValue])

  const handlePointerUp = useCallback((e: React.PointerEvent<HTMLDivElement>) => {
    endPointer(e.pointerId, e.currentTarget)
  }, [endPointer])

  const handlePointerCancel = useCallback((e: React.PointerEvent<HTMLDivElement>) => {
    endPointer(e.pointerId, e.currentTarget)
  }, [endPointer])

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
    handlePointerMove,
    handlePointerUp,
    handlePointerCancel,
  }
}
