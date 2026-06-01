import { useEffect, useState } from 'react'

export function useMediaQuery(query: string, defaultValue = false): boolean {
  const [matches, setMatches] = useState(defaultValue)

  useEffect(() => {
    if (typeof window === 'undefined' || !('matchMedia' in window)) return

    const mediaQueryList = window.matchMedia(query)
    const sync = () => setMatches(mediaQueryList.matches)
    sync()

    mediaQueryList.addEventListener('change', sync)
    return () => mediaQueryList.removeEventListener('change', sync)
  }, [query])

  return matches
}
