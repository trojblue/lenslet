import { type Dispatch, type SetStateAction, useCallback, useEffect, useRef, useState } from 'react'
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
const CLICK_SUPPRESSION_DRAG_DISTANCE_PX = 3

type PanState = {
  pointerId: number
  startX: number
  startY: number
  startTransform: ImageTransform
  moved: boolean
}

type PinchState = {
  pointerIds: [number, number]
  startDistance: number
  startCenter: Point
  startTransform: ImageTransform
}

export function didViewerPanMove(start: Point, next: Point): boolean {
  return Math.hypot(next.x - start.x, next.y - start.y) >= CLICK_SUPPRESSION_DRAG_DISTANCE_PX
}

export function shouldSuppressViewerClickAfterInteraction(params: {
  panMoved: boolean
  pinchActive: boolean
}): boolean {
  return params.panMoved || params.pinchActive
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

function isInteractiveTarget(target: EventTarget | null): boolean {
  return target instanceof HTMLElement
    && target.closest('button, a, input, select, textarea, [role="button"]') !== null
}

export function useZoomPan() {
  const [scale, setScaleState] = useState<number>(1)
  const [tx, setTxState] = useState<number>(0)
  const [ty, setTyState] = useState<number>(0)
  const [base, setBaseState] = useState<number>(1)
  const [ready, setReady] = useState<boolean>(false)
  const [dragging, setDragging] = useState<boolean>(false)
  const containerRef = useRef<HTMLDivElement | null>(null)
  const imgRef = useRef<HTMLImageElement | null>(null)
  const scaleRef = useRef(1)
  const txRef = useRef(0)
  const tyRef = useRef(0)
  const baseRef = useRef(1)
  const boundsRef = useRef<Size | null>(null)
  const centerRef = useRef<Point>({ x: 0.5, y: 0.5 })
  const pointersRef = useRef<Map<number, Point>>(new Map())
  const panRef = useRef<PanState | null>(null)
  const pinchRef = useRef<PinchState | null>(null)
  const suppressClickRef = useRef(false)

  const currentTransform = useCallback((): ImageTransform => ({
    base: baseRef.current,
    scale: scaleRef.current,
    tx: txRef.current,
    ty: tyRef.current,
  }), [])

  const applyTransform = useCallback((next: ImageTransform) => {
    baseRef.current = next.base
    scaleRef.current = next.scale
    txRef.current = next.tx
    tyRef.current = next.ty
    setBaseState(next.base)
    setScaleState(next.scale)
    setTxState(next.tx)
    setTyState(next.ty)
  }, [])

  const setScale: Dispatch<SetStateAction<number>> = useCallback((value) => {
    const raw = typeof value === 'function' ? value(scaleRef.current) : value
    const next = clampImageScale(raw)
    scaleRef.current = next
    setScaleState(next)
  }, [])

  const setTx: Dispatch<SetStateAction<number>> = useCallback((value) => {
    const next = typeof value === 'function' ? value(txRef.current) : value
    txRef.current = next
    setTxState(next)
  }, [])

  const setTy: Dispatch<SetStateAction<number>> = useCallback((value) => {
    const next = typeof value === 'function' ? value(tyRef.current) : value
    tyRef.current = next
    setTyState(next)
  }, [])

  const startPanFromPointer = useCallback((pointerId: number, point: Point) => {
    panRef.current = {
      pointerId,
      startX: point.x,
      startY: point.y,
      startTransform: currentTransform(),
      moved: false,
    }
    pinchRef.current = null
    setDragging(true)
  }, [currentTransform])

  const startPinchFromPointers = useCallback(() => {
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
      startTransform: currentTransform(),
    }
    panRef.current = null
    setDragging(true)
  }, [currentTransform])

  const resetView = useCallback(() => {
    const container = readElementSize(containerRef.current)
    const image = readImageSize(imgRef.current)
    if (!container || !image) return
    boundsRef.current = container
    centerRef.current = { x: 0.5, y: 0.5 }
    applyTransform(fitImageToContainer(container, image))
  }, [applyTransform])

  const preserveCenterAfterResize = useCallback(() => {
    const container = readElementSize(containerRef.current)
    const image = readImageSize(imgRef.current)
    if (!container || !image) return
    boundsRef.current = container
    applyTransform(restoreImageTransformForCenter({
      container,
      image,
      center: centerRef.current,
      scale: scaleRef.current,
    }))
  }, [applyTransform])

  useEffect(() => {
    const el = containerRef.current
    if (!el) return
    const ro = new ResizeObserver(() => {
      try { requestAnimationFrame(() => preserveCenterAfterResize()) } catch { preserveCenterAfterResize() }
    })
    ro.observe(el)
    return () => ro.disconnect()
  }, [preserveCenterAfterResize])

  useEffect(() => {
    scaleRef.current = scale
    txRef.current = tx
    tyRef.current = ty
    baseRef.current = base
  }, [scale, tx, ty, base])

  useEffect(() => {
    return () => {
      pointersRef.current.clear()
      panRef.current = null
      pinchRef.current = null
      suppressClickRef.current = false
    }
  }, [])

  const handleWheel = useCallback((e: React.WheelEvent) => {
    e.preventDefault()
    const dir = e.deltaY > 0 ? -1 : 1
    const cont = containerRef.current
    const image = readImageSize(imgRef.current)
    const container = readElementSize(cont)
    if (!cont || !container || !image) return
    const crect = cont.getBoundingClientRect()
    const cx = e.clientX - crect.left
    const cy = e.clientY - crect.top
    const currentScale = scaleRef.current
    const nextScale = clampImageScale(currentScale * Math.pow(ZOOM_BASE, dir))
    if (nextScale === currentScale) return
    const next = zoomImageTransformAroundPoint({
      container,
      image,
      transform: currentTransform(),
      point: { x: cx, y: cy },
      nextScale,
    })
    centerRef.current = captureNormalizedImageCenter({ container, image, transform: next })
    applyTransform(next)
    boundsRef.current = container
  }, [applyTransform, currentTransform])

  const handlePointerDown = useCallback((e: React.PointerEvent<HTMLDivElement>) => {
    const pointerType = e.pointerType ?? 'mouse'
    if (pointerType === 'mouse' && e.button !== 0) return
    const activePointers = pointersRef.current
    const image = imgRef.current
    if (!image) return
    if (activePointers.size === 0) {
      const target = e.target as Node
      if (isInteractiveTarget(target)) return
      if (target !== image && scaleRef.current <= 1) return
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
  }, [startPanFromPointer, startPinchFromPointers])

  const handlePointerMove = useCallback((e: React.PointerEvent<HTMLDivElement>) => {
    const pointers = pointersRef.current
    if (!pointers.has(e.pointerId)) return
    pointers.set(e.pointerId, { x: e.clientX, y: e.clientY })
    const container = readElementSize(containerRef.current)
    const image = readImageSize(imgRef.current)
    if (!container || !image) return

    const pinch = pinchRef.current
    if (pinch) {
      const pointA = pointers.get(pinch.pointerIds[0])
      const pointB = pointers.get(pinch.pointerIds[1])
      if (pointA && pointB) {
        const distance = getDistance(pointA, pointB)
        if (distance > 2) {
          const center = getCenter(pointA, pointB)
          const nextScale = clampImageScale(pinch.startTransform.scale * (distance / pinch.startDistance))
          const zoomed = zoomImageTransformAroundPoint({
            container,
            image,
            transform: pinch.startTransform,
            point: pinch.startCenter,
            nextScale,
          })
          const next = clampImageTransform(container, image, {
            ...zoomed,
            tx: zoomed.tx + (center.x - pinch.startCenter.x),
            ty: zoomed.ty + (center.y - pinch.startCenter.y),
          })
          centerRef.current = captureNormalizedImageCenter({ container, image, transform: next })
          applyTransform(next)
          boundsRef.current = container
        }
      }
      return
    }

    const pan = panRef.current
    if (!pan || pan.pointerId !== e.pointerId) return
    const dx = e.clientX - pan.startX
    const dy = e.clientY - pan.startY
    if (!pan.moved) {
      pan.moved = didViewerPanMove(
        { x: pan.startX, y: pan.startY },
        { x: e.clientX, y: e.clientY },
      )
    }
    const next = panImageTransform({
      container,
      image,
      transform: pan.startTransform,
      dx,
      dy,
    })
    centerRef.current = captureNormalizedImageCenter({ container, image, transform: next })
    applyTransform(next)
    boundsRef.current = container
  }, [applyTransform])

  const endPointer = useCallback((pointerId: number, container: HTMLDivElement) => {
    const pointers = pointersRef.current
    if (!pointers.has(pointerId)) return
    const pan = panRef.current
    const pinch = pinchRef.current
    if (shouldSuppressViewerClickAfterInteraction({
      panMoved: pan?.pointerId === pointerId ? pan.moved : false,
      pinchActive: pinch !== null,
    })) {
      suppressClickRef.current = true
    }
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
    const [nextPointerId, point] = pointers.entries().next().value as [number, Point]
    startPanFromPointer(nextPointerId, point)
  }, [startPanFromPointer, startPinchFromPointers])

  const handlePointerUp = useCallback((e: React.PointerEvent<HTMLDivElement>) => {
    endPointer(e.pointerId, e.currentTarget)
  }, [endPointer])

  const handlePointerCancel = useCallback((e: React.PointerEvent<HTMLDivElement>) => {
    endPointer(e.pointerId, e.currentTarget)
  }, [endPointer])

  const consumeClickSuppression = useCallback(() => {
    if (!suppressClickRef.current) return false
    suppressClickRef.current = false
    return true
  }, [])

  return {
    // state
    scale, setScale, tx, setTx, ty, setTy, base, ready, setReady, dragging, setDragging,
    // refs
    containerRef, imgRef,
    // helpers/handlers
    resetView, handleWheel, handlePointerDown, handlePointerMove, handlePointerUp, handlePointerCancel, consumeClickSuppression,
  }
}
