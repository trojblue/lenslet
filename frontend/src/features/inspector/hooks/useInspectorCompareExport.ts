import { useCallback, useEffect, useState } from 'react'
import { downloadBlob } from '../../../app/utils/appShellHelpers'
import { api } from '../../../shared/api/client'
import {
  buildExportComparisonV2MaxPathsMessage,
  DEFAULT_EXPORT_COMPARISON_EMBED_METADATA,
  EXPORT_COMPARISON_PAIR_ONLY_MESSAGE,
  EXPORT_COMPARISON_V2_CAPABILITY_MESSAGE,
  buildComparisonExportFilename,
  buildExportComparisonPayload,
  buildExportComparisonPayloadV2,
} from '../exportComparison'

type UseInspectorCompareExportParams = {
  selectedPaths: string[]
  compareReady: boolean
  comparePathA: string | null
  comparePathB: string | null
  compareExportSupportsV2: boolean
  compareExportMaxPathsV2: number | null
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
  selectedPaths,
  compareReady,
  comparePathA,
  comparePathB,
  compareExportSupportsV2,
  compareExportMaxPathsV2,
}: UseInspectorCompareExportParams): UseInspectorCompareExportResult {
  const [compareExportLabelsText, setCompareExportLabelsText] = useState('')
  const [compareExportEmbedMetadata, setCompareExportEmbedMetadata] = useState(
    DEFAULT_EXPORT_COMPARISON_EMBED_METADATA,
  )
  const [compareExportMode, setCompareExportMode] = useState<'normal' | 'reverse' | null>(null)
  const [compareExportError, setCompareExportError] = useState<string | null>(null)
  const compareExportBusy = compareExportMode !== null

  useEffect(() => {
    if (selectedPaths.length < 2) {
      setCompareExportLabelsText('')
      setCompareExportEmbedMetadata(DEFAULT_EXPORT_COMPARISON_EMBED_METADATA)
      setCompareExportMode(null)
      setCompareExportError(null)
      return
    }
    if (selectedPaths.length === 2 && (!compareReady || !comparePathA || !comparePathB)) {
      setCompareExportLabelsText('')
      setCompareExportEmbedMetadata(DEFAULT_EXPORT_COMPARISON_EMBED_METADATA)
    }
    setCompareExportMode(null)
    setCompareExportError(null)
  }, [comparePathA, comparePathB, compareReady, selectedPaths.length])

  const handleCompareExportLabelsTextChange = useCallback((value: string) => {
    setCompareExportLabelsText(value)
    setCompareExportError(null)
  }, [])

  const handleCompareExportEmbedMetadataChange = useCallback((checked: boolean) => {
    setCompareExportEmbedMetadata(checked)
  }, [])

  const runComparisonExport = useCallback(
    async (reverseOrder: boolean) => {
      if (compareExportBusy) return
      const selectedCount = selectedPaths.length

      if (selectedCount < 2) {
        setCompareExportError(EXPORT_COMPARISON_PAIR_ONLY_MESSAGE)
        return
      }

      let payloadResult:
        | ReturnType<typeof buildExportComparisonPayload>
        | ReturnType<typeof buildExportComparisonPayloadV2>

      if (selectedCount === 2) {
        if (!compareReady || !comparePathA || !comparePathB) {
          setCompareExportError(EXPORT_COMPARISON_PAIR_ONLY_MESSAGE)
          return
        }
        payloadResult = buildExportComparisonPayload({
          pathA: comparePathA,
          pathB: comparePathB,
          labelsText: compareExportLabelsText,
          embedMetadata: compareExportEmbedMetadata,
          reverseOrder,
        })
      } else {
        if (!compareExportSupportsV2) {
          setCompareExportError(EXPORT_COMPARISON_V2_CAPABILITY_MESSAGE)
          return
        }
        if (compareExportMaxPathsV2 !== null && selectedCount > compareExportMaxPathsV2) {
          setCompareExportError(
            buildExportComparisonV2MaxPathsMessage(compareExportMaxPathsV2, selectedCount),
          )
          return
        }
        payloadResult = buildExportComparisonPayloadV2({
          paths: selectedPaths,
          labelsText: compareExportLabelsText,
          embedMetadata: compareExportEmbedMetadata,
          reverseOrder,
        })
      }
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
      compareExportMaxPathsV2,
      compareExportSupportsV2,
      comparePathA,
      comparePathB,
      compareReady,
      selectedPaths,
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
