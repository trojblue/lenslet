import { useCallback, useEffect, useRef, useState } from 'react'
import type { Dispatch, SetStateAction } from 'react'
import { api } from '../../../shared/api/client'
import { downloadBlob } from '../../../app/utils/appShellHelpers'
import {
  DEFAULT_EXPORT_COMPARISON_EMBED_METADATA,
  buildComparisonExportFilename,
  buildExportComparisonPayload,
} from '../exportComparison'

type MetadataState = 'idle' | 'loading' | 'loaded' | 'error'

type UseInspectorMetadataWorkflowParams = {
  path: string | null
  sidecarUpdatedAt: string | undefined
  compareReady: boolean
  comparePathA: string | null
  comparePathB: string | null
}

type UseInspectorMetadataWorkflowResult = {
  metaRaw: Record<string, unknown> | null
  metaError: string | null
  metaState: MetadataState
  showPilInfo: boolean
  setMetaError: Dispatch<SetStateAction<string | null>>
  compareMetaState: MetadataState
  compareMetaError: string | null
  compareMetaA: Record<string, unknown> | null
  compareMetaB: Record<string, unknown> | null
  compareIncludePilInfo: boolean
  compareShowPilInfoA: boolean
  compareShowPilInfoB: boolean
  compareExportLabelsText: string
  compareExportEmbedMetadata: boolean
  compareExportMode: 'normal' | 'reverse' | null
  compareExportError: string | null
  compareExportBusy: boolean
  setShowPilInfo: Dispatch<SetStateAction<boolean>>
  setCompareIncludePilInfo: Dispatch<SetStateAction<boolean>>
  setCompareShowPilInfoA: Dispatch<SetStateAction<boolean>>
  setCompareShowPilInfoB: Dispatch<SetStateAction<boolean>>
  fetchMetadata: () => Promise<void>
  reloadCompareMetadata: () => void
  handleCompareExportLabelsTextChange: (value: string) => void
  handleCompareExportEmbedMetadataChange: (checked: boolean) => void
  runComparisonExport: (reverseOrder: boolean) => Promise<void>
}

export function useInspectorMetadataWorkflow({
  path,
  sidecarUpdatedAt,
  compareReady,
  comparePathA,
  comparePathB,
}: UseInspectorMetadataWorkflowParams): UseInspectorMetadataWorkflowResult {
  const [metaRaw, setMetaRaw] = useState<Record<string, unknown> | null>(null)
  const [metaError, setMetaError] = useState<string | null>(null)
  const [metaState, setMetaState] = useState<MetadataState>('idle')
  const [showPilInfo, setShowPilInfo] = useState(false)

  const [compareMetaState, setCompareMetaState] = useState<MetadataState>('idle')
  const [compareMetaError, setCompareMetaError] = useState<string | null>(null)
  const [compareMetaA, setCompareMetaA] = useState<Record<string, unknown> | null>(null)
  const [compareMetaB, setCompareMetaB] = useState<Record<string, unknown> | null>(null)
  const [compareIncludePilInfo, setCompareIncludePilInfo] = useState(false)
  const [compareShowPilInfoA, setCompareShowPilInfoA] = useState(false)
  const [compareShowPilInfoB, setCompareShowPilInfoB] = useState(false)
  const compareMetaRequestIdRef = useRef(0)

  const [compareExportLabelsText, setCompareExportLabelsText] = useState('')
  const [compareExportEmbedMetadata, setCompareExportEmbedMetadata] = useState(
    DEFAULT_EXPORT_COMPARISON_EMBED_METADATA,
  )
  const [compareExportMode, setCompareExportMode] = useState<'normal' | 'reverse' | null>(null)
  const [compareExportError, setCompareExportError] = useState<string | null>(null)
  const compareExportBusy = compareExportMode !== null

  useEffect(() => {
    setMetaRaw(null)
    setMetaError(null)
    setMetaState('idle')
    setShowPilInfo(false)
  }, [path, sidecarUpdatedAt])

  const fetchMetadata = useCallback(async () => {
    if (!path) return
    setMetaState('loading')
    setMetaError(null)
    try {
      const res = await api.getMetadata(path)
      setMetaRaw(res.meta)
      setMetaState('loaded')
    } catch (err) {
      const msg = err instanceof Error ? err.message : 'Failed to load metadata'
      setMetaRaw(null)
      setMetaError(msg)
      setMetaState('error')
    }
  }, [path])

  const fetchCompareMetadata = useCallback(async (aPath: string, bPath: string) => {
    const requestId = compareMetaRequestIdRef.current + 1
    compareMetaRequestIdRef.current = requestId
    setCompareMetaState('loading')
    setCompareMetaError(null)
    try {
      const [aRes, bRes] = await Promise.all([api.getMetadata(aPath), api.getMetadata(bPath)])
      if (compareMetaRequestIdRef.current !== requestId) return
      setCompareMetaA(aRes.meta)
      setCompareMetaB(bRes.meta)
      setCompareMetaState('loaded')
    } catch (err) {
      if (compareMetaRequestIdRef.current !== requestId) return
      const msg = err instanceof Error ? err.message : 'Failed to load metadata'
      setCompareMetaA(null)
      setCompareMetaB(null)
      setCompareMetaError(msg)
      setCompareMetaState('error')
    }
  }, [])

  useEffect(() => {
    if (!compareReady || !comparePathA || !comparePathB) {
      compareMetaRequestIdRef.current += 1
      setCompareMetaState('idle')
      setCompareMetaError(null)
      setCompareMetaA(null)
      setCompareMetaB(null)
      setCompareShowPilInfoA(false)
      setCompareShowPilInfoB(false)
      setCompareExportLabelsText('')
      setCompareExportEmbedMetadata(DEFAULT_EXPORT_COMPARISON_EMBED_METADATA)
      setCompareExportMode(null)
      setCompareExportError(null)
      return
    }
    setCompareIncludePilInfo(false)
    setCompareShowPilInfoA(false)
    setCompareShowPilInfoB(false)
    setCompareExportMode(null)
    setCompareExportError(null)
    void fetchCompareMetadata(comparePathA, comparePathB)
  }, [compareReady, comparePathA, comparePathB, fetchCompareMetadata])

  const reloadCompareMetadata = useCallback(() => {
    if (!comparePathA || !comparePathB) return
    void fetchCompareMetadata(comparePathA, comparePathB)
  }, [comparePathA, comparePathB, fetchCompareMetadata])

  const handleCompareExportLabelsTextChange = useCallback((value: string) => {
    setCompareExportLabelsText(value)
    setCompareExportError(null)
  }, [])

  const handleCompareExportEmbedMetadataChange = useCallback((checked: boolean) => {
    setCompareExportEmbedMetadata(checked)
  }, [])

  const runComparisonExport = useCallback(
    async (reverseOrder: boolean) => {
      if (!comparePathA || !comparePathB) {
        setCompareExportError('Comparison export requires two selected images.')
        return
      }
      if (compareExportBusy) return

      const payloadResult = buildExportComparisonPayload({
        pathA: comparePathA,
        pathB: comparePathB,
        labelsText: compareExportLabelsText,
        embedMetadata: compareExportEmbedMetadata,
        reverseOrder,
      })
      if (!payloadResult.ok) {
        setCompareExportError(payloadResult.message)
        return
      }

      setCompareExportMode(reverseOrder ? 'reverse' : 'normal')
      setCompareExportError(null)
      try {
        const blob = await api.exportComparison(payloadResult.payload)
        downloadBlob(blob, buildComparisonExportFilename(reverseOrder))
      } catch (err) {
        const msg = err instanceof Error ? err.message : 'Failed to export comparison.'
        setCompareExportError(msg)
      } finally {
        setCompareExportMode(null)
      }
    },
    [
      compareExportBusy,
      compareExportEmbedMetadata,
      compareExportLabelsText,
      comparePathA,
      comparePathB,
    ],
  )

  return {
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
  }
}
