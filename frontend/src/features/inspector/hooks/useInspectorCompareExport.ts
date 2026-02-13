import { useCallback, useEffect, useState } from 'react'
import { downloadBlob } from '../../../app/utils/appShellHelpers'
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
} from '../exportComparison'

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
  compareExportMode: 'normal' | 'reverse' | null
  compareExportError: string | null
  compareExportBusy: boolean
  handleCompareExportLabelsTextChange: (value: string) => void
  handleCompareExportEmbedMetadataChange: (checked: boolean) => void
  runComparisonExport: (reverseOrder: boolean) => Promise<void>
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

  const runComparisonExport = useCallback(
    async (reverseOrder: boolean) => {
      if (compareExportBusy) return
      const selectedCount = selectedPaths.length

      if (selectedCount < 2) {
        setCompareExportError(EXPORT_COMPARISON_PAIR_ONLY_MESSAGE)
        return
      }

      const payloadResult = buildInspectorComparisonExportPayload({
        selectedPaths,
        comparePathA,
        comparePathB,
        compareExportSupportsV2,
        compareExportMaxPathsV2,
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
      compareExportMaxPathsV2,
      compareExportSupportsV2,
      comparePathA,
      comparePathB,
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
