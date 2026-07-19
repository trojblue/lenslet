import { useCallback, useEffect, useRef, useState } from 'react'
import type { Dispatch, SetStateAction } from 'react'
import { api } from '../../../api/client'
import {
  buildSingleMetadataContextKey,
  shouldApplyMetadataResponse,
} from './metadataRequestGuards'
import type { MetadataRecord, MetadataState } from './useInspectorMetadataTypes'

type UseInspectorSingleMetadataParams = {
  path: string | null
  autoloadMetadata: boolean
  scopeKey?: string
}

type UseInspectorSingleMetadataResult = {
  metaRaw: MetadataRecord
  metaError: string | null
  metaState: MetadataState
  showMetadataLoadingCopy: boolean
  showPilInfo: boolean
  setMetaError: Dispatch<SetStateAction<string | null>>
  setShowPilInfo: Dispatch<SetStateAction<boolean>>
  fetchMetadata: () => Promise<void>
}

export type SingleMetadataSnapshot = {
  contextKey: string | null
  metaRaw: MetadataRecord
  metaError: string | null
  metaState: MetadataState
  showPilInfo: boolean
}

type SingleMetadataView = Omit<SingleMetadataSnapshot, 'contextKey'>

const EMPTY_SINGLE_METADATA_VIEW: SingleMetadataView = {
  metaRaw: null,
  metaError: null,
  metaState: 'idle',
  showPilInfo: false,
}

export const METADATA_LOADING_COPY_DELAY_MS = 1_000

export function projectSingleMetadataSnapshot(
  snapshot: SingleMetadataSnapshot,
  activeContextKey: string | null,
  autoloadMetadata = false,
): SingleMetadataView {
  if (snapshot.contextKey !== activeContextKey) {
    return autoloadMetadata && activeContextKey
      ? { ...EMPTY_SINGLE_METADATA_VIEW, metaState: 'loading' }
      : EMPTY_SINGLE_METADATA_VIEW
  }
  const projected = {
    metaRaw: snapshot.metaRaw,
    metaError: snapshot.metaError,
    metaState: snapshot.metaState,
    showPilInfo: snapshot.showPilInfo,
  }
  if (autoloadMetadata && activeContextKey && projected.metaState === 'idle') {
    projected.metaState = 'loading'
  }
  return projected
}

export function useInspectorSingleMetadata({
  path,
  autoloadMetadata,
  scopeKey = 'default',
}: UseInspectorSingleMetadataParams): UseInspectorSingleMetadataResult {
  const [metaRaw, setMetaRaw] = useState<MetadataRecord>(null)
  const [metaError, setMetaError] = useState<string | null>(null)
  const [metaState, setMetaState] = useState<MetadataState>('idle')
  const [showPilInfo, setShowPilInfo] = useState(false)
  const [loadingCopyContextKey, setLoadingCopyContextKey] = useState<string | null>(null)
  const metadataContextKey = path ? JSON.stringify([scopeKey, path]) : null
  const [metaContextKey, setMetaContextKey] = useState<string | null>(metadataContextKey)
  const metaRequestIdRef = useRef(0)
  const activeMetadataContextKeyRef = useRef<string | null>(metadataContextKey)
  activeMetadataContextKeyRef.current = metadataContextKey

  useEffect(() => {
    metaRequestIdRef.current += 1
    setMetaContextKey(metadataContextKey)
    setMetaRaw(null)
    setMetaError(null)
    setMetaState('idle')
    setShowPilInfo(false)
  }, [metadataContextKey])

  const fetchMetadata = useCallback(async () => {
    const requestContextKey = path ? JSON.stringify([scopeKey, path]) : null
    if (!requestContextKey || !path) return

    const requestId = metaRequestIdRef.current + 1
    metaRequestIdRef.current = requestId

    setMetaContextKey(requestContextKey)
    setMetaState('loading')
    setMetaError(null)
    try {
      const res = await api.getMetadata(path)
      if (
        !shouldApplyMetadataResponse({
          activeRequestId: metaRequestIdRef.current,
          responseRequestId: requestId,
          activeContextKey: activeMetadataContextKeyRef.current,
          responseContextKey: requestContextKey,
        })
      ) {
        return
      }
      setMetaRaw(res.meta)
      setMetaState('loaded')
    } catch (err) {
      if (
        !shouldApplyMetadataResponse({
          activeRequestId: metaRequestIdRef.current,
          responseRequestId: requestId,
          activeContextKey: activeMetadataContextKeyRef.current,
          responseContextKey: requestContextKey,
        })
      ) {
        return
      }
      const msg = err instanceof Error ? err.message : 'Failed to load metadata'
      setMetaRaw(null)
      setMetaError(msg)
      setMetaState('error')
    }
  }, [path, scopeKey])

  useEffect(() => {
    if (!autoloadMetadata || !path) return
    void fetchMetadata()
  }, [autoloadMetadata, path, metadataContextKey, fetchMetadata])

  const projected = projectSingleMetadataSnapshot(
    {
      contextKey: metaContextKey,
      metaRaw,
      metaError,
      metaState,
      showPilInfo,
    },
    metadataContextKey,
    autoloadMetadata,
  )

  useEffect(() => {
    setLoadingCopyContextKey(null)
    if (projected.metaState !== 'loading' || !metadataContextKey) return
    const timeoutId = window.setTimeout(() => {
      setLoadingCopyContextKey(metadataContextKey)
    }, METADATA_LOADING_COPY_DELAY_MS)
    return () => window.clearTimeout(timeoutId)
  }, [metadataContextKey, projected.metaState])

  return {
    metaRaw: projected.metaRaw,
    metaError: projected.metaError,
    metaState: projected.metaState,
    showMetadataLoadingCopy: projected.metaState === 'loading'
      && loadingCopyContextKey === metadataContextKey,
    showPilInfo: projected.showPilInfo,
    setMetaError,
    setShowPilInfo,
    fetchMetadata,
  }
}
