import { useCallback, useEffect, useState } from 'react'
import { downloadBlob } from '../../../app/utils/appShellHelpers'
import { api } from '../../../shared/api/client'
import {
  DEFAULT_EXPORT_COMPARISON_EMBED_METADATA,
  EXPORT_COMPARISON_PAIR_ONLY_MESSAGE,
  buildComparisonExportFilename,
  buildExportComparisonPayload,
} from '../exportComparison'

type UseInspectorCompareExportParams = {
  compareReady: boolean
  comparePathA: string | null
  comparePathB: string | null
}

type UseInspectorCompareExportResult = {
  compareExportLabelsText: string
  compareExportEmbedMetadata: boolean
  compareExportMode: 'normal' | 'reverse' | null
  compareExportError: string | null
  compareExportBusy: boolean
  handleCompareExportLabelsTextChange: (value: string) => void
  handleCompareExportEmbedMetadataChange: (checked: boolean) => void
  runComparisonExport: (reverseOrder: boolean) => Promise<void>
}

export function useInspectorCompareExport({
  compareReady,
  comparePathA,
  comparePathB,
}: UseInspectorCompareExportParams): UseInspectorCompareExportResult {
  const [compareExportLabelsText, setCompareExportLabelsText] = useState('')
  const [compareExportEmbedMetadata, setCompareExportEmbedMetadata] = useState(
    DEFAULT_EXPORT_COMPARISON_EMBED_METADATA,
  )
  const [compareExportMode, setCompareExportMode] = useState<'normal' | 'reverse' | null>(null)
  const [compareExportError, setCompareExportError] = useState<string | null>(null)
  const compareExportBusy = compareExportMode !== null

  useEffect(() => {
    if (!compareReady || !comparePathA || !comparePathB) {
      setCompareExportLabelsText('')
      setCompareExportEmbedMetadata(DEFAULT_EXPORT_COMPARISON_EMBED_METADATA)
      setCompareExportMode(null)
      setCompareExportError(null)
      return
    }
    setCompareExportMode(null)
    setCompareExportError(null)
  }, [compareReady, comparePathA, comparePathB])

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
        setCompareExportError(EXPORT_COMPARISON_PAIR_ONLY_MESSAGE)
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
    compareExportLabelsText,
    compareExportEmbedMetadata,
    compareExportMode,
    compareExportError,
    compareExportBusy,
    handleCompareExportLabelsTextChange,
    handleCompareExportEmbedMetadataChange,
    runComparisonExport,
  }
}
