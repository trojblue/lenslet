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

export function useInspectorSingleMetadata({
  path,
  sidecarUpdatedAt,
}: UseInspectorSingleMetadataParams): UseInspectorSingleMetadataResult {
  const [metaRaw, setMetaRaw] = useState<MetadataRecord>(null)
  const [metaError, setMetaError] = useState<string | null>(null)
  const [metaState, setMetaState] = useState<MetadataState>('idle')
  const [showPilInfo, setShowPilInfo] = useState(false)
  const metadataContextKey = buildSingleMetadataContextKey(path, sidecarUpdatedAt)
  const metaRequestIdRef = useRef(0)
  const activeMetadataContextKeyRef = useRef<string | null>(metadataContextKey)
  activeMetadataContextKeyRef.current = metadataContextKey

  useEffect(() => {
    metaRequestIdRef.current += 1
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

  return {
    metaRaw,
    metaError,
    metaState,
    showPilInfo,
    setMetaError,
    setShowPilInfo,
    fetchMetadata,
  }
}
