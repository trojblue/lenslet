import React, { useEffect, useMemo, useCallback } from 'react'
import { useQueryClient } from '@tanstack/react-query'
import { useSidecar, useUpdateSidecar, bulkUpdateSidecars, queueSidecarUpdate, useSidecarConflict } from '../../shared/api/items'
import { api, makeIdempotencyKey } from '../../shared/api/client'
import { useBlobUrl } from '../../shared/hooks/useBlobUrl'
import type { Item, SortSpec, StarRating } from '../../lib/types'
import { isInputElement } from '../../lib/keyboard'
import {
  buildMetadataPathCopyPayload,
  buildJsonRenderNode,
  buildCompareMetadataDiffFromNormalized,
  buildDisplayMetadataFromNormalized,
  hasPilInfoMetadata,
  normalizeMetadataRecord,
} from './model/metadataCompare'
import { BasicsSection } from './sections/BasicsSection'
import { CompareMetadataSection } from './sections/CompareMetadataSection'
import { MetadataSection } from './sections/MetadataSection'
import { NotesSection } from './sections/NotesSection'
import { OverviewSection } from './sections/OverviewSection'
import { useInspectorMetadataWorkflow } from './hooks/useInspectorMetadataWorkflow'
import { useInspectorSidecarWorkflow } from './hooks/useInspectorSidecarWorkflow'
import { useInspectorUiState } from './hooks/useInspectorUiState'

// S0/T1 seam anchors (see docs/dev_notes/20260211_s0_t1_seam_map.md):
// - T16 model extraction: metadata normalization/flattening and compare diff helpers.
// - T17 section extraction: InspectorSection plus typed overview/compare/basics/metadata/notes blocks.
// - T18 async hook extraction: metadata/compare/export async workflow and sidecar typing/conflict hooks.
// - T19 render optimization: compare diff + metadata display memoization boundaries.

interface InspectorItem {
  path: string
  size: number
  w: number
  h: number
  type: string
  source?: string | null
  star?: StarRating | null
  metrics?: Record<string, number | null> | null
}

interface InspectorProps {
  path: string | null
  selectedPaths?: string[]
  items?: InspectorItem[]
  compareActive?: boolean
  compareA?: Item | null
  compareB?: Item | null
  onOpenCompare?: () => void
  onResize?: (e: React.PointerEvent<HTMLDivElement>) => void
  onStarChanged?: (paths: string[], val: StarRating) => void
  sortSpec?: SortSpec
  onFindSimilar?: () => void
  embeddingsAvailable?: boolean
  embeddingsLoading?: boolean
  compareExportSupportsV2?: boolean
  compareExportMaxPathsV2?: number | null
  onLocalTypingChange?: (active: boolean) => void
}

const METRICS_PREVIEW_LIMIT = 12
const COMPARE_DIFF_LIMIT = 120
const COMPARE_DIFF_MAX_DEPTH = 8
const COMPARE_DIFF_MAX_ARRAY = 80

export default function Inspector({
  path,
  selectedPaths = [],
  items = [],
  compareActive = false,
  compareA = null,
  compareB = null,
  onOpenCompare,
  onResize,
  onStarChanged,
  sortSpec,
  onFindSimilar,
  embeddingsAvailable = false,
  embeddingsLoading = false,
  compareExportSupportsV2 = false,
  compareExportMaxPathsV2 = null,
  onLocalTypingChange,
}: InspectorProps) {
  const enabled = !!path
  const { data } = useSidecar(path ?? '')
  const mut = useUpdateSidecar(path ?? '')
  const qc = useQueryClient()

  const multi = selectedPaths.length > 1

  const canFindSimilar = !!onFindSimilar && embeddingsAvailable && !multi
  const findSimilarDisabledReason = (() => {
    if (!onFindSimilar) return null
    if (!embeddingsAvailable) return embeddingsLoading ? 'Loading embeddings...' : 'No embeddings detected.'
    if (multi) return 'Select a single image to search.'
    return null
  })()

  // Get star from item list (optimistic local value) or sidecar
  const itemStarFromList = useMemo((): StarRating | null => {
    const star = items.find((i) => i.path === path)?.star
    return star ?? null
  }, [items, path])
  
  const star = itemStarFromList ?? data?.star ?? null
  const conflict = useSidecarConflict(!multi ? path : null)

  const comparePathA = compareA?.path ?? null
  const comparePathB = compareB?.path ?? null
  const compareReady = compareActive && !!comparePathA && !!comparePathB
  const {
    openSections,
    toggleOverviewSection,
    toggleCompareSection,
    toggleBasicsSection,
    toggleMetadataSection,
    toggleNotesSection,
    metricsExpanded,
    toggleMetricsExpanded,
    copiedField,
    markInfoCopied,
    metaCopied,
    markMetadataCopied,
    metaValueCopiedPath,
    markMetadataValueCopied,
    compareMetaCopied,
    markCompareMetadataCopied,
    compareValueCopiedPathA,
    compareValueCopiedPathB,
    markCompareMetadataValueCopied,
  } = useInspectorUiState({
    path,
    sidecarUpdatedAt: data?.updated_at,
    comparePathA,
    comparePathB,
    compareReady,
  })
  const compareSectionOpen = compareReady && compareActive && openSections.compare
  const metadataSectionOpen = !multi && openSections.metadata
  const compareLabelA = compareA?.name ?? comparePathA ?? 'A'
  const compareLabelB = compareB?.name ?? comparePathB ?? 'B'

  const mutateSidecar = useCallback(
    (patch: { notes?: string; tags?: string[]; star?: StarRating | null }, baseVersion: number) => {
      mut.mutate({ patch, baseVersion, idempotencyKey: makeIdempotencyKey('patch') })
    },
    [mut],
  )

  const {
    tags,
    notes,
    conflictFields,
    commitSidecar,
    applyConflict,
    keepTheirs,
    handleNotesChange,
    handleNotesBlur,
    handleTagsChange,
    handleTagsBlur,
  } = useInspectorSidecarWorkflow({
    path,
    selectedPaths,
    multi,
    sidecar: data,
    conflict,
    star,
    queryClient: qc,
    mutateSidecar,
    onStarChanged,
    onLocalTypingChange,
  })

  const {
    metaRaw,
    metaError,
    metaState,
    showPilInfo,
    setMetaError,
    compareMetaState,
    compareMetaError,
    compareMetaA,
    compareMetaB,
    compareIncludePilInfo,
    compareShowPilInfoA,
    compareShowPilInfoB,
    compareExportLabelsText,
    compareExportEmbedMetadata,
    compareExportMode,
    compareExportError,
    compareExportBusy,
    setShowPilInfo,
    setCompareIncludePilInfo,
    setCompareShowPilInfoA,
    setCompareShowPilInfoB,
    fetchMetadata,
    reloadCompareMetadata,
    handleCompareExportLabelsTextChange,
    handleCompareExportEmbedMetadataChange,
    runComparisonExport,
  } = useInspectorMetadataWorkflow({
    path,
    sidecarUpdatedAt: data?.updated_at,
    selectedPaths,
    compareReady,
    comparePathA,
    comparePathB,
    compareExportSupportsV2,
    compareExportMaxPathsV2,
  })
  
  const selectedItems = useMemo(() => {
    const set = new Set(selectedPaths)
    return items.filter((i) => set.has(i.path))
  }, [items, selectedPaths])
  
  const totalSize = useMemo(
    () => selectedItems.reduce((acc, it) => acc + (it.size || 0), 0),
    [selectedItems]
  )

  // Keyboard shortcuts for star ratings (0-5)
  useEffect(() => {
    if (!path) return
    
    const onKey = (e: KeyboardEvent) => {
      if (isInputElement(e.target)) return
      
      const k = e.key
      if (!/^[0-5]$/.test(k)) return
      
      e.preventDefault()
      const val: StarRating = k === '0' ? null : (Number(k) as 1 | 2 | 3 | 4 | 5)
      
      if (multi && selectedPaths.length) {
        commitSidecar({ star: val })
        onStarChanged?.(selectedPaths, val)
        return
      }
      commitSidecar({ star: val })
      onStarChanged?.([path], val)
    }
    
    window.addEventListener('keydown', onKey)
    return () => window.removeEventListener('keydown', onKey)
  }, [path, multi, selectedPaths, commitSidecar, onStarChanged])

  const thumbUrl = useBlobUrl(path ? () => api.getThumb(path) : null, [path])

  const filename = path ? path.split('/').pop() || path : ''
  const ext = useMemo(() => {
    if (filename.includes('.')) {
      return filename.slice(filename.lastIndexOf('.') + 1).toUpperCase()
    }
    const it = items.find((i) => i.path === path)
    if (it?.type?.includes('/')) {
      return it.type.split('/')[1].toUpperCase()
    }
    return ''
  }, [filename, items, path])
  
  const currentItem = useMemo(
    () => items.find((i) => i.path === path),
    [items, path]
  )
  const sourceValue = useMemo(() => {
    if (!path) return ''
    return currentItem?.source ?? path
  }, [currentItem, path])

  const metaRawText = useMemo(() => {
    if (!metaRaw) return ''
    try {
      return JSON.stringify(metaRaw, null, 1)
    } catch {
      return ''
    }
  }, [metaRaw])

  const normalizedMetaRaw = useMemo(() => normalizeMetadataRecord(metaRaw), [metaRaw])
  const normalizedCompareMetaA = useMemo(() => normalizeMetadataRecord(compareMetaA), [compareMetaA])
  const normalizedCompareMetaB = useMemo(() => normalizeMetadataRecord(compareMetaB), [compareMetaB])

  const metaDisplayValue = useMemo(
    () => buildDisplayMetadataFromNormalized(normalizedMetaRaw, showPilInfo),
    [normalizedMetaRaw, showPilInfo],
  )

  const compareMetaRawTextA = useMemo(() => {
    if (!compareMetaA) return ''
    try {
      return JSON.stringify(compareMetaA, null, 1)
    } catch {
      return ''
    }
  }, [compareMetaA])

  const compareMetaRawTextB = useMemo(() => {
    if (!compareMetaB) return ''
    try {
      return JSON.stringify(compareMetaB, null, 1)
    } catch {
      return ''
    }
  }, [compareMetaB])

  const compareDisplayValueA = useMemo(
    () => buildDisplayMetadataFromNormalized(normalizedCompareMetaA, compareShowPilInfoA),
    [normalizedCompareMetaA, compareShowPilInfoA],
  )

  const compareDisplayValueB = useMemo(
    () => buildDisplayMetadataFromNormalized(normalizedCompareMetaB, compareShowPilInfoB),
    [normalizedCompareMetaB, compareShowPilInfoB],
  )

  const copyMetadata = useCallback(() => {
    if (!metaRawText) return
    navigator.clipboard?.writeText(metaRawText).then(() => {
      markMetadataCopied()
    }).catch((err) => {
      const msg = err instanceof Error ? err.message : 'Copy failed'
      setMetaError(msg)
    })
  }, [markMetadataCopied, metaRawText, setMetaError])

  const metaDisplayNode = useMemo(() => {
    if (!metadataSectionOpen || !metaDisplayValue) return null
    return buildJsonRenderNode(metaDisplayValue)
  }, [metadataSectionOpen, metaDisplayValue])

  const compareDisplayNodeA = useMemo(() => {
    if (!compareSectionOpen || !compareDisplayValueA) return null
    return buildJsonRenderNode(compareDisplayValueA)
  }, [compareSectionOpen, compareDisplayValueA])

  const compareDisplayNodeB = useMemo(() => {
    if (!compareSectionOpen || !compareDisplayValueB) return null
    return buildJsonRenderNode(compareDisplayValueB)
  }, [compareSectionOpen, compareDisplayValueB])

  const copyMetadataValue = useCallback((pathLabel: string, copyText: string) => {
    navigator.clipboard?.writeText(copyText).then(() => {
      markMetadataValueCopied(pathLabel)
    }).catch(() => {})
  }, [markMetadataValueCopied])

  const copyCompareMetadataValue = useCallback(
    (side: 'A' | 'B', pathLabel: string, copyText: string) => {
      navigator.clipboard?.writeText(copyText).then(() => {
        markCompareMetadataValueCopied(side, pathLabel)
      }).catch(() => {})
    },
    [markCompareMetadataValueCopied],
  )

  const handleMetaPathCopy = useCallback((path: Array<string | number>) => {
    if (!metaDisplayValue) return
    const payload = buildMetadataPathCopyPayload(metaDisplayValue, path)
    copyMetadataValue(payload.pathLabel, payload.copyText)
  }, [metaDisplayValue, copyMetadataValue])

  const handleCompareMetaPathCopyA = useCallback((path: Array<string | number>) => {
    if (!compareDisplayValueA) return
    const payload = buildMetadataPathCopyPayload(compareDisplayValueA, path)
    copyCompareMetadataValue('A', payload.pathLabel, payload.copyText)
  }, [compareDisplayValueA, copyCompareMetadataValue])

  const handleCompareMetaPathCopyB = useCallback((path: Array<string | number>) => {
    if (!compareDisplayValueB) return
    const payload = buildMetadataPathCopyPayload(compareDisplayValueB, path)
    copyCompareMetadataValue('B', payload.pathLabel, payload.copyText)
  }, [compareDisplayValueB, copyCompareMetadataValue])

  const copyCompareMetadata = useCallback((side: 'A' | 'B') => {
    const raw = side === 'A' ? compareMetaRawTextA : compareMetaRawTextB
    if (!raw) return
    navigator.clipboard?.writeText(raw).then(() => {
      markCompareMetadataCopied(side)
    }).catch(() => {})
  }, [compareMetaRawTextA, compareMetaRawTextB, markCompareMetadataCopied])

  let metaContent = metaDisplayValue ? '' : 'PNG metadata not loaded yet.'
  if (metaState === 'loading') {
    metaContent = 'Loading metadata…'
  } else if (metaState === 'error' && metaError) {
    metaContent = metaError
  }
  let compareMetaContent = 'Metadata not loaded yet.'
  if (compareMetaState === 'loading') {
    compareMetaContent = 'Loading metadata…'
  } else if (compareMetaState === 'error' && compareMetaError) {
    compareMetaContent = compareMetaError
  }
  const metadataLoading = metaState === 'loading'
  const metaLoaded = metaState === 'loaded' && !!metaRawText
  const metaHeightClass = metaLoaded ? 'h-48' : 'h-24'
  let metadataActionLabel = 'Load meta'
  if (metadataLoading) {
    metadataActionLabel = 'Loading…'
  } else if (metaLoaded) {
    metadataActionLabel = metaCopied ? 'Copied' : 'Copy'
  }
  const handleMetadataAction = metaLoaded ? copyMetadata : fetchMetadata

  const hasPilInfo = hasPilInfoMetadata(metaRaw)
  const compareHasPilInfoA = hasPilInfoMetadata(compareMetaA)
  const compareHasPilInfoB = hasPilInfoMetadata(compareMetaB)

  const compareDiff = useMemo(() => {
    if (!compareSectionOpen) return null
    return buildCompareMetadataDiffFromNormalized(normalizedCompareMetaA, normalizedCompareMetaB, {
      includePilInfo: compareIncludePilInfo,
      limit: COMPARE_DIFF_LIMIT,
      maxDepth: COMPARE_DIFF_MAX_DEPTH,
      maxArray: COMPARE_DIFF_MAX_ARRAY,
    })
  }, [compareSectionOpen, normalizedCompareMetaA, normalizedCompareMetaB, compareIncludePilInfo])

  const copyInfo = useCallback((key: string, text: string) => {
    if (!text) return
    navigator.clipboard?.writeText(text).then(() => {
      markInfoCopied(key)
    }).catch(() => {})
  }, [markInfoCopied])

  const handleSelectStar = useCallback((value: StarRating) => {
    if (multi && selectedPaths.length) {
      onStarChanged?.(selectedPaths, value)
      bulkUpdateSidecars(selectedPaths, { star: value })
      return
    }
    if (!path) return
    onStarChanged?.([path], value)
    queueSidecarUpdate(path, { star: value })
  }, [multi, onStarChanged, path, selectedPaths])

  const handleToggleShowPilInfo = useCallback(() => {
    setShowPilInfo((prev) => !prev)
  }, [setShowPilInfo])
  const handleToggleCompareIncludePilInfo = useCallback(() => {
    setCompareIncludePilInfo((prev) => !prev)
  }, [setCompareIncludePilInfo])
  const handleToggleCompareShowPilInfoA = useCallback(() => {
    setCompareShowPilInfoA((prev) => !prev)
  }, [setCompareShowPilInfoA])
  const handleToggleCompareShowPilInfoB = useCallback(() => {
    setCompareShowPilInfoB((prev) => !prev)
  }, [setCompareShowPilInfoB])
  const handleComparisonExport = useCallback((reverseOrder: boolean) => {
    void runComparisonExport(reverseOrder)
  }, [runComparisonExport])

  const showNotesConflictBanner = !multi && !!conflict && (conflictFields.tags || conflictFields.notes)
  const hasStarConflict = !multi && !!conflict && conflictFields.star

  const resizeHandleClass = 'toolbar-offset sidebar-resize-handle sidebar-resize-handle-right absolute bottom-0'

  if (!enabled) return (
    <div className="app-right-panel col-start-3 row-start-2 border-l border-border bg-panel overflow-auto scrollbar-thin relative">
      <div className={resizeHandleClass} onPointerDown={onResize} />
    </div>
  )

  return (
    <div className="app-right-panel col-start-3 row-start-2 border-l border-border bg-panel overflow-auto scrollbar-thin relative">
      {!multi && (
        <div className="p-3 border-b border-border flex justify-center">
          <div className="relative rounded-lg overflow-hidden border border-border w-[220px] h-[160px] bg-panel select-none">
            {thumbUrl && <img src={thumbUrl} alt="thumb" className="block w-full h-full object-contain" />}
            {!!ext && <div className="absolute top-1.5 left-1.5 bg-surface border border-border text-text text-xs px-1.5 py-0.5 rounded-md select-none">{ext}</div>}
          </div>
        </div>
      )}
      <OverviewSection
        open={openSections.overview}
        onToggle={toggleOverviewSection}
        multi={multi}
        selectedCount={selectedPaths.length}
        totalSize={totalSize}
        filename={filename}
        compareActive={compareActive}
        compareReady={compareReady}
        onOpenCompare={onOpenCompare}
        compareExportSupportsV2={compareExportSupportsV2}
        compareExportMaxPathsV2={compareExportMaxPathsV2}
        compareExportLabelsText={compareExportLabelsText}
        onCompareExportLabelsTextChange={handleCompareExportLabelsTextChange}
        compareExportEmbedMetadata={compareExportEmbedMetadata}
        onCompareExportEmbedMetadataChange={handleCompareExportEmbedMetadataChange}
        compareExportBusy={compareExportBusy}
        compareExportMode={compareExportMode}
        onComparisonExport={handleComparisonExport}
        compareExportError={compareExportError}
        onFindSimilar={onFindSimilar}
        canFindSimilar={canFindSimilar}
        findSimilarDisabledReason={findSimilarDisabledReason}
      />

      {compareActive && compareReady && (
        <CompareMetadataSection
          open={openSections.compare}
          onToggle={toggleCompareSection}
          compareMetaState={compareMetaState}
          compareMetaError={compareMetaError}
          compareLabelA={compareLabelA}
          compareLabelB={compareLabelB}
          compareIncludePilInfo={compareIncludePilInfo}
          onToggleCompareIncludePilInfo={handleToggleCompareIncludePilInfo}
          onReload={reloadCompareMetadata}
          compareDiff={compareDiff}
          compareHasPilInfoA={compareHasPilInfoA}
          compareHasPilInfoB={compareHasPilInfoB}
          compareShowPilInfoA={compareShowPilInfoA}
          compareShowPilInfoB={compareShowPilInfoB}
          onToggleCompareShowPilInfoA={handleToggleCompareShowPilInfoA}
          onToggleCompareShowPilInfoB={handleToggleCompareShowPilInfoB}
          compareMetaCopied={compareMetaCopied}
          onCopyCompareMetadata={copyCompareMetadata}
          compareValueCopiedPathA={compareValueCopiedPathA}
          compareValueCopiedPathB={compareValueCopiedPathB}
          compareDisplayNodeA={compareDisplayNodeA}
          compareDisplayNodeB={compareDisplayNodeB}
          compareMetaContent={compareMetaContent}
          onCompareMetaPathCopyA={handleCompareMetaPathCopyA}
          onCompareMetaPathCopyB={handleCompareMetaPathCopyB}
        />
      )}

      <BasicsSection
        open={openSections.basics}
        onToggle={toggleBasicsSection}
        multi={multi}
        star={star}
        onSelectStar={handleSelectStar}
        hasStarConflict={hasStarConflict}
        onApplyConflict={applyConflict}
        onKeepTheirs={keepTheirs}
        currentItem={currentItem ?? null}
        sourceValue={sourceValue}
        sortSpec={sortSpec}
        copiedField={copiedField}
        onCopyInfo={copyInfo}
        metricsExpanded={metricsExpanded}
        onToggleMetricsExpanded={toggleMetricsExpanded}
        metricsPreviewLimit={METRICS_PREVIEW_LIMIT}
      />

      {!multi && (
        <MetadataSection
          open={openSections.metadata}
          onToggle={toggleMetadataSection}
          metadataLoading={metadataLoading}
          metadataActionLabel={metadataActionLabel}
          onMetadataAction={handleMetadataAction}
          metadataActionDisabled={!path}
          hasPilInfo={hasPilInfo}
          showPilInfo={showPilInfo}
          onToggleShowPilInfo={handleToggleShowPilInfo}
          metaValueCopiedPath={metaValueCopiedPath}
          metaHeightClass={metaHeightClass}
          metaLoaded={metaLoaded}
          metaDisplayNode={metaDisplayNode}
          metaContent={metaContent}
          metaError={metaError}
          onMetaPathCopy={handleMetaPathCopy}
        />
      )}

      <NotesSection
        open={openSections.notes}
        onToggle={toggleNotesSection}
        multi={multi}
        showConflictBanner={showNotesConflictBanner}
        onApplyConflict={applyConflict}
        onKeepTheirs={keepTheirs}
        notes={notes}
        onNotesChange={handleNotesChange}
        onNotesBlur={handleNotesBlur}
        tags={tags}
        onTagsChange={handleTagsChange}
        onTagsBlur={handleTagsBlur}
      />
      <div className={resizeHandleClass} onPointerDown={onResize} />
    </div>
  )
}
