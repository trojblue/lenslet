import { useCallback, useEffect, useRef, useState } from 'react'
import {
  type ImageTransformClampOptions,
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
import { createBrowserFrameScheduler, type LatestFrameScheduler } from '../../../lib/frameScheduler'

const ZOOM_BASE = 1.2
const CLICK_SUPPRESSION_DRAG_DISTANCE_PX = 3
const SURFACE_DOUBLE_CLICK_SUPPRESSION_MS = 450
const VIEWER_PAN_SLACK: ImageTransformClampOptions = { panSlack: true }
const IDENTITY_TRANSFORM: ImageTransform = { base: 1, scale: 1, tx: 0, ty: 0 }

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
  return target instanceof Element
    && target.closest('button, a, input, select, textarea, [role="button"]') !== null
}

function nowMs(): number {
  return typeof performance !== 'undefined' && typeof performance.now === 'function'
    ? performance.now()
    : Date.now()
}

export function useZoomPan() {
  const [transform, setTransformState] = useState<ImageTransform>(IDENTITY_TRANSFORM)
  const [ready, setReady] = useState<boolean>(false)
  const [dragging, setDragging] = useState<boolean>(false)
  const [geometryVersion, setGeometryVersion] = useState<number>(0)
  const { scale, tx, ty, base } = transform
  const containerRef = useRef<HTMLDivElement | null>(null)
  const imgRef = useRef<HTMLImageElement | null>(null)
  const transformRef = useRef<ImageTransform>(IDENTITY_TRANSFORM)
  const pendingTransformRef = useRef<ImageTransform | null>(null)
  const transformFrameSchedulerRef = useRef<LatestFrameScheduler | null>(null)
  const resizeFrameSchedulerRef = useRef<LatestFrameScheduler | null>(null)
  const centerRef = useRef<Point>({ x: 0.5, y: 0.5 })
  const pointersRef = useRef<Map<number, Point>>(new Map())
  const panRef = useRef<PanState | null>(null)
  const pinchRef = useRef<PinchState | null>(null)
  const suppressSurfaceDoubleClickUntilRef = useRef(0)

  if (transformFrameSchedulerRef.current === null) {
    transformFrameSchedulerRef.current = createBrowserFrameScheduler()
  }
  if (resizeFrameSchedulerRef.current === null) {
    resizeFrameSchedulerRef.current = createBrowserFrameScheduler()
  }

  const currentTransform = useCallback((): ImageTransform => transformRef.current, [])

  const flushTransformState = useCallback(() => {
    const next = pendingTransformRef.current
    if (!next) return
    pendingTransformRef.current = null
    setTransformState(next)
  }, [])

  const applyTransform = useCallback((next: ImageTransform) => {
    transformRef.current = next
    pendingTransformRef.current = next
    transformFrameSchedulerRef.current?.schedule(flushTransformState)
  }, [flushTransformState])

  const markGeometryReady = useCallback(() => {
    setGeometryVersion((version) => version + 1)
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
    centerRef.current = { x: 0.5, y: 0.5 }
    applyTransform(fitImageToContainer(container, image))
    markGeometryReady()
  }, [applyTransform, markGeometryReady])

  const prepareImagePromotion = useCallback((imageElement: HTMLImageElement): boolean => {
    const container = readElementSize(containerRef.current)
    const image = readImageSize(imageElement)
    if (!container || !image) return false
    const next = fitImageToContainer(container, image)
    transformFrameSchedulerRef.current?.cancel()
    pendingTransformRef.current = null
    centerRef.current = { x: 0.5, y: 0.5 }
    transformRef.current = next
    setTransformState(next)
    markGeometryReady()
    return true
  }, [markGeometryReady])

  const preserveCenterAfterResize = useCallback(() => {
    const container = readElementSize(containerRef.current)
    const image = readImageSize(imgRef.current)
    if (!container || !image) return
    applyTransform(restoreImageTransformForCenter({
      container,
      image,
      center: centerRef.current,
      scale: transformRef.current.scale,
      clampOptions: VIEWER_PAN_SLACK,
    }))
    markGeometryReady()
  }, [applyTransform, markGeometryReady])

  useEffect(() => {
    const el = containerRef.current
    if (!el) return
    const ro = new ResizeObserver(() => {
      resizeFrameSchedulerRef.current?.schedule(preserveCenterAfterResize)
    })
    ro.observe(el)
    return () => {
      ro.disconnect()
      resizeFrameSchedulerRef.current?.cancel()
    }
  }, [preserveCenterAfterResize])

  useEffect(() => {
    return () => {
      transformFrameSchedulerRef.current?.cancel()
      resizeFrameSchedulerRef.current?.cancel()
      pendingTransformRef.current = null
      pointersRef.current.clear()
      panRef.current = null
      pinchRef.current = null
      suppressSurfaceDoubleClickUntilRef.current = 0
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
    const currentScale = transformRef.current.scale
    const nextScale = clampImageScale(currentScale * Math.pow(ZOOM_BASE, dir))
    if (nextScale === currentScale) return
    const next = zoomImageTransformAroundPoint({
      container,
      image,
      transform: currentTransform(),
      point: { x: cx, y: cy },
      nextScale,
      clampOptions: VIEWER_PAN_SLACK,
    })
    centerRef.current = captureNormalizedImageCenter({ container, image, transform: next })
    applyTransform(next)
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
      if (target !== image && transformRef.current.scale <= 1) return
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
            clampOptions: VIEWER_PAN_SLACK,
          })
          const next = clampImageTransform(container, image, {
            ...zoomed,
            tx: zoomed.tx + (center.x - pinch.startCenter.x),
            ty: zoomed.ty + (center.y - pinch.startCenter.y),
          }, VIEWER_PAN_SLACK)
          centerRef.current = captureNormalizedImageCenter({ container, image, transform: next })
          applyTransform(next)
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
      clampOptions: VIEWER_PAN_SLACK,
    })
    centerRef.current = captureNormalizedImageCenter({ container, image, transform: next })
    applyTransform(next)
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
      suppressSurfaceDoubleClickUntilRef.current = nowMs() + SURFACE_DOUBLE_CLICK_SUPPRESSION_MS
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

  const shouldSuppressSurfaceClick = useCallback(() => {
    return suppressSurfaceDoubleClickUntilRef.current > nowMs()
  }, [])

  const zoomToPercent = useCallback((percent: number): boolean => {
    const cont = containerRef.current
    const container = readElementSize(cont)
    const image = readImageSize(imgRef.current)
    if (!cont || !container || !image) return false
    const targetScale = clampImageScale((percent / 100) / Math.max(1e-6, transformRef.current.base))
    const rect = cont.getBoundingClientRect()
    const next = zoomImageTransformAroundPoint({
      container,
      image,
      transform: currentTransform(),
      point: { x: rect.width / 2, y: rect.height / 2 },
      nextScale: targetScale,
      clampOptions: VIEWER_PAN_SLACK,
    })
    centerRef.current = captureNormalizedImageCenter({ container, image, transform: next })
    applyTransform(next)
    return true
  }, [applyTransform, currentTransform])

  return {
    scale, tx, ty, base, ready, setReady, dragging, setDragging, geometryVersion,
    containerRef, imgRef,
    resetView, prepareImagePromotion, zoomToPercent, handleWheel, handlePointerDown, handlePointerMove, handlePointerUp, handlePointerCancel, shouldSuppressSurfaceClick,
  }
}
