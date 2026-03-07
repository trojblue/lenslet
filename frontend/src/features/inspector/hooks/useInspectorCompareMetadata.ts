import { useCallback, useEffect, useMemo, useRef, useState } from 'react'
import type { Dispatch, SetStateAction } from 'react'
import { api } from '../../../api/client'
import {
  resolveCompareMetadataTargets,
  shouldApplyMetadataResponse,
} from './metadataRequestGuards'
import type { MetadataRecord, MetadataState } from './useInspectorMetadataTypes'

type UseInspectorCompareMetadataParams = {
  compareReady: boolean
  comparePaths: string[]
}

type UseInspectorCompareMetadataResult = {
  compareMetaState: MetadataState
  compareMetaError: string | null
  compareMetaByPath: Record<string, MetadataRecord>
  compareIncludePilInfo: boolean
  setCompareIncludePilInfo: Dispatch<SetStateAction<boolean>>
  reloadCompareMetadata: () => void
}

export function useInspectorCompareMetadata({
  compareReady,
  comparePaths,
}: UseInspectorCompareMetadataParams): UseInspectorCompareMetadataResult {
  const [compareMetaState, setCompareMetaState] = useState<MetadataState>('idle')
  const [compareMetaError, setCompareMetaError] = useState<string | null>(null)
  const [compareMetaByPath, setCompareMetaByPath] = useState<Record<string, MetadataRecord>>({})
  const [compareIncludePilInfo, setCompareIncludePilInfo] = useState(false)
  const compareTargets = useMemo(
    () => resolveCompareMetadataTargets(compareReady, comparePaths),
    [compareReady, comparePaths],
  )
  const compareContextKey = useMemo(
    () => (compareTargets.paths.length >= 2 ? compareTargets.paths.join('::') : null),
    [compareTargets.paths],
  )
  const compareMetaRequestIdRef = useRef(0)
  const activeCompareContextKeyRef = useRef<string | null>(compareContextKey)
  activeCompareContextKeyRef.current = compareContextKey

  const fetchCompareMetadata = useCallback(async (
    paths: string[],
    requestContextKey: string,
  ) => {
    const requestId = compareMetaRequestIdRef.current + 1
    compareMetaRequestIdRef.current = requestId
    setCompareMetaState('loading')
    setCompareMetaError(null)
    try {
      const responses = await Promise.all(paths.map((path) => api.getMetadata(path)))
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
      const nextMetadata: Record<string, MetadataRecord> = {}
      paths.forEach((path, idx) => {
        nextMetadata[path] = responses[idx].meta
      })
      setCompareMetaByPath(nextMetadata)
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
      setCompareMetaByPath({})
      setCompareMetaError(msg)
      setCompareMetaState('error')
    }
  }, [])

  useEffect(() => {
    compareMetaRequestIdRef.current += 1
    if (!compareContextKey || compareTargets.paths.length < 2) {
      setCompareMetaState('idle')
      setCompareMetaError(null)
      setCompareMetaByPath({})
      return
    }
    setCompareIncludePilInfo(false)
    void fetchCompareMetadata(compareTargets.paths, compareContextKey)
  }, [compareContextKey, compareTargets.paths, fetchCompareMetadata])

  const reloadCompareMetadata = useCallback(() => {
    if (!compareContextKey || compareTargets.paths.length < 2) return
    void fetchCompareMetadata(compareTargets.paths, compareContextKey)
  }, [compareContextKey, compareTargets.paths, fetchCompareMetadata])

  return {
    compareMetaState,
    compareMetaError,
    compareMetaByPath,
    compareIncludePilInfo,
    setCompareIncludePilInfo,
    reloadCompareMetadata,
  }
}
