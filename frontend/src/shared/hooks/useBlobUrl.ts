import { useEffect, useRef, useState } from 'react'

type PendingRevoke = {
  url: string
  cancel: () => void
}

function revokeObjectUrl(url: string): void {
  try {
    URL.revokeObjectURL(url)
  } catch {
    // Ignore URL revocation errors.
  }
}

function scheduleObjectUrlRevoke(url: string, onFinalize: () => void): PendingRevoke {
  let finalized = false
  const finalize = () => {
    if (finalized) return
    finalized = true
    onFinalize()
  }

  if (typeof window !== 'undefined' && typeof window.requestAnimationFrame === 'function') {
    let frameA = 0
    let frameB = 0
    frameA = window.requestAnimationFrame(() => {
      frameB = window.requestAnimationFrame(() => {
        finalize()
        revokeObjectUrl(url)
      })
    })
    return {
      url,
      cancel: () => {
        if (frameA) window.cancelAnimationFrame(frameA)
        if (frameB) window.cancelAnimationFrame(frameB)
        finalize()
      },
    }
  }

  const timeoutId = setTimeout(() => {
    finalize()
    revokeObjectUrl(url)
  }, 0)
  return {
    url,
    cancel: () => {
      clearTimeout(timeoutId)
      finalize()
    },
  }
}

export function useBlobUrl(fetcher: (() => Promise<Blob>) | null, deps: React.DependencyList): string | null {
  const [url, setUrl] = useState<string | null>(null)
  const urlRef = useRef<string | null>(null)
  const pendingRevokesRef = useRef<PendingRevoke[]>([])

  const flushPendingRevokes = () => {
    const pending = pendingRevokesRef.current
    pendingRevokesRef.current = []
    for (const entry of pending) {
      entry.cancel()
      revokeObjectUrl(entry.url)
    }
  }

  useEffect(() => {
    if (!fetcher) {
      flushPendingRevokes()
      if (urlRef.current) {
        revokeObjectUrl(urlRef.current)
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
        const previous = urlRef.current
        urlRef.current = next
        setUrl(next)
        if (previous) {
          const pendingRevoke = scheduleObjectUrlRevoke(previous, () => {
            pendingRevokesRef.current = pendingRevokesRef.current.filter((entry) => entry.url !== previous)
          })
          pendingRevokesRef.current.push(pendingRevoke)
        }
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
      flushPendingRevokes()
      if (urlRef.current) {
        revokeObjectUrl(urlRef.current)
        urlRef.current = null
      }
    }
  }, [])

  return url
}
