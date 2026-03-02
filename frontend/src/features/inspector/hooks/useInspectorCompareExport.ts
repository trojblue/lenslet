import { useCallback, useEffect, useState } from 'react'
import { downloadBlob } from '../../../app/utils/appShellHelpers'
import type { ExportComparisonOutputFormat } from '../../../lib/types'
import { api } from '../../../shared/api/client'
import {
  type ExportComparisonPayloadResult,
  buildExportComparisonV2MaxPathsMessage,
  DEFAULT_EXPORT_COMPARISON_EMBED_METADATA,
  EXPORT_COMPARISON_PAIR_ONLY_MESSAGE,
  EXPORT_COMPARISON_V2_CAPABILITY_MESSAGE,
  buildComparisonExportFilename,
  buildExportComparisonPayload,
  buildExportComparisonPayloadV2,
} from '../compareExportBoundary'

const INSPECTOR_EXPORT_REVERSE_ORDER_KEY = 'lenslet.inspector.export.reverseOrder'
const INSPECTOR_EXPORT_HIGH_QUALITY_GIF_KEY = 'lenslet.inspector.export.highQualityGif'

function parseStoredBool(raw: string | null, fallback: boolean): boolean {
  if (raw === '1' || raw === 'true') return true
  if (raw === '0' || raw === 'false') return false
  return fallback
}

type UseInspectorCompareExportParams = {
  selectedPaths: string[]
  comparePathA: string | null
  comparePathB: string | null
  compareExportSupportsV2: boolean
  compareExportMaxPathsV2: number | null
}

type UseInspectorCompareExportResult = {
  compareExportLabelsText: string
  compareExportEmbedMetadata: boolean
  compareExportReverseOrder: boolean
  compareExportHighQualityGif: boolean
  compareExportMode: 'png' | 'gif' | null
  compareExportError: string | null
  compareExportBusy: boolean
  handleCompareExportLabelsTextChange: (value: string) => void
  handleCompareExportEmbedMetadataChange: (checked: boolean) => void
  handleCompareExportReverseOrderChange: (checked: boolean) => void
  handleCompareExportHighQualityGifChange: (checked: boolean) => void
  runComparisonExport: (outputFormat: ExportComparisonOutputFormat) => Promise<void>
}

type BuildInspectorComparisonExportPayloadArgs = {
  selectedPaths: string[]
  comparePathA: string | null
  comparePathB: string | null
  compareExportSupportsV2: boolean
  compareExportMaxPathsV2: number | null
  labelsText: string
  embedMetadata: boolean
  reverseOrder: boolean
  outputFormat: ExportComparisonOutputFormat
  highQualityGif: boolean
}

function resolveComparisonPairPaths({
  selectedPaths,
  comparePathA,
  comparePathB,
}: {
  selectedPaths: string[]
  comparePathA: string | null
  comparePathB: string | null
}): [string, string] | null {
  if (selectedPaths.length !== 2) return null
  if (comparePathA && comparePathB) return [comparePathA, comparePathB]

  const [pathA, pathB] = selectedPaths
  if (!pathA || !pathB) return null
  return [pathA, pathB]
}

export function buildInspectorComparisonExportPayload({
  selectedPaths,
  comparePathA,
  comparePathB,
  compareExportSupportsV2,
  compareExportMaxPathsV2,
  labelsText,
  embedMetadata,
  reverseOrder,
  outputFormat,
  highQualityGif,
}: BuildInspectorComparisonExportPayloadArgs): ExportComparisonPayloadResult {
  const selectedCount = selectedPaths.length
  if (selectedCount < 2) {
    return { ok: false, message: EXPORT_COMPARISON_PAIR_ONLY_MESSAGE }
  }

  if (selectedCount === 2) {
    const pairPaths = resolveComparisonPairPaths({
      selectedPaths,
      comparePathA,
      comparePathB,
    })
    if (!pairPaths) {
      return { ok: false, message: EXPORT_COMPARISON_PAIR_ONLY_MESSAGE }
    }
    const [pathA, pathB] = pairPaths
    return buildExportComparisonPayload({
      pathA,
      pathB,
      labelsText,
      embedMetadata,
      reverseOrder,
      outputFormat,
      highQualityGif,
    })
  }

  if (!compareExportSupportsV2) {
    return { ok: false, message: EXPORT_COMPARISON_V2_CAPABILITY_MESSAGE }
  }
  if (compareExportMaxPathsV2 !== null && selectedCount > compareExportMaxPathsV2) {
    return {
      ok: false,
      message: buildExportComparisonV2MaxPathsMessage(compareExportMaxPathsV2, selectedCount),
    }
  }
  return buildExportComparisonPayloadV2({
    paths: selectedPaths,
    labelsText,
    embedMetadata,
    reverseOrder,
    outputFormat,
    highQualityGif,
  })
}

export function useInspectorCompareExport({
  selectedPaths,
  comparePathA,
  comparePathB,
  compareExportSupportsV2,
  compareExportMaxPathsV2,
}: UseInspectorCompareExportParams): UseInspectorCompareExportResult {
  const [compareExportLabelsText, setCompareExportLabelsText] = useState('')
  const [compareExportEmbedMetadata, setCompareExportEmbedMetadata] = useState(
    DEFAULT_EXPORT_COMPARISON_EMBED_METADATA,
  )
  const [compareExportReverseOrder, setCompareExportReverseOrder] = useState(false)
  const [compareExportHighQualityGif, setCompareExportHighQualityGif] = useState(false)
  const [compareExportMode, setCompareExportMode] = useState<'png' | 'gif' | null>(null)
  const [compareExportError, setCompareExportError] = useState<string | null>(null)
  const compareExportBusy = compareExportMode !== null

  useEffect(() => {
    try {
      setCompareExportReverseOrder(
        parseStoredBool(localStorage.getItem(INSPECTOR_EXPORT_REVERSE_ORDER_KEY), false),
      )
      setCompareExportHighQualityGif(
        parseStoredBool(localStorage.getItem(INSPECTOR_EXPORT_HIGH_QUALITY_GIF_KEY), false),
      )
    } catch {
      // Ignore localStorage read errors.
    }
  }, [])

  useEffect(() => {
    try {
      localStorage.setItem(
        INSPECTOR_EXPORT_REVERSE_ORDER_KEY,
        compareExportReverseOrder ? '1' : '0',
      )
    } catch {
      // Ignore localStorage write errors.
    }
  }, [compareExportReverseOrder])

  useEffect(() => {
    try {
      localStorage.setItem(
        INSPECTOR_EXPORT_HIGH_QUALITY_GIF_KEY,
        compareExportHighQualityGif ? '1' : '0',
      )
    } catch {
      // Ignore localStorage write errors.
    }
  }, [compareExportHighQualityGif])

  useEffect(() => {
    if (selectedPaths.length < 2) {
      setCompareExportLabelsText('')
      setCompareExportEmbedMetadata(DEFAULT_EXPORT_COMPARISON_EMBED_METADATA)
      setCompareExportMode(null)
      setCompareExportError(null)
      return
    }
    setCompareExportMode(null)
    setCompareExportError(null)
  }, [comparePathA, comparePathB, selectedPaths])

  const handleCompareExportLabelsTextChange = useCallback((value: string) => {
    setCompareExportLabelsText(value)
    setCompareExportError(null)
  }, [])

  const handleCompareExportEmbedMetadataChange = useCallback((checked: boolean) => {
    setCompareExportEmbedMetadata(checked)
  }, [])

  const handleCompareExportReverseOrderChange = useCallback((checked: boolean) => {
    setCompareExportReverseOrder(checked)
  }, [])

  const handleCompareExportHighQualityGifChange = useCallback((checked: boolean) => {
    setCompareExportHighQualityGif(checked)
  }, [])

  const runComparisonExport = useCallback(
    async (outputFormat: ExportComparisonOutputFormat) => {
      if (compareExportBusy) return
      const selectedCount = selectedPaths.length
      const reverseOrder = compareExportReverseOrder

      if (selectedCount < 2) {
        setCompareExportError(EXPORT_COMPARISON_PAIR_ONLY_MESSAGE)
        return
      }

      const highQualityGif = outputFormat === 'gif' && compareExportHighQualityGif
      const payloadResult = buildInspectorComparisonExportPayload({
        selectedPaths,
        comparePathA,
        comparePathB,
        compareExportSupportsV2,
        compareExportMaxPathsV2,
        labelsText: compareExportLabelsText,
        embedMetadata: compareExportEmbedMetadata,
        reverseOrder,
        outputFormat,
        highQualityGif,
      })
      if (!payloadResult.ok) {
        setCompareExportError(payloadResult.message)
        return
      }

      setCompareExportMode(outputFormat)
      setCompareExportError(null)
      try {
        const blob = await api.exportComparison(payloadResult.payload)
        downloadBlob(blob, buildComparisonExportFilename(reverseOrder, outputFormat))
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
      compareExportHighQualityGif,
      compareExportLabelsText,
      compareExportMaxPathsV2,
      compareExportReverseOrder,
      compareExportSupportsV2,
      comparePathA,
      comparePathB,
      selectedPaths,
    ],
  )

  return {
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
  }
}
