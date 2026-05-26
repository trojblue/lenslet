import type { MutableRefObject } from 'react'

export function clearScrollIdleTimeout(
  timeoutId: number | null,
  clearTimeoutFn: (timeoutId: number) => void,
): null {
  if (timeoutId !== null) {
    clearTimeoutFn(timeoutId)
  }
  return null
}

export function cancelPendingScrollAnimationFrame(
  frameRef: MutableRefObject<number | null>,
  cancelFrame: (frameId: number) => void,
): void {
  if (frameRef.current === null) return
  try {
    cancelFrame(frameRef.current)
  } finally {
    frameRef.current = null
  }
}
