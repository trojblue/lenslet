import { useCallback, useEffect, useState } from 'react'
import { downloadBlob } from '../../../app/utils/appShellHelpers'
import type { ExportComparisonOutputFormat } from '../../../lib/types'
import { api } from '../../../api/client'
import {
  type ExportComparisonPayloadResult,
  DEFAULT_EXPORT_COMPARISON_EMBED_METADATA,
  EXPORT_COMPARISON_MIN_SELECTIONS_MESSAGE,
  buildComparisonExportFilename,
  buildExportComparisonPayload,
} from '../compareExportBoundary'
import {
  readInspectorStoredBool,
  writeInspectorStoredBool,
} from './inspectorStorage'

const INSPECTOR_EXPORT_REVERSE_ORDER_KEY = 'lenslet.inspector.export.reverseOrder'
const INSPECTOR_EXPORT_HIGH_QUALITY_GIF_KEY = 'lenslet.inspector.export.highQualityGif'

type UseInspectorCompareExportParams = {
  selectedPaths: string[]
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
  labelsText: string
  embedMetadata: boolean
  reverseOrder: boolean
  outputFormat: ExportComparisonOutputFormat
  highQualityGif: boolean
}

export function buildInspectorComparisonExportPayload({
  selectedPaths,
  labelsText,
  embedMetadata,
  reverseOrder,
  outputFormat,
  highQualityGif,
}: BuildInspectorComparisonExportPayloadArgs): ExportComparisonPayloadResult {
  return buildExportComparisonPayload({
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
    setCompareExportReverseOrder(readInspectorStoredBool(INSPECTOR_EXPORT_REVERSE_ORDER_KEY, false))
    setCompareExportHighQualityGif(readInspectorStoredBool(INSPECTOR_EXPORT_HIGH_QUALITY_GIF_KEY, false))
  }, [])

  useEffect(() => {
    writeInspectorStoredBool(INSPECTOR_EXPORT_REVERSE_ORDER_KEY, compareExportReverseOrder)
  }, [compareExportReverseOrder])

  useEffect(() => {
    writeInspectorStoredBool(INSPECTOR_EXPORT_HIGH_QUALITY_GIF_KEY, compareExportHighQualityGif)
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
  }, [selectedPaths])

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

      if (selectedPaths.length < 2) {
        setCompareExportError(EXPORT_COMPARISON_MIN_SELECTIONS_MESSAGE)
        return
      }

      const reverseOrder = compareExportReverseOrder
      const highQualityGif = outputFormat === 'gif' && compareExportHighQualityGif
      const payloadResult = buildInspectorComparisonExportPayload({
        selectedPaths,
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
      compareExportReverseOrder,
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
