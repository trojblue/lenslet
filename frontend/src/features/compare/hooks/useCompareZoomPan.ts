import { useCallback, useEffect, useRef, useState } from 'react'
import {
  type ImageTransform,
  type Point,
  type Size,
  captureNormalizedImageCenter,
  clampImageScale,
  clampImageTransform,
  fitImageToContainer,
  panImageTransform,
  restoreImageTransformForCenter,
  zoomImageTransformAroundPoint,
} from '../../../lib/imageTransform'

const ZOOM_BASE = 1.2

type UseCompareZoomPanOptions = {
  onUserInteraction?: () => void
}

type PanState = {
  pointerId: number
  startX: number
  startY: number
  startA: ImageTransform
  startB: ImageTransform
}

type PinchState = {
  pointerIds: [number, number]
  startDistance: number
  startCenter: Point
  startA: ImageTransform
  startB: ImageTransform
}

function getDistance(a: Point, b: Point): number {
  return Math.hypot(a.x - b.x, a.y - b.y)
}

function getCenter(a: Point, b: Point): Point {
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

function readElementSize(element: HTMLElement | null): Size | null {
  if (!element) return null
  const rect = element.getBoundingClientRect()
  if (!Number.isFinite(rect.width) || !Number.isFinite(rect.height) || rect.width <= 0 || rect.height <= 0) {
    return null
  }
  return { width: rect.width, height: rect.height }
}

function readImageSize(image: HTMLImageElement | null): Size | null {
  if (!image || !image.naturalWidth || !image.naturalHeight) return null
  return { width: image.naturalWidth, height: image.naturalHeight }
}

export function useCompareZoomPan(options: UseCompareZoomPanOptions = {}) {
  const { onUserInteraction } = options
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
  const baseARef = useRef(1)
  const baseBRef = useRef(1)
  const centerARef = useRef<Point>({ x: 0.5, y: 0.5 })
  const centerBRef = useRef<Point>({ x: 0.5, y: 0.5 })
  const pointersRef = useRef<Map<number, Point>>(new Map())
  const panRef = useRef<PanState | null>(null)
  const pinchRef = useRef<PinchState | null>(null)

  const currentA = useCallback((): ImageTransform => ({
    base: baseARef.current,
    scale: scaleRef.current,
    tx: txARef.current,
    ty: tyARef.current,
  }), [])

  const currentB = useCallback((): ImageTransform => ({
    base: baseBRef.current,
    scale: scaleRef.current,
    tx: txBRef.current,
    ty: tyBRef.current,
  }), [])

  const applyTransforms = useCallback((next: {
    a?: ImageTransform
    b?: ImageTransform
    scale?: number
  }) => {
    const nextScale = clampImageScale(next.scale ?? next.a?.scale ?? next.b?.scale ?? scaleRef.current)
    scaleRef.current = nextScale
    setScale(nextScale)
    if (next.a) {
      baseARef.current = next.a.base
      txARef.current = next.a.tx
      tyARef.current = next.a.ty
      setBaseA(next.a.base)
      setTxA(next.a.tx)
      setTyA(next.a.ty)
    }
    if (next.b) {
      baseBRef.current = next.b.base
      txBRef.current = next.b.tx
      tyBRef.current = next.b.ty
      setBaseB(next.b.base)
      setTxB(next.b.tx)
      setTyB(next.b.ty)
    }
  }, [])

  const startPanFromPointer = useCallback((pointerId: number, point: Point) => {
    panRef.current = {
      pointerId,
      startX: point.x,
      startY: point.y,
      startA: currentA(),
      startB: currentB(),
    }
    pinchRef.current = null
    setDragging(true)
  }, [currentA, currentB])

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
      startA: currentA(),
      startB: currentB(),
    }
    panRef.current = null
    setDragging(true)
  }, [currentA, currentB])

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
    const [nextPointerId, point] = pointers.entries().next().value as [number, Point]
    startPanFromPointer(nextPointerId, point)
  }, [startPanFromPointer, startPinchFromPointers])

  const fitAndCenter = useCallback((): boolean => {
    const container = readElementSize(containerRef.current)
    if (!container) return false
    centerARef.current = { x: 0.5, y: 0.5 }
    centerBRef.current = { x: 0.5, y: 0.5 }
    const imageA = readImageSize(imgARef.current)
    const imageB = readImageSize(imgBRef.current)
    if (!imageA || !imageB) return false
    applyTransforms({
      a: restoreImageTransformForCenter({
        container,
        image: imageA,
        center: { x: 0.5, y: 0.5 },
        scale: scaleRef.current,
      }),
      b: restoreImageTransformForCenter({
        container,
        image: imageB,
        center: { x: 0.5, y: 0.5 },
        scale: scaleRef.current,
      }),
    })
    return true
  }, [applyTransforms])

  const preserveCenterAfterResize = useCallback(() => {
    const container = readElementSize(containerRef.current)
    if (!container) return
    const imageA = readImageSize(imgARef.current)
    const imageB = readImageSize(imgBRef.current)
    applyTransforms({
      a: imageA ? restoreImageTransformForCenter({
        container,
        image: imageA,
        center: centerARef.current,
        scale: scaleRef.current,
      }) : undefined,
      b: imageB ? restoreImageTransformForCenter({
        container,
        image: imageB,
        center: centerBRef.current,
        scale: scaleRef.current,
      }) : undefined,
    })
  }, [applyTransforms])

  useEffect(() => {
    const el = containerRef.current
    if (!el) return
    const ro = new ResizeObserver(() => {
      try { requestAnimationFrame(() => preserveCenterAfterResize()) } catch { preserveCenterAfterResize() }
    })
    ro.observe(el)
    return () => ro.disconnect()
  }, [preserveCenterAfterResize])

  const resetView = useCallback(() => {
    const container = readElementSize(containerRef.current)
    if (!container) {
      scaleRef.current = 1
      setScale(1)
      return
    }
    centerARef.current = { x: 0.5, y: 0.5 }
    centerBRef.current = { x: 0.5, y: 0.5 }
    const imageA = readImageSize(imgARef.current)
    const imageB = readImageSize(imgBRef.current)
    applyTransforms({
      scale: 1,
      a: imageA ? fitImageToContainer(container, imageA) : undefined,
      b: imageB ? fitImageToContainer(container, imageB) : undefined,
    })
  }, [applyTransforms])

  useEffect(() => {
    scaleRef.current = scale
    txARef.current = txA
    tyARef.current = tyA
    txBRef.current = txB
    tyBRef.current = tyB
    baseARef.current = baseA
    baseBRef.current = baseB
  }, [scale, txA, tyA, txB, tyB, baseA, baseB])

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
    const container = readElementSize(cont)
    const imageA = readImageSize(imgARef.current)
    const imageB = readImageSize(imgBRef.current)
    if (!cont || !container || !imageA || !imageB) return
    const crect = cont.getBoundingClientRect()
    const cx = e.clientX - crect.left
    const cy = e.clientY - crect.top
    const currentScale = scaleRef.current
    const nextScale = clampImageScale(currentScale * Math.pow(ZOOM_BASE, dir))
    if (nextScale === currentScale) return
    onUserInteraction?.()
    const nextA = zoomImageTransformAroundPoint({
      container,
      image: imageA,
      transform: currentA(),
      point: { x: cx, y: cy },
      nextScale,
    })
    const nextB = zoomImageTransformAroundPoint({
      container,
      image: imageB,
      transform: currentB(),
      point: { x: cx, y: cy },
      nextScale,
    })
    centerARef.current = captureNormalizedImageCenter({ container, image: imageA, transform: nextA })
    centerBRef.current = captureNormalizedImageCenter({ container, image: imageB, transform: nextB })
    applyTransforms({
      a: nextA,
      b: nextB,
    })
  }, [applyTransforms, currentA, currentB, onUserInteraction])

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
    const container = readElementSize(containerRef.current)
    const imageA = readImageSize(imgARef.current)
    const imageB = readImageSize(imgBRef.current)
    if (!container || !imageA || !imageB) return

    const pinch = pinchRef.current
    if (pinch) {
      const pointA = pointers.get(pinch.pointerIds[0])
      const pointB = pointers.get(pinch.pointerIds[1])
      if (pointA && pointB) {
        const distance = getDistance(pointA, pointB)
        if (distance > 2) {
          const center = getCenter(pointA, pointB)
          const nextScale = clampImageScale(pinch.startA.scale * (distance / pinch.startDistance))
          const zoomedA = zoomImageTransformAroundPoint({
            container,
            image: imageA,
            transform: pinch.startA,
            point: pinch.startCenter,
            nextScale,
          })
          const zoomedB = zoomImageTransformAroundPoint({
            container,
            image: imageB,
            transform: pinch.startB,
            point: pinch.startCenter,
            nextScale,
          })
          const nextA = clampImageTransform(container, imageA, {
            ...zoomedA,
            tx: zoomedA.tx + (center.x - pinch.startCenter.x),
            ty: zoomedA.ty + (center.y - pinch.startCenter.y),
          })
          const nextB = clampImageTransform(container, imageB, {
            ...zoomedB,
            tx: zoomedB.tx + (center.x - pinch.startCenter.x),
            ty: zoomedB.ty + (center.y - pinch.startCenter.y),
          })
          centerARef.current = captureNormalizedImageCenter({ container, image: imageA, transform: nextA })
          centerBRef.current = captureNormalizedImageCenter({ container, image: imageB, transform: nextB })
          onUserInteraction?.()
          applyTransforms({ a: nextA, b: nextB })
        }
      }
      return
    }

    const pan = panRef.current
    if (!pan || pan.pointerId !== e.pointerId) return
    const dx = e.clientX - pan.startX
    const dy = e.clientY - pan.startY
    const nextA = panImageTransform({
      container,
      image: imageA,
      transform: pan.startA,
      dx,
      dy,
    })
    const nextB = panImageTransform({
      container,
      image: imageB,
      transform: pan.startB,
      dx,
      dy,
    })
    centerARef.current = captureNormalizedImageCenter({ container, image: imageA, transform: nextA })
    centerBRef.current = captureNormalizedImageCenter({ container, image: imageB, transform: nextB })
    onUserInteraction?.()
    applyTransforms({ a: nextA, b: nextB })
  }, [applyTransforms, onUserInteraction])

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
