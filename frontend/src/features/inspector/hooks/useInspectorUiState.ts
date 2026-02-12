import { useCallback, useEffect, useRef, useState } from 'react'
import type { MutableRefObject } from 'react'

export type InspectorSectionKey = 'overview' | 'compare' | 'basics' | 'metadata' | 'notes'

type CompareSide = 'A' | 'B'

type UseInspectorUiStateParams = {
  path: string | null
  sidecarUpdatedAt: string | undefined
  compareReady: boolean
  comparePathA: string | null
  comparePathB: string | null
}

type UseInspectorUiStateResult = {
  openSections: Record<InspectorSectionKey, boolean>
  toggleOverviewSection: () => void
  toggleCompareSection: () => void
  toggleBasicsSection: () => void
  toggleMetadataSection: () => void
  toggleNotesSection: () => void
  metricsExpanded: boolean
  toggleMetricsExpanded: () => void
  copiedField: string | null
  markInfoCopied: (key: string) => void
  metaCopied: boolean
  markMetadataCopied: () => void
  metaValueCopiedPath: string | null
  markMetadataValueCopied: (path: string) => void
  compareMetaCopied: CompareSide | null
  markCompareMetadataCopied: (side: CompareSide) => void
  compareValueCopiedPathA: string | null
  compareValueCopiedPathB: string | null
  markCompareMetadataValueCopied: (side: CompareSide, path: string) => void
}

const INSPECTOR_SECTION_KEYS: InspectorSectionKey[] = ['overview', 'compare', 'basics', 'metadata', 'notes']
const INSPECTOR_SECTION_STORAGE_KEY = 'lenslet.inspector.sections'
const INSPECTOR_METRICS_EXPANDED_KEY = 'lenslet.inspector.metricsExpanded'
const DEFAULT_SECTION_STATE: Record<InspectorSectionKey, boolean> = {
  overview: true,
  compare: true,
  metadata: true,
  basics: true,
  notes: true,
}

function clearTimer(timerRef: MutableRefObject<number | null>): void {
  if (timerRef.current === null) return
  window.clearTimeout(timerRef.current)
  timerRef.current = null
}

export function useInspectorUiState({
  path,
  sidecarUpdatedAt,
  compareReady,
  comparePathA,
  comparePathB,
}: UseInspectorUiStateParams): UseInspectorUiStateResult {
  const [openSections, setOpenSections] = useState<Record<InspectorSectionKey, boolean>>(DEFAULT_SECTION_STATE)
  const [metricsExpanded, setMetricsExpanded] = useState(false)

  const [copiedField, setCopiedField] = useState<string | null>(null)
  const [metaCopied, setMetaCopied] = useState(false)
  const [metaValueCopiedPath, setMetaValueCopiedPath] = useState<string | null>(null)
  const [compareMetaCopied, setCompareMetaCopied] = useState<CompareSide | null>(null)
  const [compareValueCopiedPathA, setCompareValueCopiedPathA] = useState<string | null>(null)
  const [compareValueCopiedPathB, setCompareValueCopiedPathB] = useState<string | null>(null)

  const infoCopyTimeoutRef = useRef<number | null>(null)
  const metaCopiedTimeoutRef = useRef<number | null>(null)
  const metaValueCopyTimeoutRef = useRef<number | null>(null)
  const compareMetaCopiedTimeoutRef = useRef<number | null>(null)
  const compareValueCopyTimeoutRef = useRef<number | null>(null)

  const toggleSection = useCallback((key: InspectorSectionKey) => {
    setOpenSections((prev) => ({ ...prev, [key]: !prev[key] }))
  }, [])

  const toggleOverviewSection = useCallback(() => toggleSection('overview'), [toggleSection])
  const toggleCompareSection = useCallback(() => toggleSection('compare'), [toggleSection])
  const toggleBasicsSection = useCallback(() => toggleSection('basics'), [toggleSection])
  const toggleMetadataSection = useCallback(() => toggleSection('metadata'), [toggleSection])
  const toggleNotesSection = useCallback(() => toggleSection('notes'), [toggleSection])

  const toggleMetricsExpanded = useCallback(() => {
    setMetricsExpanded((prev) => !prev)
  }, [])

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

  const markCompareMetadataCopied = useCallback((side: CompareSide) => {
    setCompareMetaCopied(side)
    clearTimer(compareMetaCopiedTimeoutRef)
    compareMetaCopiedTimeoutRef.current = window.setTimeout(() => {
      setCompareMetaCopied((curr) => (curr === side ? null : curr))
      compareMetaCopiedTimeoutRef.current = null
    }, 1200)
  }, [])

  const markCompareMetadataValueCopied = useCallback((side: CompareSide, pathLabel: string) => {
    if (side === 'A') {
      setCompareValueCopiedPathA(pathLabel)
    } else {
      setCompareValueCopiedPathB(pathLabel)
    }
    clearTimer(compareValueCopyTimeoutRef)
    compareValueCopyTimeoutRef.current = window.setTimeout(() => {
      setCompareValueCopiedPathA(null)
      setCompareValueCopiedPathB(null)
      compareValueCopyTimeoutRef.current = null
    }, 900)
  }, [])

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

  useEffect(() => {
    setMetaCopied(false)
    setMetaValueCopiedPath(null)
    clearTimer(metaCopiedTimeoutRef)
    clearTimer(metaValueCopyTimeoutRef)
  }, [path, sidecarUpdatedAt])

  useEffect(() => {
    setCompareMetaCopied(null)
    setCompareValueCopiedPathA(null)
    setCompareValueCopiedPathB(null)
    clearTimer(compareMetaCopiedTimeoutRef)
    clearTimer(compareValueCopyTimeoutRef)
  }, [comparePathA, comparePathB, compareReady])

  useEffect(
    () => () => {
      clearTimer(infoCopyTimeoutRef)
      clearTimer(metaCopiedTimeoutRef)
      clearTimer(metaValueCopyTimeoutRef)
      clearTimer(compareMetaCopiedTimeoutRef)
      clearTimer(compareValueCopyTimeoutRef)
    },
    [],
  )

  return {
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
  }
}
