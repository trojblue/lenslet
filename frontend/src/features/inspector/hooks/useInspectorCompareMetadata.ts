import { useCallback, useEffect, useRef, useState } from 'react'
import type { Dispatch, SetStateAction } from 'react'
import { api } from '../../../shared/api/client'
import {
  buildCompareMetadataContextKey,
  shouldApplyMetadataResponse,
} from './metadataRequestGuards'
import type { MetadataRecord, MetadataState } from './useInspectorMetadataTypes'

type UseInspectorCompareMetadataParams = {
  compareReady: boolean
  comparePathA: string | null
  comparePathB: string | null
}

type UseInspectorCompareMetadataResult = {
  compareMetaState: MetadataState
  compareMetaError: string | null
  compareMetaA: MetadataRecord
  compareMetaB: MetadataRecord
  compareIncludePilInfo: boolean
  compareShowPilInfoA: boolean
  compareShowPilInfoB: boolean
  setCompareIncludePilInfo: Dispatch<SetStateAction<boolean>>
  setCompareShowPilInfoA: Dispatch<SetStateAction<boolean>>
  setCompareShowPilInfoB: Dispatch<SetStateAction<boolean>>
  reloadCompareMetadata: () => void
}

export function useInspectorCompareMetadata({
  compareReady,
  comparePathA,
  comparePathB,
}: UseInspectorCompareMetadataParams): UseInspectorCompareMetadataResult {
  const [compareMetaState, setCompareMetaState] = useState<MetadataState>('idle')
  const [compareMetaError, setCompareMetaError] = useState<string | null>(null)
  const [compareMetaA, setCompareMetaA] = useState<MetadataRecord>(null)
  const [compareMetaB, setCompareMetaB] = useState<MetadataRecord>(null)
  const [compareIncludePilInfo, setCompareIncludePilInfo] = useState(false)
  const [compareShowPilInfoA, setCompareShowPilInfoA] = useState(false)
  const [compareShowPilInfoB, setCompareShowPilInfoB] = useState(false)
  const compareContextKey = buildCompareMetadataContextKey(compareReady, comparePathA, comparePathB)
  const compareMetaRequestIdRef = useRef(0)
  const activeCompareContextKeyRef = useRef<string | null>(compareContextKey)
  activeCompareContextKeyRef.current = compareContextKey

  const fetchCompareMetadata = useCallback(async (
    aPath: string,
    bPath: string,
    requestContextKey: string,
  ) => {
    const requestId = compareMetaRequestIdRef.current + 1
    compareMetaRequestIdRef.current = requestId
    setCompareMetaState('loading')
    setCompareMetaError(null)
    try {
      const [aRes, bRes] = await Promise.all([api.getMetadata(aPath), api.getMetadata(bPath)])
      if (
        !shouldApplyMetadataResponse({
          activeRequestId: compareMetaRequestIdRef.current,
          responseRequestId: requestId,
          activeContextKey: activeCompareContextKeyRef.current,
          responseContextKey: requestContextKey,
        })
      ) {
        return
      }
      setCompareMetaA(aRes.meta)
      setCompareMetaB(bRes.meta)
      setCompareMetaState('loaded')
    } catch (err) {
      if (
        !shouldApplyMetadataResponse({
          activeRequestId: compareMetaRequestIdRef.current,
          responseRequestId: requestId,
          activeContextKey: activeCompareContextKeyRef.current,
          responseContextKey: requestContextKey,
        })
      ) {
        return
      }
      const msg = err instanceof Error ? err.message : 'Failed to load metadata'
      setCompareMetaA(null)
      setCompareMetaB(null)
      setCompareMetaError(msg)
      setCompareMetaState('error')
    }
  }, [])

  useEffect(() => {
    compareMetaRequestIdRef.current += 1
    if (!compareContextKey || !comparePathA || !comparePathB) {
      setCompareMetaState('idle')
      setCompareMetaError(null)
      setCompareMetaA(null)
      setCompareMetaB(null)
      setCompareShowPilInfoA(false)
      setCompareShowPilInfoB(false)
      return
    }
    setCompareIncludePilInfo(false)
    setCompareShowPilInfoA(false)
    setCompareShowPilInfoB(false)
    void fetchCompareMetadata(comparePathA, comparePathB, compareContextKey)
  }, [compareContextKey, comparePathA, comparePathB, fetchCompareMetadata])

  const reloadCompareMetadata = useCallback(() => {
    const requestContextKey = buildCompareMetadataContextKey(compareReady, comparePathA, comparePathB)
    if (!requestContextKey || !comparePathA || !comparePathB) return
    void fetchCompareMetadata(comparePathA, comparePathB, requestContextKey)
  }, [compareReady, comparePathA, comparePathB, fetchCompareMetadata])

  return {
    compareMetaState,
    compareMetaError,
    compareMetaA,
    compareMetaB,
    compareIncludePilInfo,
    compareShowPilInfoA,
    compareShowPilInfoB,
    setCompareIncludePilInfo,
    setCompareShowPilInfoA,
    setCompareShowPilInfoB,
    reloadCompareMetadata,
  }
}
