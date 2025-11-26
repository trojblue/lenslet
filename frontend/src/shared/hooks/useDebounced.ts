import React from 'react'

export function useDebounced<T>(value: T, delayMs: number = 250): T {
  const [debounced, setDebounced] = React.useState<T>(value)
  React.useEffect(() => {
    const t = window.setTimeout(() => setDebounced(value), Math.max(0, delayMs))
    return () => window.clearTimeout(t)
  }, [value, delayMs])
  return debounced
}


