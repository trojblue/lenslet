import { useEffect, type Dispatch, type RefObject, type SetStateAction } from 'react'
import { useLatestRef } from '../../shared/hooks/useLatestRef'

type UseGridPinchResizeParams = {
  shellRef: RefObject<HTMLElement | null>
  disabled: boolean
  gridItemSize: number
  setGridItemSize: Dispatch<SetStateAction<number>>
}

function clampGridItemSize(value: number): number {
  return Math.min(500, Math.max(80, value))
}

function getTouchDistance(touches: TouchList): number {
  if (touches.length < 2) return 0
  const [a, b] = [touches[0], touches[1]]
  return Math.hypot(a.clientX - b.clientX, a.clientY - b.clientY)
}

export function useGridPinchResize({
  shellRef,
  disabled,
  gridItemSize,
  setGridItemSize,
}: UseGridPinchResizeParams): void {
  const gridItemSizeRef = useLatestRef(gridItemSize)

  useEffect(() => {
    if (disabled) return
    const shell = shellRef.current
    if (!shell) return
    let pinchStart: { dist: number; size: number } | null = null

    const onTouchStart = (event: TouchEvent) => {
      if (event.touches.length !== 2) return
      const dist = getTouchDistance(event.touches)
      if (!dist) return
      pinchStart = { dist, size: gridItemSizeRef.current }
    }

    const onTouchMove = (event: TouchEvent) => {
      if (!pinchStart || event.touches.length !== 2) return
      const dist = getTouchDistance(event.touches)
      if (!dist) return
      event.preventDefault()
      setGridItemSize(clampGridItemSize(pinchStart.size * (dist / pinchStart.dist)))
    }

    const onTouchEnd = () => {
      pinchStart = null
    }

    shell.addEventListener('touchstart', onTouchStart, { passive: true })
    shell.addEventListener('touchmove', onTouchMove, { passive: false })
    shell.addEventListener('touchend', onTouchEnd)
    shell.addEventListener('touchcancel', onTouchEnd)

    return () => {
      shell.removeEventListener('touchstart', onTouchStart)
      shell.removeEventListener('touchmove', onTouchMove)
      shell.removeEventListener('touchend', onTouchEnd)
      shell.removeEventListener('touchcancel', onTouchEnd)
    }
  }, [disabled, gridItemSizeRef, setGridItemSize, shellRef])
}
