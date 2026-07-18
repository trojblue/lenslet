import React, { useCallback, useEffect, useLayoutEffect, useMemo, useRef, useState } from 'react'
import { api } from '../../api/client'
import { useBlobResource } from '../../shared/hooks/useBlobUrl'
import { useModalFocusTrap } from '../../shared/hooks/useModalFocusTrap'
import { getHorizontalNavigationDelta, shouldHandleDialogNavigationKey } from '../../lib/keyboard'
import type { BrowseItemPayload } from '../../lib/types'
import { buildComparePairKey, shouldAutoFitComparePair } from './compareAutoFit'
import { useDividerDrag } from './hooks/useDividerDrag'
import { useCompareZoomPan } from './hooks/useCompareZoomPan'
import { directOriginalImageUrl, originalMediaUnsupportedReason } from '../media/originalImageResource'
import { browserDecodeMediaError, mediaErrorSummary, type MediaResourceError } from '../../lib/mediaResourceState'
import {
  comparePairCanCommit,
  compareResource,
  retainCurrentDecodedResourceIdentities,
  selectDecodedCompareResource,
  type CompareResource,
} from './comparePresentation'
import './compare.css'

interface CompareViewerProps {
  aItem: BrowseItemPayload | null
  bItem: BrowseItemPayload | null
  proxyHttpOriginals?: boolean
  index: number
  total: number
  canPrev: boolean
  canNext: boolean
  onNavigate: (delta: number) => void
  onClose: () => void
}

type ComparePairPresentation = {
  pairKey: string
  aItem: BrowseItemPayload
  bItem: BrowseItemPayload
  aResource: CompareResource | null
  bResource: CompareResource | null
  aLoadError: MediaResourceError | null
  bLoadError: MediaResourceError | null
  aUnsupported: string | null
  bUnsupported: string | null
  index: number
  total: number
}

type CompareDecodeError = {
  resourceIdentity: string
  error: MediaResourceError
}

type DecodeCandidateProps = {
  resource: CompareResource | null
  onDecoded: (resource: CompareResource) => void
  onError?: (resource: CompareResource) => void
}

function DecodeCandidate({ resource, onDecoded, onError }: DecodeCandidateProps) {
  if (!resource) return null
  return (
    <img
      key={resource.identity}
      src={resource.url}
      alt=""
      aria-hidden="true"
      className="compare-decode-candidate"
      onLoad={(event) => {
        const image = event.currentTarget
        void image.decode().then(
          () => {
            if (image.isConnected && (image.currentSrc || image.src) === resource.url) {
              onDecoded(resource)
            }
          },
          () => onError?.(resource),
        )
      }}
      onError={() => onError?.(resource)}
    />
  )
}

function useBoundCompareResource(
  path: string | null,
  url: string | null,
  kind: CompareResource['kind'],
): CompareResource | null {
  const [bound, setBound] = useState<CompareResource | null>(null)
  useLayoutEffect(() => {
    setBound(compareResource(path, url, kind))
    // A retained URL must stay bound to the path that produced it. A path-only
    // render deliberately does not rebind it before the resource hook advances.
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [kind, url])
  return bound?.path === path ? bound : null
}

function useBoundCompareError(
  path: string | null,
  error: MediaResourceError | null,
): MediaResourceError | null {
  const [bound, setBound] = useState<{ path: string; error: MediaResourceError } | null>(null)
  useLayoutEffect(() => {
    setBound(path && error ? { path, error } : null)
    // Like object URLs, retained errors belong to the request path that created
    // them and must not be projected onto a path-only render.
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [error])
  return bound?.path === path ? bound.error : null
}

export default function CompareViewer({
  aItem,
  bItem,
  proxyHttpOriginals = false,
  index,
  total,
  canPrev,
  canNext,
  onNavigate,
  onClose,
}: CompareViewerProps) {
  const overlayRef = useRef<HTMLDivElement | null>(null)
  const [splitPct, setSplitPct] = useState(50)
  const [loadedAPath, setLoadedAPath] = useState<string | null>(null)
  const [loadedBPath, setLoadedBPath] = useState<string | null>(null)
  const [errorA, setErrorA] = useState<CompareDecodeError | null>(null)
  const [errorB, setErrorB] = useState<CompareDecodeError | null>(null)
  const [directFailures, setDirectFailures] = useState<Set<string>>(() => new Set())
  const fittedPairKeyRef = useRef<string | null>(null)
  const userInteractedPairKeyRef = useRef<string | null>(null)
  const [decodedResourceIdentities, setDecodedResourceIdentities] = useState<Set<string>>(
    () => new Set(),
  )
  const [presentedPair, setPresentedPair] = useState<ComparePairPresentation | null>(null)
  const aTargetFullIdentityRef = useRef<string | null>(null)
  const bTargetFullIdentityRef = useRef<string | null>(null)
  const currentCandidateIdentitiesRef = useRef<Set<string>>(new Set())
  const aPath = aItem?.path ?? null
  const bPath = bItem?.path ?? null
  const pairKey = buildComparePairKey(aPath, bPath)
  const presentedPairKey = presentedPair?.pairKey ?? null
  const markCompareUserInteraction = useCallback(() => {
    userInteractedPairKeyRef.current = presentedPairKey ?? pairKey
  }, [pairKey, presentedPairKey])
  const {
    scale,
    baseA,
    baseB,
    txA,
    tyA,
    txB,
    tyB,
    dragging,
    containerRef,
    imgARef,
    imgBRef,
    fitAndCenter,
    resetView,
    handleWheel,
    handlePointerDown,
    handlePointerMove,
    handlePointerUp,
    handlePointerCancel,
  } = useCompareZoomPan({ onUserInteraction: markCompareUserInteraction })

  const handleDialogKeyDown = useModalFocusTrap(overlayRef, { onEscape: onClose })

  useLayoutEffect(() => {
    resetView()
    setLoadedAPath(null)
    setLoadedBPath(null)
    setErrorA(null)
    setErrorB(null)
    fittedPairKeyRef.current = null
    userInteractedPairKeyRef.current = null
  }, [aPath, bPath, resetView])

  useEffect(() => {
    const onKey = (e: KeyboardEvent) => {
      if (!shouldHandleDialogNavigationKey(e, overlayRef.current)) return
      const delta = getHorizontalNavigationDelta(e)
      if (delta === 1 && canNext) {
        e.preventDefault()
        onNavigate(delta)
        return
      }
      if (delta === -1 && canPrev) {
        e.preventDefault()
        onNavigate(delta)
      }
    }

    window.addEventListener('keydown', onKey)
    return () => window.removeEventListener('keydown', onKey)
  }, [onNavigate, canPrev, canNext])

  const aDirectUrl = directOriginalImageUrl(aItem, proxyHttpOriginals, directFailures)
  const bDirectUrl = directOriginalImageUrl(bItem, proxyHttpOriginals, directFailures)
  const aUnsupportedReason = aDirectUrl ? null : originalMediaUnsupportedReason(aItem)
  const bUnsupportedReason = bDirectUrl ? null : originalMediaUnsupportedReason(bItem)
  const aBlobResource = useBlobResource(
    aPath && !aDirectUrl && !aUnsupportedReason ? () => api.getFile(aPath) : null,
    [aPath, aDirectUrl, aUnsupportedReason],
    { source: 'proxy', unsupportedReason: aUnsupportedReason },
  )
  const bBlobResource = useBlobResource(
    bPath && !bDirectUrl && !bUnsupportedReason ? () => api.getFile(bPath) : null,
    [bPath, bDirectUrl, bUnsupportedReason],
    { source: 'proxy', unsupportedReason: bUnsupportedReason },
  )
  const aThumbBlobResource = useBlobResource(
    aPath ? () => api.getThumb(aPath) : null,
    [aPath],
    { source: 'thumbnail' },
  )
  const bThumbBlobResource = useBlobResource(
    bPath ? () => api.getThumb(bPath) : null,
    [bPath],
    { source: 'thumbnail' },
  )
  const aBlobUrl = aBlobResource.status === 'ready' ? aBlobResource.url : null
  const bBlobUrl = bBlobResource.status === 'ready' ? bBlobResource.url : null
  const aThumbUrl = aThumbBlobResource.status === 'ready' ? aThumbBlobResource.url : null
  const bThumbUrl = bThumbBlobResource.status === 'ready' ? bThumbBlobResource.url : null
  const boundABlobResource = useBoundCompareResource(aPath, aBlobUrl, 'full')
  const boundBBlobResource = useBoundCompareResource(bPath, bBlobUrl, 'full')
  const boundAThumbResource = useBoundCompareResource(aPath, aThumbUrl, 'thumbnail')
  const boundBThumbResource = useBoundCompareResource(bPath, bThumbUrl, 'thumbnail')
  const boundABlobError = useBoundCompareError(
    aPath,
    aBlobResource.status === 'error' ? aBlobResource.error : null,
  )
  const boundBBlobError = useBoundCompareError(
    bPath,
    bBlobResource.status === 'error' ? bBlobResource.error : null,
  )
  const aRetryLoad = aBlobResource.status === 'error' ? aBlobResource.retry : null
  const bRetryLoad = bBlobResource.status === 'error' ? bBlobResource.retry : null
  const aUnsupported = aUnsupportedReason
  const bUnsupported = bUnsupportedReason
  const aFullCandidate = aDirectUrl
    ? compareResource(aPath, aDirectUrl, 'full')
    : boundABlobResource
  const bFullCandidate = bDirectUrl
    ? compareResource(bPath, bDirectUrl, 'full')
    : boundBBlobResource
  const aThumbCandidate = boundAThumbResource
  const bThumbCandidate = boundBThumbResource
  useLayoutEffect(() => {
    currentCandidateIdentitiesRef.current = new Set(
      [aFullCandidate, aThumbCandidate, bFullCandidate, bThumbCandidate]
        .flatMap((resource) => resource ? [resource.identity] : []),
    )
    setDecodedResourceIdentities((prev) => {
      const retained = retainCurrentDecodedResourceIdentities(
        [aFullCandidate, aThumbCandidate, bFullCandidate, bThumbCandidate],
        prev,
      )
      if (retained.size === prev.size && [...retained].every((identity) => prev.has(identity))) {
        return prev
      }
      return retained
    })
  }, [
    aFullCandidate?.identity,
    aThumbCandidate?.identity,
    bFullCandidate?.identity,
    bThumbCandidate?.identity,
  ])
  const aLoadError = errorA && errorA.resourceIdentity === aFullCandidate?.identity
    ? errorA.error
    : boundABlobError
  const bLoadError = errorB && errorB.resourceIdentity === bFullCandidate?.identity
    ? errorB.error
    : boundBBlobError
  const aDecodedCandidate = selectDecodedCompareResource(
    aFullCandidate,
    aThumbCandidate,
    decodedResourceIdentities,
  )
  const bDecodedCandidate = selectDecodedCompareResource(
    bFullCandidate,
    bThumbCandidate,
    decodedResourceIdentities,
  )
  const aTerminal = Boolean(aLoadError || aUnsupported)
  const bTerminal = Boolean(bLoadError || bUnsupported)
  const targetPairCanCommit = comparePairCanCommit(
    aDecodedCandidate,
    bDecodedCandidate,
    aTerminal,
    bTerminal,
  )
  const markResourceDecoded = useCallback((resource: CompareResource) => {
    if (!currentCandidateIdentitiesRef.current.has(resource.identity)) return
    setDecodedResourceIdentities((prev) => {
      if (prev.has(resource.identity)) return prev
      const next = new Set(prev)
      next.add(resource.identity)
      return next
    })
  }, [])
  const markDirectImageFailed = useCallback((path: string | null, directUrl: string | null) => {
    if (!path || !directUrl) return
    setDirectFailures((prev) => {
      if (prev.has(path)) return prev
      const next = new Set(prev)
      next.add(path)
      return next
    })
  }, [])
  useLayoutEffect(() => {
    aTargetFullIdentityRef.current = aFullCandidate?.identity ?? null
    bTargetFullIdentityRef.current = bFullCandidate?.identity ?? null
  }, [aFullCandidate?.identity, bFullCandidate?.identity])
  const handleCandidateAFullError = useCallback((resource: CompareResource) => {
    if (aTargetFullIdentityRef.current !== resource.identity) return
    if (aDirectUrl === resource.url) {
      markDirectImageFailed(resource.path, resource.url)
      return
    }
    setErrorA({ resourceIdentity: resource.identity, error: browserDecodeMediaError() })
  }, [aDirectUrl, markDirectImageFailed])
  const handleCandidateBFullError = useCallback((resource: CompareResource) => {
    if (bTargetFullIdentityRef.current !== resource.identity) return
    if (bDirectUrl === resource.url) {
      markDirectImageFailed(resource.path, resource.url)
      return
    }
    setErrorB({ resourceIdentity: resource.identity, error: browserDecodeMediaError() })
  }, [bDirectUrl, markDirectImageFailed])

  useLayoutEffect(() => {
    if (!aItem || !bItem || !pairKey) {
      setPresentedPair(null)
      return
    }
    if (!targetPairCanCommit) return

    const next: ComparePairPresentation = {
      pairKey,
      aItem,
      bItem,
      aResource: aDecodedCandidate,
      bResource: bDecodedCandidate,
      aLoadError,
      bLoadError,
      aUnsupported,
      bUnsupported,
      index,
      total,
    }
    setPresentedPair((prev) => {
      if (
        prev?.pairKey === next.pairKey
        && prev.aResource?.identity === next.aResource?.identity
        && prev.bResource?.identity === next.bResource?.identity
        && prev.aLoadError === next.aLoadError
        && prev.bLoadError === next.bLoadError
        && prev.aUnsupported === next.aUnsupported
        && prev.bUnsupported === next.bUnsupported
        && prev.index === next.index
        && prev.total === next.total
      ) return prev
      return next
    })
  }, [
    aDecodedCandidate,
    aItem,
    aLoadError,
    aUnsupported,
    bDecodedCandidate,
    bItem,
    bLoadError,
    bUnsupported,
    index,
    pairKey,
    targetPairCanCommit,
    total,
  ])

  const presentedAPath = presentedPair?.aItem.path ?? null
  const presentedBPath = presentedPair?.bItem.path ?? null
  const presentedAResource = presentedPair?.aResource ?? null
  const presentedBResource = presentedPair?.bResource ?? null
  const aLabel = presentedPair?.aItem.name ?? presentedAPath ?? 'Select an image'
  const bLabel = presentedPair?.bItem.name ?? presentedBPath ?? 'Select another image'
  const presentedARetry = presentedAPath === aPath && presentedPair?.aLoadError?.retryable
    ? aRetryLoad
    : null
  const presentedBRetry = presentedBPath === bPath && presentedPair?.bLoadError?.retryable
    ? bRetryLoad
    : null
  const markImageAReady = useCallback(() => {
    const image = imgARef.current
    if (
      !presentedAPath
      || !presentedAResource
      || !image
      || (image.currentSrc || image.src) !== presentedAResource.url
    ) {
      return
    }
    setLoadedAPath(presentedAPath)
  }, [imgARef, presentedAPath, presentedAResource])
  const markImageBReady = useCallback(() => {
    const image = imgBRef.current
    if (
      !presentedBPath
      || !presentedBResource
      || !image
      || (image.currentSrc || image.src) !== presentedBResource.url
    ) {
      return
    }
    setLoadedBPath(presentedBPath)
  }, [imgBRef, presentedBPath, presentedBResource])
  useEffect(() => {
    if (!shouldAutoFitComparePair({
      aPath: presentedAPath,
      bPath: presentedBPath,
      loadedAPath,
      loadedBPath,
      fittedPairKey: fittedPairKeyRef.current,
      userInteracted: userInteractedPairKeyRef.current === presentedPairKey,
    })) return
    if (fitAndCenter()) {
      fittedPairKeyRef.current = presentedPairKey
    }
  }, [fitAndCenter, loadedAPath, loadedBPath, presentedAPath, presentedBPath, presentedPairKey])

  useEffect(() => {
    const image = imgARef.current
    if (image?.complete && image.naturalWidth > 0) {
      markImageAReady()
    }
  }, [markImageAReady, presentedAResource])

  useEffect(() => {
    const image = imgBRef.current
    if (image?.complete && image.naturalWidth > 0) {
      markImageBReady()
    }
  }, [markImageBReady, presentedBResource])

  const handleStagePointerDown = useCallback((e: React.PointerEvent<HTMLDivElement>) => {
    const target = e.target as HTMLElement | null
    if (
      target?.closest('.compare-label')
      || target?.closest('.compare-divider-hit')
      || target?.closest('.media-error-overlay')
    ) return
    handlePointerDown(e)
  }, [handlePointerDown])

  const handleStageWheel = useCallback((e: React.WheelEvent<HTMLDivElement>) => {
    markCompareUserInteraction()
    handleWheel(e)
  }, [handleWheel, markCompareUserInteraction])

  const handleStagePointerMove = useCallback((e: React.PointerEvent<HTMLDivElement>) => {
    if (e.buttons !== 0) markCompareUserInteraction()
    handlePointerMove(e)
  }, [handlePointerMove, markCompareUserInteraction])

  const getCompareStage = useCallback(() => containerRef.current, [containerRef])
  const handleDividerPointerDown = useDividerDrag({
    getStage: getCompareStage,
    setSplitPct,
    onUserInteraction: markCompareUserInteraction,
  })

  return (
    <div
      ref={overlayRef}
      role="dialog"
      aria-modal={true}
      aria-label="Compare images"
      data-compare-a-path={presentedAPath ?? undefined}
      data-compare-b-path={presentedBPath ?? undefined}
      data-compare-target-a-path={aPath ?? undefined}
      data-compare-target-b-path={bPath ?? undefined}
      data-compare-target-pair={pairKey}
      data-compare-presented-pair={presentedPairKey ?? ''}
      tabIndex={-1}
      className="toolbar-offset absolute inset-0 left-[var(--overlay-left)] right-[var(--overlay-right)] bg-panel z-viewer flex flex-col overflow-hidden"
      onKeyDown={handleDialogKeyDown}
    >
      <div className="compare-header flex items-center gap-3 px-3 py-2">
        <div className="text-[11px] uppercase tracking-wide text-muted">Compare</div>
        <div className="text-xs text-muted">
          {presentedPair && presentedPair.total >= 2
            ? `${presentedPair.index + 1}-${Math.min(presentedPair.index + 2, presentedPair.total)} of ${presentedPair.total}`
            : 'Select 2 images'}
        </div>
        <div className="ml-auto flex items-center gap-2">
          <button className="btn btn-sm" onClick={() => onNavigate(-1)} disabled={!canPrev} title="Previous (Left Arrow or A)">
            <svg width="12" height="12" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round" aria-hidden="true">
              <path d="M15 18l-6-6 6-6" />
            </svg>
            Prev
          </button>
          <button className="btn btn-sm" onClick={() => onNavigate(1)} disabled={!canNext} title="Next (Right Arrow or D)">
            Next
            <svg width="12" height="12" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round" aria-hidden="true">
              <path d="M9 18l6-6-6-6" />
            </svg>
          </button>
          <button className="btn btn-sm" onClick={onClose} title="Close (Esc)">
            <svg width="12" height="12" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round" aria-hidden="true">
              <path d="M18 6 6 18" />
              <path d="M6 6l12 12" />
            </svg>
            Close
          </button>
        </div>
      </div>
      <div className="flex-1 min-h-0 p-3 bg-panel">
        <div
          ref={containerRef}
          className={`compare-stage ${dragging ? 'is-dragging' : ''}`}
          onWheel={handleStageWheel}
          onPointerDown={handleStagePointerDown}
          onPointerMove={handleStagePointerMove}
          onPointerUp={handlePointerUp}
          onPointerCancel={handlePointerCancel}
        >
          {!aItem || !bItem ? (
            <div className="absolute inset-0 flex items-center justify-center text-sm text-muted">
              Select 2 images to compare.
            </div>
          ) : presentedPair ? (
            <>
              <div className="compare-label left-3">
                <span className="compare-label-tag">A</span>
                <span className="truncate" title={presentedPair.aItem.path}>{aLabel}</span>
              </div>
              <div className="compare-label right-3">
                <span className="compare-label-tag">B</span>
                <span className="truncate" title={presentedPair.bItem.path}>{bLabel}</span>
              </div>
              <div className="compare-layer" style={{ clipPath: `inset(0 ${100 - splitPct}% 0 0)` }}>
                {(presentedPair.aLoadError || presentedPair.aUnsupported) && (
                  <div className="media-error-overlay media-error-overlay-compare">
                    <div className="media-error-title">{presentedPair.aUnsupported ? 'Original unsupported' : 'Image A failed'}</div>
                    <div className="media-error-message">{presentedPair.aUnsupported ?? (presentedPair.aLoadError ? mediaErrorSummary(presentedPair.aLoadError) : '')}</div>
                    {presentedARetry && (
                      <button type="button" className="btn btn-xs" onClick={presentedARetry}>
                        Retry
                      </button>
                    )}
                  </div>
                )}
                {presentedAResource && !presentedPair.aLoadError && !presentedPair.aUnsupported && (
                  <img
                    ref={imgARef}
                    src={presentedAResource.url}
                    alt={`Compare image A: ${aLabel}`}
                    data-compare-image="a"
                    data-current-path={presentedAResource.path}
                    data-resource-kind={presentedAResource.kind}
                    className={`compare-image${presentedAResource.kind === 'thumbnail' ? ' compare-image-thumb' : ''}`}
                    draggable={false}
                    onDragStart={(e)=> e.preventDefault()}
                    onLoad={markImageAReady}
                    onError={presentedAResource.kind === 'full'
                      ? () => handleCandidateAFullError(presentedAResource)
                      : undefined}
                    style={{
                      transform: `translate(${txA}px, ${tyA}px) scale(${baseA * scale})`,
                      transformOrigin: '0 0',
                      opacity: presentedAResource.kind === 'full' ? 0.99 : 0.5,
                    }}
                  />
                )}
              </div>
              <div className="compare-layer" style={{ clipPath: `inset(0 0 0 ${splitPct}%)` }}>
                {(presentedPair.bLoadError || presentedPair.bUnsupported) && (
                  <div className="media-error-overlay media-error-overlay-compare">
                    <div className="media-error-title">{presentedPair.bUnsupported ? 'Original unsupported' : 'Image B failed'}</div>
                    <div className="media-error-message">{presentedPair.bUnsupported ?? (presentedPair.bLoadError ? mediaErrorSummary(presentedPair.bLoadError) : '')}</div>
                    {presentedBRetry && (
                      <button type="button" className="btn btn-xs" onClick={presentedBRetry}>
                        Retry
                      </button>
                    )}
                  </div>
                )}
                {presentedBResource && !presentedPair.bLoadError && !presentedPair.bUnsupported && (
                  <img
                    ref={imgBRef}
                    src={presentedBResource.url}
                    alt={`Compare image B: ${bLabel}`}
                    data-compare-image="b"
                    data-current-path={presentedBResource.path}
                    data-resource-kind={presentedBResource.kind}
                    className={`compare-image${presentedBResource.kind === 'thumbnail' ? ' compare-image-thumb' : ''}`}
                    draggable={false}
                    onDragStart={(e)=> e.preventDefault()}
                    onLoad={markImageBReady}
                    onError={presentedBResource.kind === 'full'
                      ? () => handleCandidateBFullError(presentedBResource)
                      : undefined}
                    style={{
                      transform: `translate(${txB}px, ${tyB}px) scale(${baseB * scale})`,
                      transformOrigin: '0 0',
                      opacity: presentedBResource.kind === 'full' ? 0.99 : 0.5,
                    }}
                  />
                )}
              </div>
              <div
                className="compare-divider-hit"
                style={{ left: `${splitPct}%` }}
                onPointerDown={handleDividerPointerDown}
              >
                <div className="compare-divider-line" />
                <div className="compare-divider-handle" />
              </div>
            </>
          ) : null}
          <DecodeCandidate
            resource={aFullCandidate}
            onDecoded={markResourceDecoded}
            onError={handleCandidateAFullError}
          />
          <DecodeCandidate
            resource={aThumbCandidate}
            onDecoded={markResourceDecoded}
          />
          <DecodeCandidate
            resource={bFullCandidate}
            onDecoded={markResourceDecoded}
            onError={handleCandidateBFullError}
          />
          <DecodeCandidate
            resource={bThumbCandidate}
            onDecoded={markResourceDecoded}
          />
        </div>
      </div>
    </div>
  )
}
