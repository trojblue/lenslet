import { useEffect, useState } from 'react'

export function useMediaQuery(query: string, defaultValue = false): boolean {
  const [matches, setMatches] = useState(defaultValue)

  useEffect(() => {
    if (typeof window === 'undefined' || !('matchMedia' in window)) return

    const mediaQueryList = window.matchMedia(query)
    const legacyMediaQueryList = mediaQueryList as MediaQueryList & {
      addListener?: (listener: (event: MediaQueryListEvent) => void) => void
      removeListener?: (listener: (event: MediaQueryListEvent) => void) => void
    }
    const sync = () => setMatches(mediaQueryList.matches)
    sync()

    if (typeof mediaQueryList.addEventListener === 'function') {
      mediaQueryList.addEventListener('change', sync)
      return () => mediaQueryList.removeEventListener('change', sync)
    }

    if (typeof legacyMediaQueryList.addListener === 'function' && typeof legacyMediaQueryList.removeListener === 'function') {
      legacyMediaQueryList.addListener(sync)
      return () => legacyMediaQueryList.removeListener?.(sync)
    }

    return undefined
  }, [query])

  return matches
}
