import { useCallback, useMemo, useSyncExternalStore } from 'react'

export function useMediaQuery(query: string, defaultValue = false): boolean {
  const mediaQueryList = useMemo(() => {
    if (typeof window === 'undefined' || !('matchMedia' in window)) return null
    return window.matchMedia(query)
  }, [query])

  const subscribe = useCallback((onStoreChange: () => void) => {
    if (!mediaQueryList) return () => {}
    mediaQueryList.addEventListener('change', onStoreChange)
    return () => mediaQueryList.removeEventListener('change', onStoreChange)
  }, [mediaQueryList])

  const getSnapshot = useCallback(
    () => mediaQueryList?.matches ?? defaultValue,
    [defaultValue, mediaQueryList],
  )
  const getServerSnapshot = useCallback(() => defaultValue, [defaultValue])

  return useSyncExternalStore(subscribe, getSnapshot, getServerSnapshot)
}
