import { useEffect, type RefObject } from 'react'
import { clampGridItemSize, GRID_ITEM_SIZE_CONTRACT } from '../../lib/gridItemSize'
import { useLatestRef } from '../../shared/hooks/useLatestRef'

const WHEEL_DELTA_PER_STEP = 100

type GridResizeGestureBinding = {
  target: HTMLElement
  getGridItemSize: () => number
  onGridItemSizeChange: (size: number) => void
  requestFrame: (callback: FrameRequestCallback) => number
  cancelFrame: (handle: number) => void
}

type UseGridResizeGesturesParams = {
  gridRef: RefObject<HTMLElement | null>
  disabled: boolean
  gridItemSize: number
  onGridItemSizeChange: (size: number) => void
}

export function isGridResizeWheel(
  event: Pick<WheelEvent, 'ctrlKey' | 'metaKey'>,
): boolean {
  return event.ctrlKey || event.metaKey
}

export function applyAccumulatedGridWheelDelta(
  gridItemSize: number,
  accumulatedDelta: number,
): { gridItemSize: number; remainingDelta: number } {
  const steps = Math.trunc(accumulatedDelta / WHEEL_DELTA_PER_STEP)
  if (steps === 0) return { gridItemSize, remainingDelta: accumulatedDelta }

  const rawSize = gridItemSize + steps * GRID_ITEM_SIZE_CONTRACT.step
  const nextSize = clampGridItemSize(rawSize)
  return {
    gridItemSize: nextSize,
    remainingDelta: nextSize === rawSize
      ? accumulatedDelta - steps * WHEEL_DELTA_PER_STEP
      : 0,
  }
}

function getTouchDistance(touches: TouchList): number {
  if (touches.length < 2) return 0
  const [a, b] = [touches[0], touches[1]]
  return Math.hypot(a.clientX - b.clientX, a.clientY - b.clientY)
}

export function bindGridResizeGestures({
  target,
  getGridItemSize,
  onGridItemSizeChange,
  requestFrame,
  cancelFrame,
}: GridResizeGestureBinding): () => void {
  let pinchStart: { dist: number; size: number } | null = null
  let accumulatedWheelDelta = 0
  let wheelFrame: number | null = null

  const flushWheel = () => {
    wheelFrame = null
    const currentSize = getGridItemSize()
    const result = applyAccumulatedGridWheelDelta(currentSize, accumulatedWheelDelta)
    accumulatedWheelDelta = result.remainingDelta
    if (result.gridItemSize !== currentSize) onGridItemSizeChange(result.gridItemSize)
  }

  const onWheel = (event: WheelEvent) => {
    if (!isGridResizeWheel(event)) return
    event.preventDefault()
    accumulatedWheelDelta -= event.deltaY
    if (wheelFrame === null) wheelFrame = requestFrame(flushWheel)
  }

  const onTouchStart = (event: TouchEvent) => {
    if (event.touches.length !== 2) return
    const dist = getTouchDistance(event.touches)
    if (!dist) return
    pinchStart = { dist, size: getGridItemSize() }
  }

  const onTouchMove = (event: TouchEvent) => {
    if (!pinchStart || event.touches.length !== 2) return
    const dist = getTouchDistance(event.touches)
    if (!dist) return
    event.preventDefault()
    onGridItemSizeChange(clampGridItemSize(pinchStart.size * (dist / pinchStart.dist)))
  }

  const onTouchEnd = () => {
    pinchStart = null
  }

  target.addEventListener('wheel', onWheel, { passive: false })
  target.addEventListener('touchstart', onTouchStart, { passive: true })
  target.addEventListener('touchmove', onTouchMove, { passive: false })
  target.addEventListener('touchend', onTouchEnd)
  target.addEventListener('touchcancel', onTouchEnd)

  return () => {
    target.removeEventListener('wheel', onWheel)
    target.removeEventListener('touchstart', onTouchStart)
    target.removeEventListener('touchmove', onTouchMove)
    target.removeEventListener('touchend', onTouchEnd)
    target.removeEventListener('touchcancel', onTouchEnd)
    if (wheelFrame !== null) cancelFrame(wheelFrame)
  }
}

export function useGridResizeGestures({
  gridRef,
  disabled,
  gridItemSize,
  onGridItemSizeChange,
}: UseGridResizeGesturesParams): void {
  const gridItemSizeRef = useLatestRef(gridItemSize)
  const onGridItemSizeChangeRef = useLatestRef(onGridItemSizeChange)

  useEffect(() => {
    if (disabled) return
    const grid = gridRef.current
    if (!grid) return

    return bindGridResizeGestures({
      target: grid,
      getGridItemSize: () => gridItemSizeRef.current,
      onGridItemSizeChange: (nextSize) => {
        gridItemSizeRef.current = nextSize
        onGridItemSizeChangeRef.current(nextSize)
      },
      requestFrame: window.requestAnimationFrame.bind(window),
      cancelFrame: window.cancelAnimationFrame.bind(window),
    })
  }, [disabled, gridItemSizeRef, gridRef, onGridItemSizeChangeRef])
}
