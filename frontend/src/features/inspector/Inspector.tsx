import React, { useEffect, useMemo, useState, useCallback, useRef } from 'react'
import { useQueryClient } from '@tanstack/react-query'
import { useSidecar, useUpdateSidecar, bulkUpdateSidecars, queueSidecarUpdate, useSidecarConflict } from '../../shared/api/items'
import { api, makeIdempotencyKey } from '../../shared/api/client'
import { useBlobUrl } from '../../shared/hooks/useBlobUrl'
import type { Item, SortSpec, StarRating } from '../../lib/types'
import { isInputElement } from '../../lib/keyboard'
import {
  buildCompareMetadataDiffFromNormalized,
  buildDisplayMetadataFromNormalized,
  formatCopyValue,
  formatPathLabel,
  getValueAtPath,
  hasPilInfoMetadata,
  normalizeMetadataRecord,
  renderJsonValue,
} from './model/metadataCompare'
import { BasicsSection } from './sections/BasicsSection'
import { CompareMetadataSection } from './sections/CompareMetadataSection'
import { MetadataSection } from './sections/MetadataSection'
import { NotesSection } from './sections/NotesSection'
import { OverviewSection } from './sections/OverviewSection'
import { useInspectorMetadataWorkflow } from './hooks/useInspectorMetadataWorkflow'
import { useInspectorSidecarWorkflow } from './hooks/useInspectorSidecarWorkflow'

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
  onResize?: (e: React.PointerEvent<HTMLDivElement>) => void
  onStarChanged?: (paths: string[], val: StarRating) => void
  sortSpec?: SortSpec
  onFindSimilar?: () => void
  embeddingsAvailable?: boolean
  embeddingsLoading?: boolean
  onLocalTypingChange?: (active: boolean) => void
}

type InspectorSectionKey = 'overview' | 'compare' | 'basics' | 'metadata' | 'notes'

const INSPECTOR_SECTION_KEYS: InspectorSectionKey[] = ['overview', 'compare', 'basics', 'metadata', 'notes']
const INSPECTOR_SECTION_STORAGE_KEY = 'lenslet.inspector.sections'
const INSPECTOR_METRICS_EXPANDED_KEY = 'lenslet.inspector.metricsExpanded'
const METRICS_PREVIEW_LIMIT = 12
const COMPARE_DIFF_LIMIT = 120
const COMPARE_DIFF_MAX_DEPTH = 8
const COMPARE_DIFF_MAX_ARRAY = 80
const DEFAULT_SECTION_STATE: Record<InspectorSectionKey, boolean> = {
  overview: true,
  compare: true,
  metadata: true,
  basics: true,
  notes: true,
}

export default function Inspector({
  path,
  selectedPaths = [],
  items = [],
  compareActive = false,
  compareA = null,
  compareB = null,
  onResize,
  onStarChanged,
  sortSpec,
  onFindSimilar,
  embeddingsAvailable = false,
  embeddingsLoading = false,
  onLocalTypingChange,
}: InspectorProps) {
  const enabled = !!path
  const { data } = useSidecar(path ?? '')
  const mut = useUpdateSidecar(path ?? '')
  const qc = useQueryClient()

  const [openSections, setOpenSections] = useState<Record<InspectorSectionKey, boolean>>(DEFAULT_SECTION_STATE)
  const toggleSection = useCallback((key: InspectorSectionKey) => {
    setOpenSections((prev) => ({ ...prev, [key]: !prev[key] }))
  }, [])
  const toggleOverviewSection = useCallback(() => toggleSection('overview'), [toggleSection])
  const toggleCompareSection = useCallback(() => toggleSection('compare'), [toggleSection])
  const toggleBasicsSection = useCallback(() => toggleSection('basics'), [toggleSection])
  const toggleMetadataSection = useCallback(() => toggleSection('metadata'), [toggleSection])
  const toggleNotesSection = useCallback(() => toggleSection('notes'), [toggleSection])
  
  const [metricsExpanded, setMetricsExpanded] = useState(false)
  const multi = selectedPaths.length > 1

  const canFindSimilar = !!onFindSimilar && embeddingsAvailable && !multi
  const findSimilarDisabledReason = (() => {
    if (!onFindSimilar) return null
    if (!embeddingsAvailable) return embeddingsLoading ? 'Loading embeddings...' : 'No embeddings detected.'
    if (multi) return 'Select a single image to search.'
    return null
  })()

  const [copiedField, setCopiedField] = useState<string | null>(null)
  const [valueHeights, setValueHeights] = useState<Record<string, number>>({})

  const [metaCopied, setMetaCopied] = useState(false)
  const [metaValueCopiedPath, setMetaValueCopiedPath] = useState<string | null>(null)
  const metaValueCopyTimeoutRef = useRef<number | null>(null)
  const [compareMetaCopied, setCompareMetaCopied] = useState<'A' | 'B' | null>(null)
  const [compareValueCopiedPathA, setCompareValueCopiedPathA] = useState<string | null>(null)
  const [compareValueCopiedPathB, setCompareValueCopiedPathB] = useState<string | null>(null)
  const compareValueCopyTimeoutRef = useRef<number | null>(null)
  
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
    compareReady,
    comparePathA,
    comparePathB,
  })
  
  const selectedItems = useMemo(() => {
    const set = new Set(selectedPaths)
    return items.filter((i) => set.has(i.path))
  }, [items, selectedPaths])
  
  const totalSize = useMemo(
    () => selectedItems.reduce((acc, it) => acc + (it.size || 0), 0),
    [selectedItems]
  )

  useEffect(() => {
    setMetaCopied(false)
    setMetaValueCopiedPath(null)
    if (metaValueCopyTimeoutRef.current) {
      window.clearTimeout(metaValueCopyTimeoutRef.current)
      metaValueCopyTimeoutRef.current = null
    }
  }, [data?.updated_at, path])

  useEffect(() => {
    setCompareMetaCopied(null)
    setCompareValueCopiedPathA(null)
    setCompareValueCopiedPathB(null)
    if (compareValueCopyTimeoutRef.current) {
      window.clearTimeout(compareValueCopyTimeoutRef.current)
      compareValueCopyTimeoutRef.current = null
    }
  }, [comparePathA, comparePathB, compareReady])

  useEffect(() => {
    return () => {
      if (metaValueCopyTimeoutRef.current) {
        window.clearTimeout(metaValueCopyTimeoutRef.current)
        metaValueCopyTimeoutRef.current = null
      }
      if (compareValueCopyTimeoutRef.current) {
        window.clearTimeout(compareValueCopyTimeoutRef.current)
        compareValueCopyTimeoutRef.current = null
      }
    }
  }, [])

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
      setMetaCopied(true)
      setTimeout(() => setMetaCopied(false), 1200)
    }).catch((err) => {
      const msg = err instanceof Error ? err.message : 'Copy failed'
      setMetaError(msg)
    })
  }, [metaRawText])

  const metaDisplayHtml = useMemo(() => {
    if (!metadataSectionOpen || !metaDisplayValue) return ''
    return renderJsonValue(metaDisplayValue, [], 0)
  }, [metadataSectionOpen, metaDisplayValue])

  const compareDisplayHtmlA = useMemo(() => {
    if (!compareSectionOpen || !compareDisplayValueA) return ''
    return renderJsonValue(compareDisplayValueA, [], 0)
  }, [compareSectionOpen, compareDisplayValueA])

  const compareDisplayHtmlB = useMemo(() => {
    if (!compareSectionOpen || !compareDisplayValueB) return ''
    return renderJsonValue(compareDisplayValueB, [], 0)
  }, [compareSectionOpen, compareDisplayValueB])

  const triggerValueToast = useCallback((path: string) => {
    setMetaValueCopiedPath(path)
    if (metaValueCopyTimeoutRef.current) {
      window.clearTimeout(metaValueCopyTimeoutRef.current)
    }
    metaValueCopyTimeoutRef.current = window.setTimeout(() => {
      setMetaValueCopiedPath(null)
      metaValueCopyTimeoutRef.current = null
    }, 900)
  }, [])

  const copyMetadataValue = useCallback((path: string, value: unknown) => {
    const text = formatCopyValue(value)
    navigator.clipboard?.writeText(text).then(() => {
      triggerValueToast(path)
    }).catch(() => {})
  }, [triggerValueToast])

  const triggerCompareValueToast = useCallback((side: 'A' | 'B', path: string) => {
    if (side === 'A') {
      setCompareValueCopiedPathA(path)
    } else {
      setCompareValueCopiedPathB(path)
    }
    if (compareValueCopyTimeoutRef.current) {
      window.clearTimeout(compareValueCopyTimeoutRef.current)
    }
    compareValueCopyTimeoutRef.current = window.setTimeout(() => {
      setCompareValueCopiedPathA(null)
      setCompareValueCopiedPathB(null)
      compareValueCopyTimeoutRef.current = null
    }, 900)
  }, [])

  const copyCompareMetadataValue = useCallback((side: 'A' | 'B', path: string, value: unknown) => {
    const text = formatCopyValue(value)
    navigator.clipboard?.writeText(text).then(() => {
      triggerCompareValueToast(side, path)
    }).catch(() => {})
  }, [triggerCompareValueToast])

  const handleMetaClick = useCallback((e: React.MouseEvent) => {
    if (!metaDisplayValue) return
    const target = e.target as HTMLElement | null
    if (!target) return
    const keyEl = target.closest('[data-json-path]') as HTMLElement | null
    if (!keyEl) return
    const rawPath = keyEl.getAttribute('data-json-path')
    if (!rawPath) return
    let path: Array<string | number>
    try {
      path = JSON.parse(rawPath) as Array<string | number>
    } catch {
      return
    }
    const value = getValueAtPath(metaDisplayValue, path)
    copyMetadataValue(formatPathLabel(path), value)
  }, [metaDisplayValue, copyMetadataValue])

  const handleCompareMetaClickA = useCallback((e: React.MouseEvent) => {
    if (!compareDisplayValueA) return
    const target = e.target as HTMLElement | null
    if (!target) return
    const keyEl = target.closest('[data-json-path]') as HTMLElement | null
    if (!keyEl) return
    const rawPath = keyEl.getAttribute('data-json-path')
    if (!rawPath) return
    let path: Array<string | number>
    try {
      path = JSON.parse(rawPath) as Array<string | number>
    } catch {
      return
    }
    const value = getValueAtPath(compareDisplayValueA, path)
    copyCompareMetadataValue('A', formatPathLabel(path), value)
  }, [compareDisplayValueA, copyCompareMetadataValue])

  const handleCompareMetaClickB = useCallback((e: React.MouseEvent) => {
    if (!compareDisplayValueB) return
    const target = e.target as HTMLElement | null
    if (!target) return
    const keyEl = target.closest('[data-json-path]') as HTMLElement | null
    if (!keyEl) return
    const rawPath = keyEl.getAttribute('data-json-path')
    if (!rawPath) return
    let path: Array<string | number>
    try {
      path = JSON.parse(rawPath) as Array<string | number>
    } catch {
      return
    }
    const value = getValueAtPath(compareDisplayValueB, path)
    copyCompareMetadataValue('B', formatPathLabel(path), value)
  }, [compareDisplayValueB, copyCompareMetadataValue])

  const copyCompareMetadata = useCallback((side: 'A' | 'B') => {
    const raw = side === 'A' ? compareMetaRawTextA : compareMetaRawTextB
    if (!raw) return
    navigator.clipboard?.writeText(raw).then(() => {
      setCompareMetaCopied(side)
      setTimeout(() => setCompareMetaCopied((curr) => (curr === side ? null : curr)), 1200)
    }).catch(() => {})
  }, [compareMetaRawTextA, compareMetaRawTextB])

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

  useEffect(() => {
    try {
      const raw = localStorage.getItem(INSPECTOR_SECTION_STORAGE_KEY)
      if (!raw) return
      const parsed = JSON.parse(raw) as Record<string, unknown>
      if (!parsed || typeof parsed !== 'object') return
      const restored: Partial<Record<InspectorSectionKey, boolean>> = {}
      for (const key of INSPECTOR_SECTION_KEYS) {
        if (typeof parsed[key] === 'boolean') restored[key] = parsed[key] as boolean
      }
      if (Object.keys(restored).length > 0) {
        setOpenSections((prev) => ({ ...prev, ...restored }))
      }
    } catch {
      // Ignore localStorage parsing errors
    }
  }, [])

  useEffect(() => {
    try {
      localStorage.setItem(INSPECTOR_SECTION_STORAGE_KEY, JSON.stringify(openSections))
    } catch {
      // Ignore localStorage write errors
    }
  }, [openSections])

  useEffect(() => {
    try {
      const raw = localStorage.getItem(INSPECTOR_METRICS_EXPANDED_KEY)
      if (raw === '1' || raw === 'true') {
        setMetricsExpanded(true)
      } else if (raw === '0' || raw === 'false') {
        setMetricsExpanded(false)
      }
    } catch {
      // Ignore localStorage parsing errors
    }
  }, [])

  useEffect(() => {
    try {
      localStorage.setItem(INSPECTOR_METRICS_EXPANDED_KEY, metricsExpanded ? '1' : '0')
    } catch {
      // Ignore localStorage write errors
    }
  }, [metricsExpanded])

  const copyInfo = useCallback((key: string, text: string) => {
    if (!text) return
    navigator.clipboard?.writeText(text).then(() => {
      setCopiedField(key)
      setTimeout(() => setCopiedField((curr) => (curr === key ? null : curr)), 1000)
    }).catch(() => {})
  }, [])

  const rememberHeight = useCallback((key: string, el: HTMLSpanElement | null) => {
    if (el && !valueHeights[key]) {
      const h = el.offsetHeight
      if (h) {
        setValueHeights((prev) => (prev[key] ? prev : { ...prev, [key]: h }))
      }
    }
  }, [valueHeights])

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

  const handleToggleMetricsExpanded = useCallback(() => {
    setMetricsExpanded((prev) => !prev)
  }, [])
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

  const resizeHandleClass = 'toolbar-offset sidebar-resize-handle absolute bottom-0 left-0'

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
          compareDisplayHtmlA={compareDisplayHtmlA}
          compareDisplayHtmlB={compareDisplayHtmlB}
          compareMetaContent={compareMetaContent}
          onCompareMetaClickA={handleCompareMetaClickA}
          onCompareMetaClickB={handleCompareMetaClickB}
          compareExportLabelsText={compareExportLabelsText}
          onCompareExportLabelsTextChange={handleCompareExportLabelsTextChange}
          compareExportEmbedMetadata={compareExportEmbedMetadata}
          onCompareExportEmbedMetadataChange={handleCompareExportEmbedMetadataChange}
          compareExportBusy={compareExportBusy}
          compareReady={compareReady}
          compareExportMode={compareExportMode}
          onComparisonExport={handleComparisonExport}
          compareExportError={compareExportError}
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
        valueHeights={valueHeights}
        onRememberHeight={rememberHeight}
        metricsExpanded={metricsExpanded}
        onToggleMetricsExpanded={handleToggleMetricsExpanded}
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
          metaDisplayHtml={metaDisplayHtml}
          metaContent={metaContent}
          metaError={metaError}
          onMetaClick={handleMetaClick}
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
