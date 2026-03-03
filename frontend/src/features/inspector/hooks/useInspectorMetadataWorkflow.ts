import type { Dispatch, SetStateAction } from 'react'
import type { ExportComparisonOutputFormat } from '../../../lib/types'
import { useInspectorCompareExport } from './useInspectorCompareExport'
import { useInspectorCompareMetadata } from './useInspectorCompareMetadata'
import { useInspectorSingleMetadata } from './useInspectorSingleMetadata'
import type { MetadataRecord, MetadataState } from './useInspectorMetadataTypes'

type UseInspectorMetadataWorkflowParams = {
  path: string | null
  sidecarUpdatedAt: string | undefined
  selectedPaths: string[]
  compareReady: boolean
  comparePaths: string[]
  autoloadMetadata: boolean
}

type UseInspectorMetadataWorkflowResult = {
  metaRaw: MetadataRecord
  metaError: string | null
  metaState: MetadataState
  showPilInfo: boolean
  setMetaError: Dispatch<SetStateAction<string | null>>
  compareMetaState: MetadataState
  compareMetaError: string | null
  compareMetaByPath: Record<string, MetadataRecord>
  compareIncludePilInfo: boolean
  compareExportLabelsText: string
  compareExportEmbedMetadata: boolean
  compareExportReverseOrder: boolean
  compareExportHighQualityGif: boolean
  compareExportMode: 'png' | 'gif' | null
  compareExportError: string | null
  compareExportBusy: boolean
  setShowPilInfo: Dispatch<SetStateAction<boolean>>
  setCompareIncludePilInfo: Dispatch<SetStateAction<boolean>>
  fetchMetadata: () => Promise<void>
  reloadCompareMetadata: () => void
  handleCompareExportLabelsTextChange: (value: string) => void
  handleCompareExportEmbedMetadataChange: (checked: boolean) => void
  handleCompareExportReverseOrderChange: (checked: boolean) => void
  handleCompareExportHighQualityGifChange: (checked: boolean) => void
  runComparisonExport: (outputFormat: ExportComparisonOutputFormat) => Promise<void>
}

export function useInspectorMetadataWorkflow({
  path,
  sidecarUpdatedAt,
  selectedPaths,
  compareReady,
  comparePaths,
  autoloadMetadata,
}: UseInspectorMetadataWorkflowParams): UseInspectorMetadataWorkflowResult {
  const singleMetadata = useInspectorSingleMetadata({
    path,
    sidecarUpdatedAt,
    autoloadMetadata,
  })

  const compareMetadata = useInspectorCompareMetadata({
    compareReady,
    comparePaths,
  })

  const compareExport = useInspectorCompareExport({
    selectedPaths,
  })

  return {
    metaRaw: singleMetadata.metaRaw,
    metaError: singleMetadata.metaError,
    metaState: singleMetadata.metaState,
    showPilInfo: singleMetadata.showPilInfo,
    setMetaError: singleMetadata.setMetaError,
    compareMetaState: compareMetadata.compareMetaState,
    compareMetaError: compareMetadata.compareMetaError,
    compareMetaByPath: compareMetadata.compareMetaByPath,
    compareIncludePilInfo: compareMetadata.compareIncludePilInfo,
    compareExportLabelsText: compareExport.compareExportLabelsText,
    compareExportEmbedMetadata: compareExport.compareExportEmbedMetadata,
    compareExportReverseOrder: compareExport.compareExportReverseOrder,
    compareExportHighQualityGif: compareExport.compareExportHighQualityGif,
    compareExportMode: compareExport.compareExportMode,
    compareExportError: compareExport.compareExportError,
    compareExportBusy: compareExport.compareExportBusy,
    setShowPilInfo: singleMetadata.setShowPilInfo,
    setCompareIncludePilInfo: compareMetadata.setCompareIncludePilInfo,
    fetchMetadata: singleMetadata.fetchMetadata,
    reloadCompareMetadata: compareMetadata.reloadCompareMetadata,
    handleCompareExportLabelsTextChange: compareExport.handleCompareExportLabelsTextChange,
    handleCompareExportEmbedMetadataChange: compareExport.handleCompareExportEmbedMetadataChange,
    handleCompareExportReverseOrderChange: compareExport.handleCompareExportReverseOrderChange,
    handleCompareExportHighQualityGifChange: compareExport.handleCompareExportHighQualityGifChange,
    runComparisonExport: compareExport.runComparisonExport,
  }
}
