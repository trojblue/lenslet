import { useEffect, useRef, useState } from 'react'

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
  startTx: number
  startTy: number
}

type PinchState = {
  pointerIds: [number, number]
  startDistance: number
  startCenter: PointerPoint
  startScale: number
  startTx: number
  startTy: number
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
  const scaleRef = useRef(1)
  const txRef = useRef(0)
  const tyRef = useRef(0)
  const pointersRef = useRef<Map<number, PointerPoint>>(new Map())
  const panRef = useRef<PanState | null>(null)
  const pinchRef = useRef<PinchState | null>(null)

  const setOffsets = (nextTx: number, nextTy: number) => {
    txRef.current = nextTx
    tyRef.current = nextTy
    setTx(nextTx)
    setTy(nextTy)
  }

  const setScaleValue = (value: number) => {
    const next = clampScale(value)
    scaleRef.current = next
    setScale(next)
  }

  const startPanFromPointer = (pointerId: number, point: PointerPoint) => {
    panRef.current = {
      pointerId,
      startX: point.x,
      startY: point.y,
      startTx: txRef.current,
      startTy: tyRef.current,
    }
    pinchRef.current = null
    setDragging(true)
  }

  const startPinchFromPointers = () => {
    const entries = Array.from(pointersRef.current.entries())
    if (entries.length < 2) return
    const [first, second] = entries
    const [idA, pointA] = first
    const [idB, pointB] = second
    const startDistance = getDistance(pointA, pointB)
    if (!Number.isFinite(startDistance) || startDistance <= 2) return
    pinchRef.current = {
      pointerIds: [idA, idB],
      startDistance,
      startCenter: getCenter(pointA, pointB),
      startScale: scaleRef.current,
      startTx: txRef.current,
      startTy: tyRef.current,
    }
    panRef.current = null
    setDragging(true)
  }

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
    setOffsets((r.width - imgW) / 2, (r.height - imgH) / 2)
    setScaleValue(1)
  }

  useEffect(() => {
    const el = containerRef.current
    if (!el) return
    const ro = new ResizeObserver(() => { try { requestAnimationFrame(() => fitAndCenter()) } catch { fitAndCenter() } })
    ro.observe(el)
    return () => ro.disconnect()
  }, [])

  useEffect(() => {
    scaleRef.current = scale
    txRef.current = tx
    tyRef.current = ty
  }, [scale, tx, ty])

  useEffect(() => {
    return () => {
      pointersRef.current.clear()
      panRef.current = null
      pinchRef.current = null
    }
  }, [])

  const handleWheel = (e: React.WheelEvent) => {
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
    const nextTx = cx - ratio * (cx - txRef.current)
    const nextTy = cy - ratio * (cy - tyRef.current)
    setScaleValue(nextScale)
    setOffsets(nextTx, nextTy)
  }

  const handlePointerDown = (e: React.PointerEvent<HTMLDivElement>) => {
    const pointerType = e.pointerType ?? 'mouse'
    if (pointerType === 'mouse' && e.button !== 0) return
    const activePointers = pointersRef.current
    const image = imgRef.current
    if (!image) return
    if (activePointers.size === 0) {
      const target = e.target as Node
      if (target !== image) return
    }
    const container = e.currentTarget
    const rect = container.getBoundingClientRect()
    if (e.clientX < rect.left || e.clientX > rect.right || e.clientY < rect.top || e.clientY > rect.bottom) return
    e.preventDefault()
    e.stopPropagation()
    activePointers.set(e.pointerId, { x: e.clientX, y: e.clientY })
    trySetPointerCapture(container, e.pointerId)
    if (activePointers.size >= 2) {
      startPinchFromPointers()
      return
    }
    startPanFromPointer(e.pointerId, { x: e.clientX, y: e.clientY })
  }

  const handlePointerMove = (e: React.PointerEvent<HTMLDivElement>) => {
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
          const nextTx = center.x - ratio * (pinch.startCenter.x - pinch.startTx)
          const nextTy = center.y - ratio * (pinch.startCenter.y - pinch.startTy)
          setScaleValue(nextScale)
          setOffsets(nextTx, nextTy)
        }
      }
      return
    }

    const pan = panRef.current
    if (!pan || pan.pointerId !== e.pointerId) return
    const dx = e.clientX - pan.startX
    const dy = e.clientY - pan.startY
    setOffsets(pan.startTx + dx, pan.startTy + dy)
  }

  const endPointer = (pointerId: number, container: HTMLDivElement) => {
    const pointers = pointersRef.current
    if (!pointers.has(pointerId)) return
    pointers.delete(pointerId)
    tryReleasePointerCapture(container, pointerId)
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
  }

  const handlePointerUp = (e: React.PointerEvent<HTMLDivElement>) => {
    endPointer(e.pointerId, e.currentTarget)
  }

  const handlePointerCancel = (e: React.PointerEvent<HTMLDivElement>) => {
    endPointer(e.pointerId, e.currentTarget)
  }

  return {
    // state
    scale, setScale, tx, setTx, ty, setTy, base, setBase, ready, setReady, dragging, setDragging, visible, setVisible,
    // refs
    containerRef, imgRef,
    // helpers/handlers
    fitAndCenter, handleWheel, handlePointerDown, handlePointerMove, handlePointerUp, handlePointerCancel,
  }
}
