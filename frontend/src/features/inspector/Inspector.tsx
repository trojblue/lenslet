import React, { Fragment, useEffect, useMemo, useCallback, useLayoutEffect, useRef } from 'react'
import { DndContext, PointerSensor, closestCenter, useSensor, useSensors, type DragEndEvent } from '@dnd-kit/core'
import { SortableContext, verticalListSortingStrategy } from '@dnd-kit/sortable'
import { useQueryClient } from '@tanstack/react-query'
import { useUpdateSidecar, bulkUpdateSidecars, queueSidecarUpdate, useSidecarConflict } from '../../api/items'
import { makeIdempotencyKey } from '../../api/client'
import type { BrowseItemPayload, MetricDisplayNames, SortSpec, StarRating } from '../../lib/types'
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
import { useInspectorCompareExport } from './hooks/useInspectorCompareExport'
import { useInspectorCompareMetadata } from './hooks/useInspectorCompareMetadata'
import { useInspectorSidecarWorkflow } from './hooks/useInspectorSidecarWorkflow'
import { useInspectorPresentation } from './hooks/useInspectorPresentation'
import { useInspectorUiState } from './hooks/useInspectorUiState'

interface InspectorProps {
  path: string | null
  selectedPaths?: string[]
  comparePaths?: string[]
  items?: BrowseItemPayload[]
  presentationResetKey?: string
  visible?: boolean
  viewerCompareActive?: boolean
  compareA?: BrowseItemPayload | null
  compareB?: BrowseItemPayload | null
  onOpenCompare?: () => void
  onResize?: (e: React.PointerEvent<HTMLDivElement>) => void
  onStarChanged?: (paths: string[], val: StarRating) => void
  sortSpec?: SortSpec
  metricDisplayNames?: MetricDisplayNames | null
  onFindSimilar?: () => void
  embeddingsAvailable?: boolean
  embeddingsLoading?: boolean
  autoloadImageMetadata?: boolean
  onLocalTypingChange?: (active: boolean) => void
  onActionStart?: () => void
  onActionError?: (action: string, error: unknown) => void
}

const METRICS_PREVIEW_LIMIT = 12
const COMPARE_MATRIX_LIMIT = 120
const COMPARE_MATRIX_MAX_DEPTH = 8
const COMPARE_MATRIX_MAX_ARRAY = 80
const QUICK_VIEW_ERROR_ROWS = [
  { id: 'default:prompt', label: 'Prompt', value: '', sourcePath: 'prompt' },
  { id: 'default:model', label: 'Model', value: '', sourcePath: 'model' },
  { id: 'default:lora', label: 'LoRA', value: '', sourcePath: 'lora' },
]
const INSPECTOR_WIDGET_MAP = new Map(
  INSPECTOR_WIDGETS.map((widget) => [widget.id, widget] as const),
)

export default function Inspector({
  path,
  selectedPaths = [],
  comparePaths,
  items = [],
  presentationResetKey = 'default',
  visible = true,
  viewerCompareActive = false,
  compareA = null,
  compareB = null,
  onOpenCompare,
  onResize,
  onStarChanged,
  sortSpec,
  metricDisplayNames,
  onFindSimilar,
  embeddingsAvailable = false,
  embeddingsLoading = false,
  autoloadImageMetadata = true,
  onLocalTypingChange,
  onActionStart,
  onActionError,
}: InspectorProps) {
  const qc = useQueryClient()
  const {
    presentation,
    requestedIdentity,
    transitioning,
    showMetadataLoadingCopy,
    previewStage,
    decodeTargetPreview,
    failTargetPreview,
    setTargetMetadataError,
    setTargetShowPilInfo,
    fetchTargetMetadata,
  } = useInspectorPresentation({
    path,
    selectedPaths,
    comparePaths: comparePaths ?? selectedPaths,
    items,
    resetKey: presentationResetKey,
    visible,
    autoloadMetadata: autoloadImageMetadata,
  })
  const presentedPath = presentation?.path ?? null
  const presentedSelectedPaths = presentation?.selectedPaths ?? []
  const presentedComparePaths = presentation?.comparePaths ?? presentedSelectedPaths
  const presentedItems = presentation?.items ?? []
  const data = presentation?.sidecar ?? undefined
  const enabled = !!presentedPath
  const selectedCount = presentedSelectedPaths.length
  const activePresentationIdentityRef = useRef<string | null>(presentation?.identity ?? null)
  const activeRequestedIdentityRef = useRef<string | null>(requestedIdentity)
  activePresentationIdentityRef.current = presentation?.identity ?? null
  activeRequestedIdentityRef.current = requestedIdentity
  const copyContextIsCurrent = useCallback((context: string | null) => (
    context !== null
    && activePresentationIdentityRef.current === context
    && activeRequestedIdentityRef.current === context
  ), [])
  const multi = selectedCount > 1
  const comparisonPathsKey = JSON.stringify(presentedComparePaths)

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
    const star = presentedItems.find((i) => i.path === presentedPath)?.star
    return star ?? null
  }, [presentedItems, presentedPath])

  const star = itemStarFromList ?? data?.star ?? null
  const conflict = useSidecarConflict(!multi ? presentedPath : null)

  const compareTargets = useMemo(
    () => resolveCompareMetadataTargets(selectedCount >= 2, presentedComparePaths),
    [selectedCount, comparisonPathsKey],
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
    path: presentedPath,
    feedbackContextKey: presentation
      ? `${presentationResetKey}\n${presentation.identity}`
      : null,
    comparePaths: compareTargetPaths,
    selectedCount,
    metadataCompareAvailable,
    autoloadMetadataCompare: autoloadImageMetadata,
  })
  const compareSectionOpen = metadataCompareReady && openSections.compare
  const metadataSectionOpen = !multi && openSections.metadata
  const mut = useUpdateSidecar(presentedPath ?? '', presentationResetKey)

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
    path: presentedPath,
    selectedPaths: presentedSelectedPaths,
    resetKey: presentationResetKey,
    multi,
    sidecar: data,
    conflict,
    star,
    queryClient: qc,
    mutateSidecar,
    onStarChanged,
    onLocalTypingChange,
  })

  const metaRaw = presentation?.metadata.raw ?? null
  const metaError = presentation?.metadata.error ?? null
  const metaState = presentation?.metadata.state ?? 'idle'
  const showPilInfo = presentation?.metadata.showPilInfo ?? false

  const {
    compareMetaState,
    compareMetaError,
    compareMetaByPath,
    compareIncludePilInfo,
    setCompareIncludePilInfo,
    reloadCompareMetadata,
  } = useInspectorCompareMetadata({
    compareReady: metadataCompareReady,
    comparePaths: compareTargetPaths,
    enabled: visible,
  })

  const {
    compareExportLabelsText,
    compareExportEmbedMetadata,
    compareExportReverseOrder,
    compareExportHighQualityGif,
    compareExportMode,
    compareExportError,
    compareExportBusy,
    handleCompareExportLabelsTextChange,
    handleCompareExportEmbedMetadataChange,
    handleCompareExportReverseOrderChange,
    handleCompareExportHighQualityGifChange,
    runComparisonExport,
  } = useInspectorCompareExport({
    selectedPaths: compareTargetPaths,
    onActionStart,
    onActionError,
  })

  const selectedItems = useMemo(() => {
    const selectedPathSet = new Set(presentedSelectedPaths)
    return presentedItems.filter((i) => selectedPathSet.has(i.path))
  }, [presentedItems, presentedSelectedPaths])

  const totalSize = useMemo(
    () => selectedItems.reduce((acc, it) => acc + (it.size || 0), 0),
    [selectedItems],
  )

  useEffect(() => {
    if (!presentedPath || transitioning || !visible) return

    const onKey = (e: KeyboardEvent) => {
      if (isInputElement(e.target)) return

      const k = e.key
      if (!/^[0-5]$/.test(k)) return

      e.preventDefault()
      const val: StarRating = k === '0' ? null : (Number(k) as 1 | 2 | 3 | 4 | 5)

      if (multi) {
        commitSidecar({ star: val })
        onStarChanged?.(presentedSelectedPaths, val)
        return
      }
      commitSidecar({ star: val })
      onStarChanged?.([presentedPath], val)
    }

    window.addEventListener('keydown', onKey)
    return () => window.removeEventListener('keydown', onKey)
  }, [
    commitSidecar,
    multi,
    onStarChanged,
    presentedPath,
    presentedSelectedPaths,
    transitioning,
    visible,
  ])

  const filename = presentedPath ? presentedPath.split('/').pop() || presentedPath : ''
  const ext = useMemo(() => {
    if (filename.includes('.')) {
      return filename.slice(filename.lastIndexOf('.') + 1).toUpperCase()
    }
    const it = presentedItems.find((i) => i.path === presentedPath)
    if (it?.mime?.includes('/')) {
      return it.mime.split('/')[1].toUpperCase()
    }
    return ''
  }, [filename, presentedItems, presentedPath])

  const currentItem = presentation?.item ?? presentedItems.find((i) => i.path === presentedPath) ?? null
  const sourceValue = useMemo(() => {
    if (!presentedPath) return ''
    return currentItem?.source ?? presentedPath
  }, [currentItem, presentedPath])

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
    () => (metaState === 'error'
      ? QUICK_VIEW_ERROR_ROWS
      : buildQuickViewRows(metaRaw, quickViewCustomPaths)),
    [metaRaw, metaState, quickViewCustomPaths],
  )
  const quickViewVisible = useMemo(
    () => shouldShowQuickViewSection({
      multi,
      autoloadMetadata: autoloadImageMetadata,
      meta: metaRaw,
    }),
    [autoloadImageMetadata, metaRaw, multi],
  )
  const quickViewReserved = !multi && metaState === 'error'

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
    const context = presentation?.identity ?? null
    onActionStart?.()
    navigator.clipboard?.writeText(metaRawText).then(() => {
      if (!copyContextIsCurrent(context)) return
      markMetadataCopied()
    }).catch((err) => {
      if (!copyContextIsCurrent(context)) return
      const msg = err instanceof Error ? err.message : 'Copy failed'
      setTargetMetadataError(msg)
      onActionError?.('Copy metadata failed', err)
    })
  }, [
    copyContextIsCurrent,
    markMetadataCopied,
    metaRawText,
    onActionError,
    onActionStart,
    presentation?.identity,
    setTargetMetadataError,
  ])

  const metaDisplayNode = useMemo(() => {
    if (!metadataSectionOpen || !metaDisplayValue) return null
    return buildJsonRenderNode(metaDisplayValue)
  }, [metadataSectionOpen, metaDisplayValue])

  const copyMetadataValue = useCallback((pathLabel: string, copyText: string) => {
    const context = presentation?.identity ?? null
    onActionStart?.()
    navigator.clipboard?.writeText(copyText).then(() => {
      if (!copyContextIsCurrent(context)) return
      markMetadataValueCopied(pathLabel)
    }).catch((err) => {
      if (!copyContextIsCurrent(context)) return
      onActionError?.('Copy metadata value failed', err)
    })
  }, [
    copyContextIsCurrent,
    markMetadataValueCopied,
    onActionError,
    onActionStart,
    presentation?.identity,
  ])

  const handleCopyQuickViewValue = useCallback((rowId: string, value: string) => {
    if (!value) return
    const context = presentation?.identity ?? null
    onActionStart?.()
    navigator.clipboard?.writeText(value).then(() => {
      if (!copyContextIsCurrent(context)) return
      markQuickViewValueCopied(rowId)
    }).catch((err) => {
      if (!copyContextIsCurrent(context)) return
      onActionError?.('Copy quick view value failed', err)
    })
  }, [
    copyContextIsCurrent,
    markQuickViewValueCopied,
    onActionError,
    onActionStart,
    presentation?.identity,
  ])

  const handleMetaPathCopy = useCallback((path: Array<string | number>) => {
    if (!metaDisplayValue) return
    const payload = buildMetadataPathCopyPayload(metaDisplayValue, path)
    copyMetadataValue(payload.pathLabel, payload.copyText)
  }, [metaDisplayValue, copyMetadataValue])

  let metaContent = metaDisplayValue ? '' : 'PNG metadata not loaded yet.'
  if (metaState === 'loading') {
    metaContent = showMetadataLoadingCopy ? 'Loading metadata…' : ''
  } else if (metaState === 'error' && metaError) {
    metaContent = metaError
  }
  const metadataLoading = metaState === 'loading'
  const metaLoaded = metaState === 'loaded' && !!metaRawText
  const metaHeightClass = presentedPath && autoloadImageMetadata ? 'h-48' : (metaLoaded ? 'h-48' : 'h-24')
  let metadataActionLabel = 'Load meta'
  if (metadataLoading) {
    metadataActionLabel = showMetadataLoadingCopy ? 'Loading…' : '\u00a0'
  } else if (metaLoaded) {
    metadataActionLabel = metaCopied ? 'Copied' : 'Copy'
  }
  const metadataActionAriaLabel = metadataLoading ? 'Loading metadata' : metadataActionLabel
  const handleMetadataAction = metaLoaded ? copyMetadata : fetchTargetMetadata

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
    const context = presentation?.identity ?? null
    onActionStart?.()
    navigator.clipboard?.writeText(text).then(() => {
      if (!copyContextIsCurrent(context)) return
      markInfoCopied(key)
    }).catch((err) => {
      if (!copyContextIsCurrent(context)) return
      onActionError?.('Copy item info failed', err)
    })
  }, [
    copyContextIsCurrent,
    markInfoCopied,
    onActionError,
    onActionStart,
    presentation?.identity,
  ])

  const handleSelectStar = useCallback((value: StarRating) => {
    onActionStart?.()
    if (multi) {
      onStarChanged?.(presentedSelectedPaths, value)
      void bulkUpdateSidecars(presentedSelectedPaths, { star: value }).catch((error) => {
        onActionError?.('Bulk rating update failed', error)
      })
      return
    }
    if (!presentedPath) return
    onStarChanged?.([presentedPath], value)
    void queueSidecarUpdate(presentedPath, { star: value }).catch((error) => {
      onActionError?.('Rating update failed', error)
    })
  }, [
    multi,
    onActionError,
    onActionStart,
    onStarChanged,
    presentedPath,
    presentedSelectedPaths,
  ])

  const handleToggleShowPilInfo = useCallback(() => {
    setTargetShowPilInfo((prev) => !prev)
  }, [setTargetShowPilInfo])
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
      quickViewCopiedRowId,
      onCopyQuickViewValue: handleCopyQuickViewValue,
      quickViewCustomPathsDraft,
      onQuickViewCustomPathsDraftChange: setQuickViewCustomPathsDraft,
      onSaveQuickViewCustomPaths: saveQuickViewCustomPaths,
      quickViewCustomPathsError,
      statusMessage: metaState === 'error' ? (metaError ?? 'Metadata unavailable.') : null,
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
      currentItem,
      sourceValue,
      sortSpec,
      metricDisplayNames,
      copiedField,
      onCopyInfo: copyInfo,
      metricsExpanded,
      onToggleMetricsExpanded: toggleMetricsExpanded,
      metricsPreviewLimit: METRICS_PREVIEW_LIMIT,
      tableFields: data?.table_fields ?? null,
      statusMessage: presentation?.itemError ?? null,
      controlsDisabled: transitioning,
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
      metadataActionAriaLabel,
      onMetadataAction: handleMetadataAction,
      metadataActionDisabled: !presentedPath || transitioning,
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
      transitionStatusVisible: showMetadataLoadingCopy,
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
      disabled: transitioning || !!presentation?.sidecarError,
      statusMessage: presentation?.sidecarError ?? null,
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

  const panelRef = useRef<HTMLDivElement | null>(null)
  useLayoutEffect(() => {
    const panel = panelRef.current
    panel?.toggleAttribute('inert', transitioning || !visible)
    if (!transitioning && visible) return
    const activeElement = document.activeElement
    if (activeElement instanceof HTMLElement && panel?.contains(activeElement)) activeElement.blur()
  }, [transitioning, visible])

  const panelProps = {
    ref: panelRef,
    hidden: !visible,
    'aria-hidden': !visible || undefined,
    'aria-busy': transitioning || undefined,
    'data-inspector-panel': true,
    'data-inspector-path': presentedPath ?? '',
    'data-inspector-requested-path': path ?? '',
    'data-inspector-presented-path': presentedPath ?? '',
    'data-inspector-requested-identity': requestedIdentity ?? '',
    'data-inspector-presented-identity': presentation?.identity ?? '',
    'data-inspector-requested-reset-key': presentationResetKey,
    'data-inspector-presented-reset-key': presentation?.resetKey ?? '',
    'data-inspector-item-notes': presentation?.item?.notes ?? '',
    'data-inspector-transitioning': transitioning ? 'true' : 'false',
    'data-inspector-metadata-state': metaState,
    'data-inspector-item-state': presentation?.itemError ? 'error' : 'ready',
    'data-inspector-sidecar-state': presentation?.sidecarError ? 'error' : 'ready',
    'data-inspector-section-order': JSON.stringify(sectionOrder),
    'data-inspector-quick-view-paths': JSON.stringify(quickViewCustomPaths),
    'data-inspector-export-reverse': compareExportReverseOrder ? 'true' : 'false',
    'data-inspector-export-high-quality': compareExportHighQualityGif ? 'true' : 'false',
  } as const

  return (
    <div className="app-right-panel inspector-panel col-start-3 row-start-2 border-l border-border bg-panel overflow-auto scrollbar-thin relative" {...panelProps}>
      <div
        className={`inspector-preview-shell p-3 border-b border-border justify-center ${enabled && !multi ? 'flex' : 'hidden'}`}
        aria-hidden={!enabled || multi || undefined}
      >
        <div className="inspector-preview-block space-y-2">
          <div
            className="inspector-preview-card relative rounded-lg overflow-hidden border border-border bg-panel select-none"
            data-preview-state={presentation?.preview.status ?? 'idle'}
          >
              {presentation?.preview.status === 'ready' && (
                <img
                  key={presentation.preview.url}
                  src={presentation.preview.url}
                  alt="thumb"
                  className="inspector-preview-image block"
                  data-preview-path={presentedPath ?? ''}
                />
              )}
              {previewStage && previewStage.url !== (
                presentation?.preview.status === 'ready' ? presentation.preview.url : null
              ) && (
                <img
                  key={previewStage.url}
                  src={previewStage.url}
                  alt=""
                  aria-hidden="true"
                  className="absolute inset-0 invisible h-full w-full"
                  data-preview-candidate-path={previewStage.path}
                  onLoad={(event) => decodeTargetPreview(event.currentTarget, previewStage)}
                  onError={() => failTargetPreview(previewStage)}
                />
              )}
              {presentation?.preview.status === 'error' && (
                <div className="absolute inset-0 flex flex-col items-center justify-center gap-2 p-3 text-center text-[11px] text-danger">
                  <span>{presentation.preview.message}</span>
                  <button type="button" className="btn btn-sm" onClick={presentation.preview.retry}>
                    Retry preview
                  </button>
                </div>
              )}
              {!!ext && <div className="absolute top-1.5 left-1.5 bg-surface border border-border text-text text-xs px-1.5 py-0.5 rounded-md select-none">{ext}</div>}
          </div>
          <div className="space-y-0.5">
            <div className="text-[10px] uppercase tracking-wide text-muted">Filename</div>
            <div className="inspector-value-clamp h-9 [overflow-wrap:anywhere] text-[12px] leading-relaxed" title={filename || undefined}>
              {filename || '—'}
            </div>
          </div>
        </div>
      </div>
      {enabled && (
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
      )}
      <div className={resizeHandleClass} onPointerDown={onResize} />
    </div>
  )
}
