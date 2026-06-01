import { useCallback, useEffect, useMemo, useState } from 'react'
import {
  getBrowserZoomWarningBucket,
  resolveVisibleBrowserZoomPercent,
} from '../utils/appShellHelpers'

const BASE_DPR_CANDIDATES = [1, 1.25, 1.5, 1.75, 2, 3, 4] as const

function nearestBaseDevicePixelRatio(dpr: number): number {
  return BASE_DPR_CANDIDATES.reduce((closest, candidate) => (
    Math.abs(candidate - dpr) < Math.abs(closest - dpr) ? candidate : closest
  ), BASE_DPR_CANDIDATES[0])
}

function readBrowserZoomPercent(): number | null {
  const dpr = window.devicePixelRatio || 1
  const base = nearestBaseDevicePixelRatio(dpr)
  const pinchScale = window.visualViewport?.scale ?? 1
  const zoom = (dpr * pinchScale) / base
  if (!Number.isFinite(zoom)) return null
  return Math.min(500, Math.max(25, Math.round(zoom * 100)))
}

export function useBrowserZoomWarning(): {
  visibleBrowserZoomPercent: number | null
  dismissBrowserZoomWarning: () => void
} {
  const [browserZoomPercent, setBrowserZoomPercent] = useState<number | null>(null)
  const [dismissedBrowserZoomBucket, setDismissedBrowserZoomBucket] = useState<number | null>(null)

  useEffect(() => {
    if (typeof window === 'undefined') return
    const update = () => {
      setBrowserZoomPercent(readBrowserZoomPercent())
    }
    update()
    window.addEventListener('resize', update)
    window.addEventListener('orientationchange', update)
    const viewport = window.visualViewport
    if (viewport) viewport.addEventListener('resize', update)
    return () => {
      window.removeEventListener('resize', update)
      window.removeEventListener('orientationchange', update)
      if (viewport) viewport.removeEventListener('resize', update)
    }
  }, [])

  useEffect(() => {
    if (getBrowserZoomWarningBucket(browserZoomPercent) === null) {
      setDismissedBrowserZoomBucket(null)
    }
  }, [browserZoomPercent])

  const visibleBrowserZoomPercent = useMemo(() => (
    resolveVisibleBrowserZoomPercent(browserZoomPercent, dismissedBrowserZoomBucket)
  ), [browserZoomPercent, dismissedBrowserZoomBucket])

  const dismissBrowserZoomWarning = useCallback(() => {
    setDismissedBrowserZoomBucket(getBrowserZoomWarningBucket(browserZoomPercent))
  }, [browserZoomPercent])

  return { visibleBrowserZoomPercent, dismissBrowserZoomWarning }
}
