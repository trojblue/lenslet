import { useCallback, useEffect, useRef, useState } from 'react'
import type { Dispatch, SetStateAction } from 'react'
import { api } from '../../../shared/api/client'
import {
  buildSingleMetadataContextKey,
  shouldApplyMetadataResponse,
} from './metadataRequestGuards'
import type { MetadataRecord, MetadataState } from './useInspectorMetadataTypes'

type UseInspectorSingleMetadataParams = {
  path: string | null
  sidecarUpdatedAt: string | undefined
  autoloadMetadata: boolean
}

type UseInspectorSingleMetadataResult = {
  metaRaw: MetadataRecord
  metaError: string | null
  metaState: MetadataState
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

export function projectSingleMetadataSnapshot(
  snapshot: SingleMetadataSnapshot,
  activeContextKey: string | null,
): SingleMetadataView {
  if (snapshot.contextKey !== activeContextKey) {
    return EMPTY_SINGLE_METADATA_VIEW
  }
  return {
    metaRaw: snapshot.metaRaw,
    metaError: snapshot.metaError,
    metaState: snapshot.metaState,
    showPilInfo: snapshot.showPilInfo,
  }
}

export function useInspectorSingleMetadata({
  path,
  sidecarUpdatedAt,
  autoloadMetadata,
}: UseInspectorSingleMetadataParams): UseInspectorSingleMetadataResult {
  const [metaRaw, setMetaRaw] = useState<MetadataRecord>(null)
  const [metaError, setMetaError] = useState<string | null>(null)
  const [metaState, setMetaState] = useState<MetadataState>('idle')
  const [showPilInfo, setShowPilInfo] = useState(false)
  const metadataContextKey = buildSingleMetadataContextKey(path, sidecarUpdatedAt)
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
    const requestContextKey = buildSingleMetadataContextKey(path, sidecarUpdatedAt)
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
  }, [path, sidecarUpdatedAt])

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
  )

  return {
    metaRaw: projected.metaRaw,
    metaError: projected.metaError,
    metaState: projected.metaState,
    showPilInfo: projected.showPilInfo,
    setMetaError,
    setShowPilInfo,
    fetchMetadata,
  }
}
