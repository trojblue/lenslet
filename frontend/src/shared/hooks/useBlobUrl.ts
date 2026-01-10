import { useEffect, useRef, useState } from 'react'

export function useBlobUrl(fetcher: (() => Promise<Blob>) | null, deps: React.DependencyList): string | null {
  const [url, setUrl] = useState<string | null>(null)
  const urlRef = useRef<string | null>(null)

  useEffect(() => {
    if (!fetcher) {
      if (urlRef.current) {
        try { URL.revokeObjectURL(urlRef.current) } catch {}
        urlRef.current = null
      }
      setUrl(null)
      return
    }

    let alive = true
    fetcher()
      .then((blob) => {
        if (!alive) return
        const next = URL.createObjectURL(blob)
        if (urlRef.current) {
          try { URL.revokeObjectURL(urlRef.current) } catch {}
        }
        urlRef.current = next
        setUrl(next)
      })
      .catch(() => {
        // Ignore fetch errors
      })

    return () => {
      alive = false
    }
  // eslint-disable-next-line react-hooks/exhaustive-deps
  }, deps)

  useEffect(() => {
    return () => {
      if (urlRef.current) {
        try { URL.revokeObjectURL(urlRef.current) } catch {}
        urlRef.current = null
      }
    }
  }, [])

  return url
}
