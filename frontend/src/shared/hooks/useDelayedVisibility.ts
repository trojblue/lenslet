import { useEffect, useState } from 'react'

export function delayedVisibilityWaitMs(
  delayMs: number,
  startedAtMs: number,
  nowMs: number,
): number {
  return Math.max(0, delayMs - Math.max(0, nowMs - startedAtMs))
}

export function useDelayedVisibility(
  active: boolean,
  delayMs: number,
  startedAtMs?: number,
): boolean {
  const [visible, setVisible] = useState(() => (
    active
    && startedAtMs != null
    && delayedVisibilityWaitMs(delayMs, startedAtMs, Date.now()) === 0
  ))

  useEffect(() => {
    if (!active) {
      setVisible(false)
      return
    }

    const startedAt = startedAtMs ?? Date.now()
    const waitMs = delayedVisibilityWaitMs(delayMs, startedAt, Date.now())
    if (waitMs === 0) {
      setVisible(true)
      return
    }

    setVisible(false)
    const timeoutId = window.setTimeout(() => setVisible(true), waitMs)
    return () => window.clearTimeout(timeoutId)
  }, [active, delayMs, startedAtMs])

  return visible
}
