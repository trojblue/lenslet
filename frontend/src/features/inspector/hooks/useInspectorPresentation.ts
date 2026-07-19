import { useCallback, useEffect, useMemo, useRef, useState } from 'react'
import { useItemDetail, useSidecar } from '../../../api/items'
import { api } from '../../../api/client'
import {
  browserDecodeMediaError,
  mediaErrorFromUnknown,
  mediaErrorSummary,
} from '../../../lib/mediaResourceState'
import type { BrowseItemPayload, Sidecar } from '../../../lib/types'
import { decodeThumbnailBeforeReveal } from '../../browse/model/thumbnailReveal'
import {
  thumbnailObjectUrlCache,
  type ThumbnailObjectUrlLease,
} from '../../browse/model/thumbnailObjectUrlCache'
import {
  buildInspectorTargetCandidate,
  inspectorPresentationIsTransitioning,
  selectInspectorPresentation,
  type InspectorDependency,
  type InspectorMetadataPresentation,
  type InspectorPresentationSnapshot,
  type InspectorPreviewPresentation,
  type StoredInspectorPresentation,
} from '../model/inspectorPresentation'
import { useInspectorSingleMetadata } from './useInspectorSingleMetadata'

type PreviewCandidate =
  | { path: null; status: 'idle' }
  | { path: string; status: 'pending'; resourceKey: string }
  | { path: string; status: 'staging'; resourceKey: string; url: string }
  | { path: string; status: 'ready'; resourceKey: string; url: string }
  | { path: string; status: 'error'; resourceKey: string; message: string; retry: () => void }

export type InspectorPreviewStage = {
  path: string
  url: string
}

type UseInspectorPresentationParams = {
  path: string | null
  selectedPaths: string[]
  comparePaths: string[]
  items: BrowseItemPayload[]
  resetKey: string
  visible: boolean
  autoloadMetadata: boolean
}

type UseInspectorPresentationResult = {
  presentation: InspectorPresentationSnapshot | null
  requestedIdentity: string | null
  transitioning: boolean
  showMetadataLoadingCopy: boolean
  previewStage: InspectorPreviewStage | null
  decodeTargetPreview: (image: HTMLImageElement, stage: InspectorPreviewStage) => void
  failTargetPreview: (stage: InspectorPreviewStage) => void
  setTargetMetadataError: ReturnType<typeof useInspectorSingleMetadata>['setMetaError']
  setTargetShowPilInfo: ReturnType<typeof useInspectorSingleMetadata>['setShowPilInfo']
  fetchTargetMetadata: ReturnType<typeof useInspectorSingleMetadata>['fetchMetadata']
}

function errorMessage(error: unknown, fallback: string): string {
  if (error instanceof Error && error.message) return error.message
  return fallback
}

function useDecodedInspectorPreview(
  path: string | null,
  enabled: boolean,
  retainedPath: string | null,
  scopeKey: string,
): {
  candidate: PreviewCandidate
  stage: InspectorPreviewStage | null
  decodeStage: (image: HTMLImageElement, stage: InspectorPreviewStage) => void
  failStage: (stage: InspectorPreviewStage) => void
} {
  const leasesRef = useRef(new Map<string, ThumbnailObjectUrlLease>())
  const requestIdRef = useRef(0)
  const [retryToken, setRetryToken] = useState(0)
  const retry = useCallback(() => setRetryToken((token) => token + 1), [])
  const [candidate, setCandidate] = useState<PreviewCandidate>({ path: null, status: 'idle' })
  const candidateRef = useRef(candidate)
  candidateRef.current = candidate
  const resourceKey = path ? JSON.stringify([scopeKey, path]) : null
  const retainedKey = retainedPath ? JSON.stringify([scopeKey, retainedPath]) : null

  const failStage = useCallback((stage: InspectorPreviewStage) => {
    const current = candidateRef.current
    if (current.status !== 'staging' || current.path !== stage.path || current.url !== stage.url) return
    const failedLease = leasesRef.current.get(current.resourceKey)
    if (failedLease) {
      thumbnailObjectUrlCache.evictPrefix(current.resourceKey)
      failedLease.release()
      leasesRef.current.delete(current.resourceKey)
    }
    setCandidate({
      path: stage.path,
      status: 'error',
      resourceKey: current.resourceKey,
      message: mediaErrorSummary(browserDecodeMediaError()),
      retry,
    })
  }, [retry])

  const decodeStage = useCallback((image: HTMLImageElement, stage: InspectorPreviewStage) => {
    void decodeThumbnailBeforeReveal(image).then(() => {
      const current = candidateRef.current
      if (
        current.status !== 'staging'
        || current.path !== stage.path
        || current.url !== stage.url
        || !image.naturalWidth
        || !image.naturalHeight
      ) {
        if (!image.naturalWidth || !image.naturalHeight) failStage(stage)
        return
      }
      leasesRef.current.get(current.resourceKey)?.markDecoded()
      setCandidate({
        path: current.path,
        status: 'ready',
        resourceKey: current.resourceKey,
        url: current.url,
      })
    }).catch(() => failStage(stage))
  }, [failStage])

  useEffect(() => {
    for (const [leasedKey, lease] of leasesRef.current) {
      if (leasedKey === resourceKey || leasedKey === retainedKey) continue
      lease.release()
      leasesRef.current.delete(leasedKey)
    }
    if (!path || !resourceKey || !enabled) return
    const existingLease = leasesRef.current.get(resourceKey)
      ?? thumbnailObjectUrlCache.acquireExisting(resourceKey)
    if (existingLease && !leasesRef.current.has(resourceKey)) {
      leasesRef.current.set(resourceKey, existingLease)
    }
    if (existingLease) {
      const current = candidateRef.current
      if (current.status === 'ready' && current.path === path && current.url === existingLease.url) return
      setCandidate({ path, status: 'staging', resourceKey, url: existingLease.url })
      return
    }
    const requestId = requestIdRef.current + 1
    requestIdRef.current = requestId
    let alive = true
    setCandidate({ path, status: 'pending', resourceKey })

    void (async () => {
      const lease = existingLease
        ?? thumbnailObjectUrlCache.acquire(resourceKey, await api.getThumb(path))
      if (!leasesRef.current.has(resourceKey)) leasesRef.current.set(resourceKey, lease)
      if (!alive || requestIdRef.current !== requestId) {
        lease.release()
        if (leasesRef.current.get(resourceKey) === lease) leasesRef.current.delete(resourceKey)
        return
      }
      setCandidate({ path, status: 'staging', resourceKey, url: lease.url })
    })().catch((error) => {
      if (!alive || requestIdRef.current !== requestId) return
      const failedLease = leasesRef.current.get(resourceKey)
      if (failedLease) {
        thumbnailObjectUrlCache.evictPrefix(resourceKey)
        failedLease.release()
        leasesRef.current.delete(resourceKey)
      }
      const mediaError = error && typeof error === 'object' && 'category' in error
        ? error
        : mediaErrorFromUnknown(error, 'Preview failed to load.')
      setCandidate({
        path,
        status: 'error',
        resourceKey,
        message: mediaErrorSummary(mediaError as ReturnType<typeof mediaErrorFromUnknown>),
        retry,
      })
    })
    return () => {
      alive = false
    }
  }, [enabled, path, resourceKey, retainedKey, retry, retryToken])

  useEffect(() => () => {
    requestIdRef.current += 1
    for (const lease of leasesRef.current.values()) lease.release()
    leasesRef.current.clear()
  }, [])

  const candidateMatchesTarget = candidate.status !== 'idle'
    && candidate.path === path
    && candidate.resourceKey === resourceKey
  const projectedCandidate: PreviewCandidate = !path || !resourceKey
    ? { path: null, status: 'idle' }
    : !enabled
      ? { path, status: 'pending', resourceKey }
      : candidateMatchesTarget
        ? candidate
        : { path, status: 'pending', resourceKey }
  const stage = candidateMatchesTarget && (candidate.status === 'staging' || candidate.status === 'ready')
    ? { path: candidate.path, url: candidate.url }
    : null
  return { candidate: projectedCandidate, stage, decodeStage, failStage }
}

export function useInspectorPresentation({
  path,
  selectedPaths,
  comparePaths,
  items,
  resetKey,
  visible,
  autoloadMetadata,
}: UseInspectorPresentationParams): UseInspectorPresentationResult {
  const multi = selectedPaths.length > 1
  const sidecarQuery = useSidecar(path ?? '', visible && !multi, resetKey)
  const itemDetailQuery = useItemDetail(path ?? '', visible, resetKey)
  const metadataTarget = useInspectorSingleMetadata({
    path,
    autoloadMetadata: autoloadMetadata && visible && selectedPaths.length <= 1,
    scopeKey: resetKey,
  })
  const [stored, setStored] = useState<StoredInspectorPresentation | null>(null)
  const storedForReset = stored?.resetKey === resetKey ? stored : null
  const requestedIdentity = path
    ? JSON.stringify([resetKey, path, selectedPaths, comparePaths])
    : null
  const previewResource = useDecodedInspectorPreview(
    path,
    visible && !multi,
    storedForReset?.snapshot.path ?? null,
    resetKey,
  )
  const previewTarget = previewResource.candidate
  const fallbackItem = items.find((item) => item.path === path) ?? null
  const previewUrl = previewTarget.status === 'ready' ? previewTarget.url : null
  const previewMessage = previewTarget.status === 'error' ? previewTarget.message : null
  const previewRetry = previewTarget.status === 'error' ? previewTarget.retry : null
  const targetPreviewDependency = useMemo<InspectorDependency<InspectorPreviewPresentation>>(() => {
    if (multi) return { status: 'ready', value: { status: 'idle' } }
    if (previewTarget.status === 'ready' && previewUrl) {
      return { status: 'ready', value: { status: 'ready', url: previewUrl } }
    }
    if (previewTarget.status === 'error' && previewMessage && previewRetry) {
      return {
        status: 'error',
        message: previewMessage,
        fallback: { status: 'error', message: previewMessage, retry: previewRetry },
      }
    }
    return { status: 'pending' }
  }, [multi, previewMessage, previewRetry, previewTarget.status, previewUrl])

  const candidate = useMemo(() => {
    const itemDependency: InspectorDependency<BrowseItemPayload | null> = !visible
      ? { status: 'pending' }
      : itemDetailQuery.isError
        ? {
          status: 'error',
          message: errorMessage(itemDetailQuery.error, 'Item details failed to load.'),
          fallback: fallbackItem,
        }
        : itemDetailQuery.data?.path === path
          ? { status: 'ready', value: itemDetailQuery.data }
          : { status: 'pending' }
    const sidecarDependency: InspectorDependency<Sidecar | null> = multi
      ? { status: 'ready', value: null }
      : !visible
        ? { status: 'pending' }
        : sidecarQuery.isError
          ? {
            status: 'error',
            message: errorMessage(sidecarQuery.error, 'Notes and tags failed to load.'),
            fallback: null,
          }
          : sidecarQuery.data
            ? { status: 'ready', value: sidecarQuery.data }
            : { status: 'pending' }
    const metadataValue: InspectorMetadataPresentation = {
      raw: metadataTarget.metaRaw,
      error: metadataTarget.metaError,
      state: metadataTarget.metaState,
      showPilInfo: metadataTarget.showPilInfo,
    }
    let metadataDependency: InspectorDependency<InspectorMetadataPresentation>
    if (multi || !autoloadMetadata) {
      metadataDependency = { status: 'ready', value: metadataValue }
    } else if (!visible || metadataTarget.metaState === 'loading' || metadataTarget.metaState === 'idle') {
      metadataDependency = { status: 'pending' }
    } else if (metadataTarget.metaState === 'error') {
      metadataDependency = {
        status: 'error',
        message: metadataTarget.metaError ?? 'Metadata failed to load.',
        fallback: metadataValue,
      }
    } else {
      metadataDependency = { status: 'ready', value: metadataValue }
    }

    return buildInspectorTargetCandidate({
      resetKey,
      identity: requestedIdentity,
      path,
      selectedPaths,
      comparePaths,
      items,
      item: itemDependency,
      sidecar: sidecarDependency,
      metadata: metadataDependency,
      preview: targetPreviewDependency,
    })
  }, [
    autoloadMetadata,
    comparePaths,
    fallbackItem,
    itemDetailQuery.data,
    itemDetailQuery.error,
    itemDetailQuery.isError,
    items,
    metadataTarget.metaError,
    metadataTarget.metaRaw,
    metadataTarget.metaState,
    metadataTarget.showPilInfo,
    multi,
    path,
    requestedIdentity,
    resetKey,
    selectedPaths,
    sidecarQuery.data,
    sidecarQuery.error,
    sidecarQuery.isError,
    targetPreviewDependency,
    visible,
  ])
  const presentation = selectInspectorPresentation(stored, candidate, resetKey)
  const transitioning = inspectorPresentationIsTransitioning(candidate, presentation)

  useEffect(() => {
    if (candidate.status === 'idle') {
      setStored(null)
      return
    }
    if (candidate.status !== 'ready') return
    setStored((current) => (
      current?.resetKey === resetKey && current.snapshot === candidate.snapshot
        ? current
        : { resetKey, snapshot: candidate.snapshot }
    ))
  }, [candidate, resetKey])

  return useMemo(() => ({
    presentation,
    requestedIdentity,
    transitioning,
    showMetadataLoadingCopy: transitioning && metadataTarget.showMetadataLoadingCopy,
    previewStage: previewResource.stage,
    decodeTargetPreview: previewResource.decodeStage,
    failTargetPreview: previewResource.failStage,
    setTargetMetadataError: metadataTarget.setMetaError,
    setTargetShowPilInfo: metadataTarget.setShowPilInfo,
    fetchTargetMetadata: metadataTarget.fetchMetadata,
  }), [
    metadataTarget.fetchMetadata,
    metadataTarget.setMetaError,
    metadataTarget.setShowPilInfo,
    metadataTarget.showMetadataLoadingCopy,
    presentation,
    previewResource.decodeStage,
    previewResource.failStage,
    previewResource.stage,
    previewTarget,
    requestedIdentity,
    transitioning,
  ])
}
