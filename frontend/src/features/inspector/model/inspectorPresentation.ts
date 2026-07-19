import type { BrowseItemPayload, Sidecar } from '../../../lib/types'
import type { MetadataRecord, MetadataState } from '../hooks/useInspectorMetadataTypes'

export type InspectorDependency<T> =
  | { status: 'pending' }
  | { status: 'ready'; value: T }
  | { status: 'error'; message: string; fallback: T }

export type InspectorPreviewPresentation =
  | { status: 'idle' }
  | { status: 'ready'; url: string }
  | { status: 'error'; message: string; retry: () => void }

export type InspectorMetadataPresentation = {
  raw: MetadataRecord
  error: string | null
  state: MetadataState
  showPilInfo: boolean
}

export type InspectorPresentationSnapshot = {
  resetKey: string
  identity: string
  path: string
  selectedPaths: string[]
  comparePaths: string[]
  items: BrowseItemPayload[]
  item: BrowseItemPayload | null
  itemError: string | null
  sidecar: Sidecar | null
  sidecarError: string | null
  metadata: InspectorMetadataPresentation
  preview: InspectorPreviewPresentation
}

export type InspectorTargetCandidate =
  | { status: 'idle'; identity: null; resetKey: string }
  | { status: 'pending'; identity: string; resetKey: string }
  | { status: 'ready'; identity: string; resetKey: string; snapshot: InspectorPresentationSnapshot }

export type StoredInspectorPresentation = {
  resetKey: string
  snapshot: InspectorPresentationSnapshot
}

type BuildInspectorTargetCandidateParams = {
  resetKey: string
  identity: string | null
  path: string | null
  selectedPaths: string[]
  comparePaths: string[]
  items: BrowseItemPayload[]
  item: InspectorDependency<BrowseItemPayload | null>
  sidecar: InspectorDependency<Sidecar | null>
  metadata: InspectorDependency<InspectorMetadataPresentation>
  preview: InspectorDependency<InspectorPreviewPresentation>
}

function dependencyValue<T>(dependency: Exclude<InspectorDependency<T>, { status: 'pending' }>): T {
  return dependency.status === 'ready' ? dependency.value : dependency.fallback
}

function dependencyError<T>(dependency: Exclude<InspectorDependency<T>, { status: 'pending' }>): string | null {
  return dependency.status === 'error' ? dependency.message : null
}

export function buildInspectorTargetCandidate({
  resetKey,
  identity,
  path,
  selectedPaths,
  comparePaths,
  items,
  item,
  sidecar,
  metadata,
  preview,
}: BuildInspectorTargetCandidateParams): InspectorTargetCandidate {
  if (!identity || !path) return { status: 'idle', identity: null, resetKey }
  if (
    item.status === 'pending'
    || sidecar.status === 'pending'
    || metadata.status === 'pending'
    || preview.status === 'pending'
  ) {
    return { status: 'pending', identity, resetKey }
  }
  return {
    status: 'ready',
    identity,
    resetKey,
    snapshot: {
      resetKey,
      identity,
      path,
      selectedPaths,
      comparePaths,
      items,
      item: dependencyValue(item),
      itemError: dependencyError(item),
      sidecar: dependencyValue(sidecar),
      sidecarError: dependencyError(sidecar),
      metadata: dependencyValue(metadata),
      preview: dependencyValue(preview),
    },
  }
}

export function selectInspectorPresentation(
  stored: StoredInspectorPresentation | null,
  candidate: InspectorTargetCandidate,
  resetKey: string,
): InspectorPresentationSnapshot | null {
  if (candidate.status === 'idle') return null
  if (candidate.resetKey !== resetKey) return null
  if (candidate.status === 'ready') return candidate.snapshot
  if (stored?.resetKey !== resetKey) return null
  return stored.snapshot
}

export function inspectorPresentationIsTransitioning(
  candidate: InspectorTargetCandidate,
  presented: InspectorPresentationSnapshot | null,
): boolean {
  return candidate.status === 'pending' && presented?.identity !== candidate.identity
}
