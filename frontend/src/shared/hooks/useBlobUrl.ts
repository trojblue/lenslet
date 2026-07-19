import {
  useCallback,
  useEffect,
  useRef,
  useState,
  type DependencyList,
  type MutableRefObject,
} from 'react'
import {
  isAbortMediaError,
  mediaErrorFromUnknown,
  type BlobMediaResourceState,
  type MediaResourceSource,
} from '../../lib/mediaResourceState'

export type PendingRevoke = {
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

export function scheduleObjectUrlRevoke(url: string, onFinalize: () => void): PendingRevoke {
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

function flushPendingRevokes(pendingRevokesRef: MutableRefObject<PendingRevoke[]>): void {
  const pending = pendingRevokesRef.current
  pendingRevokesRef.current = []
  for (const entry of pending) {
    entry.cancel()
    revokeObjectUrl(entry.url)
  }
}

function revokeCurrentObjectUrl(urlRef: MutableRefObject<string | null>): void {
  if (!urlRef.current) return
  revokeObjectUrl(urlRef.current)
  urlRef.current = null
}

function clearObjectUrls(
  urlRef: MutableRefObject<string | null>,
  pendingRevokesRef: MutableRefObject<PendingRevoke[]>,
): void {
  flushPendingRevokes(pendingRevokesRef)
  revokeCurrentObjectUrl(urlRef)
}

function queueObjectUrlRevoke(
  url: string,
  pendingRevokesRef: MutableRefObject<PendingRevoke[]>,
): void {
  const pendingRevoke = scheduleObjectUrlRevoke(url, () => {
    pendingRevokesRef.current = pendingRevokesRef.current.filter((entry) => entry.url !== url)
  })
  pendingRevokesRef.current.push(pendingRevoke)
}

export function useBlobUrl(fetcher: (() => Promise<Blob>) | null, deps: DependencyList): string | null {
  const [url, setUrl] = useState<string | null>(null)
  const urlRef = useRef<string | null>(null)
  const pendingRevokesRef = useRef<PendingRevoke[]>([])

  useEffect(() => {
    if (!fetcher) {
      clearObjectUrls(urlRef, pendingRevokesRef)
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
          queueObjectUrlRevoke(previous, pendingRevokesRef)
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
      clearObjectUrls(urlRef, pendingRevokesRef)
    }
  }, [])

  return url
}

export function useBlobResource(
  fetcher: (() => Promise<Blob>) | null,
  deps: DependencyList,
  options: {
    source?: MediaResourceSource
    unsupportedReason?: string | null
    identity?: string
  } = {},
): BlobMediaResourceState {
  const source = options.source ?? 'blob'
  const unsupportedReason = options.unsupportedReason ?? null
  const identity = options.identity
  const [state, setState] = useState<BlobMediaResourceState>({ status: 'idle' })
  const requestIdRef = useRef(0)
  const urlRef = useRef<string | null>(null)
  const pendingRevokesRef = useRef<PendingRevoke[]>([])
  const [retryToken, setRetryToken] = useState(0)
  const retry = useCallback(() => {
    setRetryToken((token) => token + 1)
  }, [])

  useEffect(() => {
    if (unsupportedReason) {
      clearObjectUrls(urlRef, pendingRevokesRef)
      setState({ status: 'unsupported', reason: unsupportedReason, identity })
      return
    }

    if (!fetcher) {
      clearObjectUrls(urlRef, pendingRevokesRef)
      setState({ status: 'idle', identity })
      return
    }

    let alive = true
    const requestId = requestIdRef.current + 1
    requestIdRef.current = requestId
    setState({ status: 'loading', requestId, source, identity })

    let promise: Promise<Blob>
    try {
      promise = fetcher()
    } catch (error) {
      if (isAbortMediaError(error)) {
        setState({ status: 'idle', identity })
      } else {
        setState({
          status: 'error',
          requestId,
          error: mediaErrorFromUnknown(error),
          retry,
          identity,
        })
      }
      return
    }

    promise
      .then((blob) => {
        if (!alive || requestIdRef.current !== requestId) return
        const next = URL.createObjectURL(blob)
        const previous = urlRef.current
        urlRef.current = next
        setState({ status: 'ready', requestId, source, url: next, identity })
        if (previous) {
          queueObjectUrlRevoke(previous, pendingRevokesRef)
        }
      })
      .catch((error) => {
        if (!alive || requestIdRef.current !== requestId) return
        if (isAbortMediaError(error)) {
          setState({ status: 'idle', identity })
          return
        }
        setState({
          status: 'error',
          requestId,
          error: mediaErrorFromUnknown(error),
          retry,
          identity,
        })
      })

    return () => {
      alive = false
    }
  // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [...deps, retryToken, source, unsupportedReason, identity])

  useEffect(() => {
    return () => {
      clearObjectUrls(urlRef, pendingRevokesRef)
    }
  }, [])

  return state
}
