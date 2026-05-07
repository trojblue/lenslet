import { useCallback, useEffect, useRef, useState } from 'react'
import type { MutableRefObject } from 'react'
import {
  INSPECTOR_WIDGET_DEFAULT_ORDER,
  parseStoredInspectorWidgetOrder,
  reorderInspectorWidgetOrder,
  type InspectorWidgetId,
} from '../model/inspectorWidgetOrder'
import {
  parseQuickViewCustomPathsInput,
  parseStoredQuickViewCustomPaths,
} from '../model/quickViewFields'
import {
  readInspectorStoredBool,
  readInspectorStoredValue,
  writeInspectorStoredBool,
  writeInspectorStoredJson,
} from './inspectorStorage'

export type InspectorSectionKey = 'quickView' | 'overview' | 'compare' | 'basics' | 'metadata' | 'notes'

type UseInspectorUiStateParams = {
  path: string | null
  sidecarUpdatedAt: string | undefined
  comparePaths: string[]
  selectedCount: number
  metadataCompareAvailable: boolean
  autoloadMetadataCompare: boolean
}

type UseInspectorUiStateResult = {
  sectionOrder: InspectorWidgetId[]
  reorderSectionOrder: (activeId: InspectorWidgetId, overId: InspectorWidgetId) => void
  metadataCompareActive: boolean
  metadataCompareReady: boolean
  toggleMetadataCompareActive: () => void
  openSections: Record<InspectorSectionKey, boolean>
  toggleQuickViewSection: () => void
  toggleOverviewSection: () => void
  toggleCompareSection: () => void
  toggleBasicsSection: () => void
  toggleMetadataSection: () => void
  toggleNotesSection: () => void
  quickViewCustomPaths: string[]
  quickViewCustomPathsDraft: string
  quickViewCustomPathsError: string | null
  setQuickViewCustomPathsDraft: (value: string) => void
  saveQuickViewCustomPaths: () => void
  quickViewCopiedRowId: string | null
  markQuickViewValueCopied: (rowId: string) => void
  metricsExpanded: boolean
  toggleMetricsExpanded: () => void
  copiedField: string | null
  markInfoCopied: (key: string) => void
  metaCopied: boolean
  markMetadataCopied: () => void
  metaValueCopiedPath: string | null
  markMetadataValueCopied: (path: string) => void
}

const INSPECTOR_SECTION_KEYS: InspectorSectionKey[] = [
  'quickView',
  'overview',
  'compare',
  'basics',
  'metadata',
  'notes',
]
const INSPECTOR_SECTION_STORAGE_KEY = 'lenslet.inspector.sections'
const INSPECTOR_SECTION_ORDER_STORAGE_KEY = 'lenslet.inspector.sectionOrder.v2'
const INSPECTOR_METRICS_EXPANDED_KEY = 'lenslet.inspector.metricsExpanded'
const INSPECTOR_QUICK_VIEW_PATHS_STORAGE_KEY = 'lenslet.inspector.quickView.paths.v1'
const DEFAULT_SECTION_STATE: Record<InspectorSectionKey, boolean> = {
  quickView: true,
  overview: true,
  compare: true,
  metadata: true,
  basics: true,
  notes: true,
}

export function toggleInspectorSectionState(
  sections: Record<InspectorSectionKey, boolean>,
  key: InspectorSectionKey,
): Record<InspectorSectionKey, boolean> {
  return { ...sections, [key]: !sections[key] }
}

export function shouldDisableMetadataCompare(
  selectedCount: number,
  metadataCompareAvailable: boolean,
): boolean {
  return selectedCount < 2 || !metadataCompareAvailable
}

export function shouldAutoActivateMetadataCompare(
  autoloadMetadataCompare: boolean,
  selectedCount: number,
  metadataCompareAvailable: boolean,
): boolean {
  return autoloadMetadataCompare && !shouldDisableMetadataCompare(selectedCount, metadataCompareAvailable)
}

function clearTimer(timerRef: MutableRefObject<number | null>): void {
  if (timerRef.current === null) return
  window.clearTimeout(timerRef.current)
  timerRef.current = null
}

export function useInspectorUiState({
  path,
  sidecarUpdatedAt,
  comparePaths,
  selectedCount,
  metadataCompareAvailable,
  autoloadMetadataCompare,
}: UseInspectorUiStateParams): UseInspectorUiStateResult {
  const [sectionOrder, setSectionOrder] = useState<InspectorWidgetId[]>([
    ...INSPECTOR_WIDGET_DEFAULT_ORDER,
  ])
  const [metadataCompareActive, setMetadataCompareActive] = useState(false)
  const [openSections, setOpenSections] = useState<Record<InspectorSectionKey, boolean>>(DEFAULT_SECTION_STATE)
  const [quickViewCustomPaths, setQuickViewCustomPaths] = useState<string[]>([])
  const [quickViewCustomPathsDraft, setQuickViewCustomPathsDraft] = useState('')
  const [quickViewCustomPathsError, setQuickViewCustomPathsError] = useState<string | null>(null)
  const [quickViewCopiedRowId, setQuickViewCopiedRowId] = useState<string | null>(null)
  const [metricsExpanded, setMetricsExpanded] = useState(false)
  const metadataCompareReady = metadataCompareActive && comparePaths.length >= 2
  const previousMetadataCompareActiveRef = useRef(metadataCompareActive)

  const [copiedField, setCopiedField] = useState<string | null>(null)
  const [metaCopied, setMetaCopied] = useState(false)
  const [metaValueCopiedPath, setMetaValueCopiedPath] = useState<string | null>(null)

  const infoCopyTimeoutRef = useRef<number | null>(null)
  const metaCopiedTimeoutRef = useRef<number | null>(null)
  const metaValueCopyTimeoutRef = useRef<number | null>(null)
  const quickViewCopyTimeoutRef = useRef<number | null>(null)

  const toggleSection = useCallback((key: InspectorSectionKey) => {
    setOpenSections((prev) => toggleInspectorSectionState(prev, key))
  }, [])
  const toggleMetadataCompareActive = useCallback(() => {
    if (shouldDisableMetadataCompare(selectedCount, metadataCompareAvailable)) return
    setMetadataCompareActive((prev) => !prev)
  }, [metadataCompareAvailable, selectedCount])

  const toggleQuickViewSection = useCallback(() => toggleSection('quickView'), [toggleSection])
  const toggleOverviewSection = useCallback(() => toggleSection('overview'), [toggleSection])
  const toggleCompareSection = useCallback(() => toggleSection('compare'), [toggleSection])
  const toggleBasicsSection = useCallback(() => toggleSection('basics'), [toggleSection])
  const toggleMetadataSection = useCallback(() => toggleSection('metadata'), [toggleSection])
  const toggleNotesSection = useCallback(() => toggleSection('notes'), [toggleSection])
  const reorderSectionOrder = useCallback((activeId: InspectorWidgetId, overId: InspectorWidgetId) => {
    setSectionOrder((prev) => reorderInspectorWidgetOrder(prev, activeId, overId))
  }, [])

  const toggleMetricsExpanded = useCallback(() => {
    setMetricsExpanded((prev) => !prev)
  }, [])

  const saveQuickViewCustomPaths = useCallback(() => {
    const parsed = parseQuickViewCustomPathsInput(quickViewCustomPathsDraft)
    if (parsed.error) {
      setQuickViewCustomPathsError(parsed.error)
      return
    }
    setQuickViewCustomPathsError(null)
    setQuickViewCustomPaths(parsed.paths)
    setQuickViewCustomPathsDraft(parsed.paths.join('\n'))
  }, [quickViewCustomPathsDraft])

  const handleQuickViewCustomPathsDraftChange = useCallback(
    (value: string) => {
      setQuickViewCustomPathsDraft(value)
      if (quickViewCustomPathsError !== null) {
        setQuickViewCustomPathsError(null)
      }
    },
    [quickViewCustomPathsError],
  )

  const markInfoCopied = useCallback((key: string) => {
    setCopiedField(key)
    clearTimer(infoCopyTimeoutRef)
    infoCopyTimeoutRef.current = window.setTimeout(() => {
      setCopiedField((curr) => (curr === key ? null : curr))
      infoCopyTimeoutRef.current = null
    }, 1000)
  }, [])

  const markMetadataCopied = useCallback(() => {
    setMetaCopied(true)
    clearTimer(metaCopiedTimeoutRef)
    metaCopiedTimeoutRef.current = window.setTimeout(() => {
      setMetaCopied(false)
      metaCopiedTimeoutRef.current = null
    }, 1200)
  }, [])

  const markMetadataValueCopied = useCallback((pathLabel: string) => {
    setMetaValueCopiedPath(pathLabel)
    clearTimer(metaValueCopyTimeoutRef)
    metaValueCopyTimeoutRef.current = window.setTimeout(() => {
      setMetaValueCopiedPath(null)
      metaValueCopyTimeoutRef.current = null
    }, 900)
  }, [])

  const markQuickViewValueCopied = useCallback((rowId: string) => {
    setQuickViewCopiedRowId(rowId)
    clearTimer(quickViewCopyTimeoutRef)
    quickViewCopyTimeoutRef.current = window.setTimeout(() => {
      setQuickViewCopiedRowId(null)
      quickViewCopyTimeoutRef.current = null
    }, 900)
  }, [])

  useEffect(() => {
    setSectionOrder(
      readInspectorStoredValue(
        INSPECTOR_SECTION_ORDER_STORAGE_KEY,
        (raw) => {
          const parsed = parseStoredInspectorWidgetOrder(raw)
          return {
            value: parsed.order,
            rewriteValue: parsed.shouldRewrite ? JSON.stringify(parsed.order) : undefined,
          }
        },
        [...INSPECTOR_WIDGET_DEFAULT_ORDER],
      ),
    )
  }, [])

  useEffect(() => {
    writeInspectorStoredJson(INSPECTOR_SECTION_ORDER_STORAGE_KEY, sectionOrder)
  }, [sectionOrder])

  useEffect(() => {
    const parsed = readInspectorStoredValue(
      INSPECTOR_QUICK_VIEW_PATHS_STORAGE_KEY,
      (raw) => {
        const stored = parseStoredQuickViewCustomPaths(raw)
        return {
          value: stored,
          rewriteValue: stored.shouldRewrite ? JSON.stringify(stored.paths) : undefined,
        }
      },
      { paths: [], shouldRewrite: false },
    )
    setQuickViewCustomPaths(parsed.paths)
    setQuickViewCustomPathsDraft(parsed.paths.join('\n'))
  }, [])

  useEffect(() => {
    writeInspectorStoredJson(INSPECTOR_QUICK_VIEW_PATHS_STORAGE_KEY, quickViewCustomPaths)
  }, [quickViewCustomPaths])

  useEffect(() => {
    const restored = readInspectorStoredValue(
      INSPECTOR_SECTION_STORAGE_KEY,
      (raw) => {
        if (!raw) {
          return { value: {} as Partial<Record<InspectorSectionKey, boolean>> }
        }
        const parsed = JSON.parse(raw) as Record<string, unknown>
        if (!parsed || typeof parsed !== 'object') {
          return { value: {} as Partial<Record<InspectorSectionKey, boolean>> }
        }
        const next: Partial<Record<InspectorSectionKey, boolean>> = {}
        for (const key of INSPECTOR_SECTION_KEYS) {
          if (typeof parsed[key] === 'boolean') {
            next[key] = parsed[key]
          }
        }
        return { value: next }
      },
      {},
    )
    if (Object.keys(restored).length > 0) {
      setOpenSections((prev) => ({ ...prev, ...restored }))
    }
  }, [])

  useEffect(() => {
    writeInspectorStoredJson(INSPECTOR_SECTION_STORAGE_KEY, openSections)
  }, [openSections])

  useEffect(() => {
    setMetricsExpanded(readInspectorStoredBool(INSPECTOR_METRICS_EXPANDED_KEY, false))
  }, [])

  useEffect(() => {
    writeInspectorStoredBool(INSPECTOR_METRICS_EXPANDED_KEY, metricsExpanded)
  }, [metricsExpanded])

  useEffect(() => {
    if (!shouldAutoActivateMetadataCompare(
      autoloadMetadataCompare,
      selectedCount,
      metadataCompareAvailable,
    )) return
    setMetadataCompareActive(true)
  }, [autoloadMetadataCompare, metadataCompareAvailable, selectedCount])

  useEffect(() => {
    if (!shouldDisableMetadataCompare(selectedCount, metadataCompareAvailable)) return
    setMetadataCompareActive(false)
  }, [metadataCompareAvailable, selectedCount])

  useEffect(() => {
    const wasActive = previousMetadataCompareActiveRef.current
    if (metadataCompareActive && !wasActive) {
      setOpenSections((prev) => (prev.compare ? prev : { ...prev, compare: true }))
    }
    previousMetadataCompareActiveRef.current = metadataCompareActive
  }, [metadataCompareActive])

  useEffect(() => {
    setMetaCopied(false)
    setMetaValueCopiedPath(null)
    setQuickViewCopiedRowId(null)
    clearTimer(metaCopiedTimeoutRef)
    clearTimer(metaValueCopyTimeoutRef)
    clearTimer(quickViewCopyTimeoutRef)
  }, [path, sidecarUpdatedAt])

  useEffect(
    () => () => {
      clearTimer(infoCopyTimeoutRef)
      clearTimer(metaCopiedTimeoutRef)
      clearTimer(metaValueCopyTimeoutRef)
      clearTimer(quickViewCopyTimeoutRef)
    },
    [],
  )

  return {
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
    setQuickViewCustomPathsDraft: handleQuickViewCustomPathsDraftChange,
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
  }
}
