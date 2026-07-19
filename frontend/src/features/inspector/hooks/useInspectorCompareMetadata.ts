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
  enabled?: boolean
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
  enabled = true,
}: UseInspectorCompareMetadataParams): UseInspectorCompareMetadataResult {
  const [compareMetaState, setCompareMetaState] = useState<MetadataState>('idle')
  const [compareMetaError, setCompareMetaError] = useState<string | null>(null)
  const [compareMetaByPath, setCompareMetaByPath] = useState<Record<string, MetadataRecord>>({})
  const [compareMetaContextKey, setCompareMetaContextKey] = useState<string | null>(null)
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
  const activeRequestContextKeyRef = useRef<string | null>(null)
  const activeCompareContextKeyRef = useRef<string | null>(compareContextKey)
  activeCompareContextKeyRef.current = compareContextKey

  const fetchCompareMetadata = useCallback(async (
    paths: string[],
    requestContextKey: string,
  ) => {
    const requestId = compareMetaRequestIdRef.current + 1
    compareMetaRequestIdRef.current = requestId
    activeRequestContextKeyRef.current = requestContextKey
    setCompareMetaContextKey(requestContextKey)
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
    } finally {
      if (compareMetaRequestIdRef.current === requestId) {
        activeRequestContextKeyRef.current = null
      }
    }
  }, [])

  useEffect(() => {
    compareMetaRequestIdRef.current += 1
    activeRequestContextKeyRef.current = null
  }, [compareContextKey, enabled])

  useEffect(() => {
    if (!compareContextKey || compareTargets.paths.length < 2) {
      setCompareMetaState('idle')
      setCompareMetaError(null)
      setCompareMetaByPath({})
      setCompareMetaContextKey(null)
      return
    }
    if (!enabled) return
    if (
      compareMetaContextKey === compareContextKey
      && (compareMetaState === 'loaded' || compareMetaState === 'error')
    ) {
      return
    }
    if (activeRequestContextKeyRef.current === compareContextKey) return
    setCompareIncludePilInfo(false)
    void fetchCompareMetadata(compareTargets.paths, compareContextKey)
  }, [
    compareContextKey,
    compareMetaContextKey,
    compareMetaState,
    compareTargets.paths,
    enabled,
    fetchCompareMetadata,
  ])

  const reloadCompareMetadata = useCallback(() => {
    if (!enabled || !compareContextKey || compareTargets.paths.length < 2) return
    void fetchCompareMetadata(compareTargets.paths, compareContextKey)
  }, [compareContextKey, compareTargets.paths, enabled, fetchCompareMetadata])

  const contextMatches = compareMetaContextKey === compareContextKey
  const projectedState: MetadataState = !compareContextKey
    ? 'idle'
    : contextMatches
      ? compareMetaState
      : enabled
        ? 'loading'
        : 'idle'

  return {
    compareMetaState: projectedState,
    compareMetaError: contextMatches ? compareMetaError : null,
    compareMetaByPath: contextMatches ? compareMetaByPath : {},
    compareIncludePilInfo,
    setCompareIncludePilInfo,
    reloadCompareMetadata,
  }
}
