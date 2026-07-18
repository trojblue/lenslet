import { useCallback, useEffect, useLayoutEffect, useRef, useState } from 'react'
import { api } from '../../../api/client'
import {
  isAbortMediaError,
  mediaErrorFromUnknown,
  type MediaResourceError,
} from '../../../lib/mediaResourceState'
import {
  thumbnailObjectUrlCache,
  type ThumbnailObjectUrlLease,
} from '../model/thumbnailObjectUrlCache'

export type ThumbnailResourceState =
  | { status: 'idle' }
  | { status: 'loading' }
  | { status: 'ready'; url: string; decoded: boolean; markDecoded: () => void }
  | { status: 'error'; error: MediaResourceError; retry: () => void }

type ThumbnailResourceInternalState =
  | Exclude<ThumbnailResourceState, { status: 'ready' }>
  | { status: 'ready'; url: string; decoded: boolean }

export function useThumbnailResource(path: string, enabled: boolean): ThumbnailResourceState {
  const leaseRef = useRef<ThumbnailObjectUrlLease | null>(null)
  const [retryToken, setRetryToken] = useState(0)
  const retry = useCallback(() => setRetryToken((token) => token + 1), [])
  const [state, setState] = useState<ThumbnailResourceInternalState>(() => {
    const existing = thumbnailObjectUrlCache.peekExisting(path)
    return existing
      ? { status: 'ready', url: existing.url, decoded: existing.decoded }
      : { status: 'idle' }
  })
  const markDecoded = useCallback(() => {
    leaseRef.current?.markDecoded()
    setState((current) => current.status === 'ready'
      ? { ...current, decoded: true }
      : current)
  }, [])

  const adoptLease = useCallback((lease: ThumbnailObjectUrlLease) => {
    const previous = leaseRef.current
    leaseRef.current = lease
    setState({ status: 'ready', url: lease.url, decoded: lease.decoded })
    previous?.release()
  }, [])

  useLayoutEffect(() => {
    if (state.status !== 'ready' || leaseRef.current) return
    const lease = thumbnailObjectUrlCache.acquireExisting(path)
    if (lease?.url === state.url) {
      leaseRef.current = lease
      return
    }
    lease?.release()
    setState({ status: 'idle' })
  }, [path, state])

  useEffect(() => {
    if (leaseRef.current || !enabled) return

    const existing = thumbnailObjectUrlCache.acquireExisting(path)
    if (existing) {
      adoptLease(existing)
      return
    }

    let alive = true
    setState({ status: 'loading' })
    api.getThumb(path)
      .then((blob) => {
        if (!alive) return
        adoptLease(thumbnailObjectUrlCache.acquire(path, blob))
      })
      .catch((error) => {
        if (!alive) return
        if (isAbortMediaError(error)) {
          setState({ status: 'idle' })
          return
        }
        setState({
          status: 'error',
          error: mediaErrorFromUnknown(error, 'Thumbnail failed to load.'),
          retry,
        })
      })
    return () => {
      alive = false
    }
  }, [adoptLease, enabled, path, retry, retryToken])

  useEffect(() => () => {
    leaseRef.current?.release()
    leaseRef.current = null
  }, [])

  return state.status === 'ready' ? { ...state, markDecoded } : state
}
