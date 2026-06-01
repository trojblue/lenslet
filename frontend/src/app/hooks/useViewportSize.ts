import { useEffect, useState } from 'react'

export type ViewportSize = {
  viewportWidth: number
  viewportHeight: number
}

export function useViewportSize(): ViewportSize {
  const [viewportWidth, setViewportWidth] = useState(() => (
    typeof window === 'undefined' ? 1440 : window.innerWidth
  ))
  const [viewportHeight, setViewportHeight] = useState(() => (
    typeof window === 'undefined' ? 900 : window.innerHeight
  ))

  useEffect(() => {
    if (typeof window === 'undefined') return
    const update = () => {
      setViewportWidth(window.innerWidth)
      setViewportHeight(window.innerHeight)
    }
    update()
    window.addEventListener('resize', update)
    window.addEventListener('orientationchange', update)
    return () => {
      window.removeEventListener('resize', update)
      window.removeEventListener('orientationchange', update)
    }
  }, [])

  return { viewportWidth, viewportHeight }
}
