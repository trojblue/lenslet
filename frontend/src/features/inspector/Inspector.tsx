import React, { Fragment, useEffect, useMemo, useCallback, useLayoutEffect, useRef, useState } from 'react'
import { DndContext, PointerSensor, closestCenter, useSensor, useSensors, type DragEndEvent } from '@dnd-kit/core'
import { SortableContext, verticalListSortingStrategy } from '@dnd-kit/sortable'
import { useQueryClient } from '@tanstack/react-query'
import { useSidecar, useUpdateSidecar, bulkUpdateSidecars, queueSidecarUpdate, useSidecarConflict } from '../../api/items'
import { api, makeIdempotencyKey } from '../../api/client'
import { useBlobUrl } from '../../shared/hooks/useBlobUrl'
import type { Item, SortSpec, StarRating } from '../../lib/types'
import { isInputElement } from '../../lib/keyboard'
import {
  buildMetadataPathCopyPayload,
  buildJsonRenderNode,
  buildCompareMetadataMatrixFromNormalized,
  buildDisplayMetadataFromNormalized,
  hasPilInfoMetadata,
  normalizeMetadataRecord,
} from './model/metadataCompare'
import {
  isInspectorWidgetId,
  sanitizeInspectorWidgetOrder,
} from './model/inspectorWidgetOrder'
import {
  buildQuickViewRows,
  shouldShowQuickViewSection,
} from './model/quickViewFields'
import { resolveFindSimilarAvailability } from './model/findSimilarAvailability'
import { INSPECTOR_WIDGETS, type InspectorWidgetContext } from './inspectorWidgets'
import { resolveCompareMetadataTargets } from './hooks/metadataRequestGuards'
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
  comparePaths?: string[]
  items?: InspectorItem[]
  viewerCompareActive?: boolean
  compareA?: Item | null
  compareB?: Item | null
  onOpenCompare?: () => void
  onResize?: (e: React.PointerEvent<HTMLDivElement>) => void
  onStarChanged?: (paths: string[], val: StarRating) => void
  sortSpec?: SortSpec
  onFindSimilar?: () => void
  embeddingsAvailable?: boolean
  embeddingsLoading?: boolean
  autoloadImageMetadata?: boolean
  onLocalTypingChange?: (active: boolean) => void
}

const METRICS_PREVIEW_LIMIT = 12
const COMPARE_MATRIX_LIMIT = 120
const COMPARE_MATRIX_MAX_DEPTH = 8
const COMPARE_MATRIX_MAX_ARRAY = 80
const QUICK_VIEW_FALLBACK_ROW_COUNT = 3
const INSPECTOR_WIDGET_MAP = new Map(
  INSPECTOR_WIDGETS.map((widget) => [widget.id, widget] as const),
)

export default function Inspector({
  path,
  selectedPaths = [],
  comparePaths,
  items = [],
  viewerCompareActive = false,
  compareA = null,
  compareB = null,
  onOpenCompare,
  onResize,
  onStarChanged,
  sortSpec,
  onFindSimilar,
  embeddingsAvailable = false,
  embeddingsLoading = false,
  autoloadImageMetadata = true,
  onLocalTypingChange,
}: InspectorProps) {
  const enabled = !!path
  const { data } = useSidecar(path ?? '')
  const mut = useUpdateSidecar(path ?? '')
  const qc = useQueryClient()

  const selectedCount = selectedPaths.length
  const multi = selectedCount > 1
  const comparisonPaths = comparePaths ?? selectedPaths

  const { canFindSimilar, disabledReason: findSimilarDisabledReason } = useMemo(
    () => resolveFindSimilarAvailability({
      enabled: !!onFindSimilar,
      embeddingsAvailable,
      embeddingsLoading,
      selectedCount,
    }),
    [embeddingsAvailable, embeddingsLoading, onFindSimilar, selectedCount],
  )

  // Get star from item list (optimistic local value) or sidecar
  const itemStarFromList = useMemo((): StarRating | null => {
    const star = items.find((i) => i.path === path)?.star
    return star ?? null
  }, [items, path])

  const star = itemStarFromList ?? data?.star ?? null
  const conflict = useSidecarConflict(!multi ? path : null)

  const compareTargets = useMemo(
    () => resolveCompareMetadataTargets(selectedCount >= 2, comparisonPaths),
    [selectedCount, comparisonPaths],
  )
  const compareTargetPaths = compareTargets.paths
  const metadataCompareAvailable = compareTargetPaths.length >= 2
  const {
    sectionOrder,
    reorderSectionOrder,
    metadataCompareActive,
    metadataCompareReady,
    toggleMetadataCompareActive,
    openSections,
    toggleQuickViewSection,
    toggleOverviewSection,
    toggleCompareSection,
    toggleBasicsSection,
    toggleMetadataSection,
    toggleNotesSection,
    quickViewCustomPaths,
    quickViewCustomPathsDraft,
    quickViewCustomPathsError,
    setQuickViewCustomPathsDraft,
    saveQuickViewCustomPaths,
    quickViewCopiedRowId,
    markQuickViewValueCopied,
    metricsExpanded,
    toggleMetricsExpanded,
    copiedField,
    markInfoCopied,
    metaCopied,
    markMetadataCopied,
    metaValueCopiedPath,
    markMetadataValueCopied,
  } = useInspectorUiState({
    path,
    sidecarUpdatedAt: data?.updated_at,
    comparePaths: compareTargetPaths,
    selectedCount,
    metadataCompareAvailable,
    autoloadMetadataCompare: autoloadImageMetadata,
  })
  const compareSectionOpen = metadataCompareReady && openSections.compare
  const metadataSectionOpen = !multi && openSections.metadata

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
    compareMetaByPath,
    compareIncludePilInfo,
    compareExportLabelsText,
    compareExportEmbedMetadata,
    compareExportReverseOrder,
    compareExportHighQualityGif,
    compareExportMode,
    compareExportError,
    compareExportBusy,
    setShowPilInfo,
    setCompareIncludePilInfo,
    fetchMetadata,
    reloadCompareMetadata,
    handleCompareExportLabelsTextChange,
    handleCompareExportEmbedMetadataChange,
    handleCompareExportReverseOrderChange,
    handleCompareExportHighQualityGifChange,
    runComparisonExport,
  } = useInspectorMetadataWorkflow({
    path,
    sidecarUpdatedAt: data?.updated_at,
    selectedPaths: compareTargetPaths,
    compareReady: metadataCompareReady,
    comparePaths: compareTargetPaths,
    autoloadMetadata: autoloadImageMetadata && !multi,
  })

  const selectedItems = useMemo(() => {
    const selectedPathSet = new Set(selectedPaths)
    return items.filter((i) => selectedPathSet.has(i.path))
  }, [items, selectedPaths])

  const totalSize = useMemo(
    () => selectedItems.reduce((acc, it) => acc + (it.size || 0), 0),
    [selectedItems],
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

      if (multi) {
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

  const metaDisplayValue = useMemo(
    () => buildDisplayMetadataFromNormalized(normalizedMetaRaw, showPilInfo),
    [normalizedMetaRaw, showPilInfo],
  )
  const quickViewRows = useMemo(
    () => buildQuickViewRows(metaRaw, quickViewCustomPaths),
    [metaRaw, quickViewCustomPaths],
  )
  const quickViewVisible = useMemo(
    () => shouldShowQuickViewSection({
      multi,
      autoloadMetadata: autoloadImageMetadata,
      meta: metaRaw,
    }),
    [autoloadImageMetadata, metaRaw, multi],
  )
  const [quickViewReservationActive, setQuickViewReservationActive] = useState(false)
  const [quickViewReservationRowCount, setQuickViewReservationRowCount] = useState(
    QUICK_VIEW_FALLBACK_ROW_COUNT,
  )
  const previousSelectionKeyRef = useRef<string | null>(null)
  const previousQuickViewRowsRef = useRef(0)
  const selectionKey = `${path ?? ''}::${data?.updated_at ?? ''}`

  useLayoutEffect(() => {
    const previousSelectionKey = previousSelectionKeyRef.current
    const selectionChanged = previousSelectionKey !== null && previousSelectionKey !== selectionKey
    if (selectionChanged) {
      if (
        autoloadImageMetadata
        && !multi
        && !!path
        && previousQuickViewRowsRef.current > 0
      ) {
        const reservedRows = Math.max(previousQuickViewRowsRef.current, QUICK_VIEW_FALLBACK_ROW_COUNT)
        setQuickViewReservationRowCount(reservedRows)
        setQuickViewReservationActive(true)
      } else {
        setQuickViewReservationActive(false)
      }
    }

    if (quickViewVisible) {
      const measuredRows = Math.max(quickViewRows.length, QUICK_VIEW_FALLBACK_ROW_COUNT)
      previousQuickViewRowsRef.current = measuredRows
      setQuickViewReservationRowCount(measuredRows)
    }

    previousSelectionKeyRef.current = selectionKey
  }, [
    autoloadImageMetadata,
    multi,
    path,
    quickViewRows.length,
    quickViewVisible,
    selectionKey,
  ])

  useEffect(() => {
    if (!quickViewReservationActive) return
    if (quickViewVisible) {
      setQuickViewReservationActive(false)
      return
    }
    if (!autoloadImageMetadata || multi || !path) {
      setQuickViewReservationActive(false)
      previousQuickViewRowsRef.current = 0
      return
    }
    const metadataSettled = metaRaw !== null || metaError !== null || metaState === 'error'
    if (metadataSettled) {
      setQuickViewReservationActive(false)
      if (!quickViewVisible) {
        previousQuickViewRowsRef.current = 0
      }
    }
  }, [
    autoloadImageMetadata,
    metaError,
    metaRaw,
    metaState,
    multi,
    path,
    quickViewReservationActive,
    quickViewVisible,
  ])
  const quickViewReserved = quickViewReservationActive && !quickViewVisible

  const compareColumns = useMemo(
    () => compareTargetPaths.map((comparePath) => ({
      path: comparePath,
      label: comparePath.split('/').pop() || comparePath,
    })),
    [compareTargetPaths],
  )

  const normalizedCompareMatrixInputs = useMemo(
    () => compareColumns.map((column) => ({
      path: column.path,
      label: column.label,
      normalizedMeta: normalizeMetadataRecord(compareMetaByPath[column.path] ?? null),
    })),
    [compareColumns, compareMetaByPath],
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

  const copyMetadataValue = useCallback((pathLabel: string, copyText: string) => {
    navigator.clipboard?.writeText(copyText).then(() => {
      markMetadataValueCopied(pathLabel)
    }).catch(() => {})
  }, [markMetadataValueCopied])

  const handleCopyQuickViewValue = useCallback((rowId: string, value: string) => {
    if (!value) return
    navigator.clipboard?.writeText(value).then(() => {
      markQuickViewValueCopied(rowId)
    }).catch(() => {})
  }, [markQuickViewValueCopied])

  const handleMetaPathCopy = useCallback((path: Array<string | number>) => {
    if (!metaDisplayValue) return
    const payload = buildMetadataPathCopyPayload(metaDisplayValue, path)
    copyMetadataValue(payload.pathLabel, payload.copyText)
  }, [metaDisplayValue, copyMetadataValue])

  let metaContent = metaDisplayValue ? '' : 'PNG metadata not loaded yet.'
  if (metaState === 'loading') {
    metaContent = 'Loading metadata…'
  } else if (metaState === 'error' && metaError) {
    metaContent = metaError
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

  const compareMatrix = useMemo(() => {
    if (!compareSectionOpen) return null
    return buildCompareMetadataMatrixFromNormalized(normalizedCompareMatrixInputs, {
      includePilInfo: compareIncludePilInfo,
      limit: COMPARE_MATRIX_LIMIT,
      maxDepth: COMPARE_MATRIX_MAX_DEPTH,
      maxArray: COMPARE_MATRIX_MAX_ARRAY,
    })
  }, [compareSectionOpen, normalizedCompareMatrixInputs, compareIncludePilInfo])

  const copyInfo = useCallback((key: string, text: string) => {
    if (!text) return
    navigator.clipboard?.writeText(text).then(() => {
      markInfoCopied(key)
    }).catch(() => {})
  }, [markInfoCopied])

  const handleSelectStar = useCallback((value: StarRating) => {
    if (multi) {
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
  const handleComparisonExport = useCallback((outputFormat: 'png' | 'gif') => {
    void runComparisonExport(outputFormat)
  }, [runComparisonExport])
  const sectionOrderSensors = useSensors(
    useSensor(PointerSensor, {
      activationConstraint: { distance: 6 },
    }),
  )
  const handleSectionDragEnd = useCallback((event: DragEndEvent) => {
    const activeId = event.active.id
    const overId = event.over?.id
    if (typeof activeId !== 'string' || typeof overId !== 'string') return
    if (!isInspectorWidgetId(activeId) || !isInspectorWidgetId(overId)) return
    reorderSectionOrder(activeId, overId)
  }, [reorderSectionOrder])

  const showNotesConflictBanner = !multi && !!conflict && (conflictFields.tags || conflictFields.notes)
  const hasStarConflict = !multi && !!conflict && conflictFields.star

  const resizeHandleClass = 'toolbar-offset sidebar-resize-handle sidebar-resize-handle-right absolute bottom-0'
  const widgetContext: InspectorWidgetContext = {
    multi,
    viewerCompareActive,
    metadataCompareReady,
    quickViewVisible,
    quickViewReserved,
    quickViewProps: {
      open: openSections.quickView,
      onToggle: toggleQuickViewSection,
      sortableId: 'quickView',
      sortableEnabled: true,
      rows: quickViewRows,
      reservationActive: quickViewReserved,
      reservationRowCount: quickViewReservationRowCount,
      metadataLoading,
      quickViewCopiedRowId,
      onCopyQuickViewValue: handleCopyQuickViewValue,
      quickViewCustomPathsDraft,
      onQuickViewCustomPathsDraftChange: setQuickViewCustomPathsDraft,
      onSaveQuickViewCustomPaths: saveQuickViewCustomPaths,
      quickViewCustomPathsError,
    },
    overviewProps: {
      open: openSections.overview,
      onToggle: toggleOverviewSection,
      sortableId: 'overview',
      sortableEnabled: true,
      selectedCount,
      totalSize,
      viewerCompareActive,
      metadataCompareActive,
      metadataCompareAvailable,
      onOpenCompare,
      onToggleMetadataCompare: toggleMetadataCompareActive,
      compareExportLabelsText,
      onCompareExportLabelsTextChange: handleCompareExportLabelsTextChange,
      compareExportEmbedMetadata,
      onCompareExportEmbedMetadataChange: handleCompareExportEmbedMetadataChange,
      compareExportReverseOrder,
      onCompareExportReverseOrderChange: handleCompareExportReverseOrderChange,
      compareExportHighQualityGif,
      onCompareExportHighQualityGifChange: handleCompareExportHighQualityGifChange,
      compareExportBusy,
      compareExportMode,
      onComparisonExport: handleComparisonExport,
      compareExportError,
    },
    compareMetadataProps: {
      open: openSections.compare,
      onToggle: toggleCompareSection,
      sortableId: 'compareMetadata',
      sortableEnabled: true,
      compareMetaState,
      compareMetaError,
      compareColumns,
      compareIncludePilInfo,
      onToggleCompareIncludePilInfo: handleToggleCompareIncludePilInfo,
      onReload: reloadCompareMetadata,
      compareCopiedPath: metaValueCopiedPath,
      onCopyCompareValue: copyMetadataValue,
      compareMatrix,
      compareSelectionTruncatedCount: compareTargets.truncatedCount,
    },
    basicsProps: {
      open: openSections.basics,
      onToggle: toggleBasicsSection,
      sortableId: 'basics',
      sortableEnabled: true,
      multi,
      star,
      onSelectStar: handleSelectStar,
      hasStarConflict,
      onApplyConflict: applyConflict,
      onKeepTheirs: keepTheirs,
      currentItem: currentItem ?? null,
      sourceValue,
      sortSpec,
      copiedField,
      onCopyInfo: copyInfo,
      metricsExpanded,
      onToggleMetricsExpanded: toggleMetricsExpanded,
      metricsPreviewLimit: METRICS_PREVIEW_LIMIT,
      onFindSimilar,
      canFindSimilar,
      findSimilarDisabledReason,
    },
    metadataProps: {
      open: openSections.metadata,
      onToggle: toggleMetadataSection,
      sortableId: 'metadata',
      sortableEnabled: true,
      metadataLoading,
      metadataActionLabel,
      onMetadataAction: handleMetadataAction,
      metadataActionDisabled: !path,
      hasPilInfo,
      showPilInfo,
      onToggleShowPilInfo: handleToggleShowPilInfo,
      metaValueCopiedPath,
      metaHeightClass,
      metaLoaded,
      metaDisplayNode,
      metaContent,
      metaError,
      onMetaPathCopy: handleMetaPathCopy,
    },
    notesProps: {
      open: openSections.notes,
      onToggle: toggleNotesSection,
      sortableId: 'notes',
      sortableEnabled: true,
      multi,
      showConflictBanner: showNotesConflictBanner,
      onApplyConflict: applyConflict,
      onKeepTheirs: keepTheirs,
      notes,
      onNotesChange: handleNotesChange,
      onNotesBlur: handleNotesBlur,
      tags,
      onTagsChange: handleTagsChange,
      onTagsBlur: handleTagsBlur,
    },
  }
  const orderedVisibleWidgets = useMemo(() => {
    const orderedIds = sanitizeInspectorWidgetOrder(sectionOrder)
    return orderedIds
      .map((widgetId) => INSPECTOR_WIDGET_MAP.get(widgetId))
      .filter((widget): widget is (typeof INSPECTOR_WIDGETS)[number] => !!widget)
      .filter((widget) => widget.isVisible(widgetContext))
  }, [sectionOrder, widgetContext])
  const visibleWidgetIds = useMemo(
    () => orderedVisibleWidgets.map((widget) => widget.id),
    [orderedVisibleWidgets],
  )

  if (!enabled) return (
    <div className="app-right-panel col-start-3 row-start-2 border-l border-border bg-panel overflow-auto scrollbar-thin relative">
      <div className={resizeHandleClass} onPointerDown={onResize} />
    </div>
  )

  return (
    <div className="app-right-panel col-start-3 row-start-2 border-l border-border bg-panel overflow-auto scrollbar-thin relative">
      {!multi && (
        <div className="p-3 border-b border-border flex justify-center">
          <div className="w-[220px] space-y-2">
            <div className="relative rounded-lg overflow-hidden border border-border w-[220px] h-[160px] bg-panel select-none">
              {thumbUrl && <img src={thumbUrl} alt="thumb" className="block w-full h-full object-contain" />}
              {!!ext && <div className="absolute top-1.5 left-1.5 bg-surface border border-border text-text text-xs px-1.5 py-0.5 rounded-md select-none">{ext}</div>}
            </div>
            <div className="space-y-0.5">
              <div className="text-[10px] uppercase tracking-wide text-muted">Filename</div>
              <div className="text-[12px] leading-relaxed break-all" title={filename || undefined}>
                {filename || '—'}
              </div>
            </div>
          </div>
        </div>
      )}
      <DndContext
        sensors={sectionOrderSensors}
        collisionDetection={closestCenter}
        onDragEnd={handleSectionDragEnd}
      >
        <SortableContext items={visibleWidgetIds} strategy={verticalListSortingStrategy}>
          {orderedVisibleWidgets.map((widget) => (
            <Fragment key={widget.id}>{widget.render(widgetContext)}</Fragment>
          ))}
        </SortableContext>
      </DndContext>
      <div className={resizeHandleClass} onPointerDown={onResize} />
    </div>
  )
}
