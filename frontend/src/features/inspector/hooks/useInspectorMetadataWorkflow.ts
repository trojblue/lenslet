import type { Dispatch, SetStateAction } from 'react'
import { useInspectorCompareExport } from './useInspectorCompareExport'
import { useInspectorCompareMetadata } from './useInspectorCompareMetadata'
import { useInspectorSingleMetadata } from './useInspectorSingleMetadata'
import type { MetadataRecord, MetadataState } from './useInspectorMetadataTypes'

type UseInspectorMetadataWorkflowParams = {
  path: string | null
  sidecarUpdatedAt: string | undefined
  selectedPaths: string[]
  compareReady: boolean
  comparePathA: string | null
  comparePathB: string | null
  compareExportSupportsV2: boolean
  compareExportMaxPathsV2: number | null
}

type UseInspectorMetadataWorkflowResult = {
  metaRaw: MetadataRecord
  metaError: string | null
  metaState: MetadataState
  showPilInfo: boolean
  setMetaError: Dispatch<SetStateAction<string | null>>
  compareMetaState: MetadataState
  compareMetaError: string | null
  compareMetaA: MetadataRecord
  compareMetaB: MetadataRecord
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
  selectedPaths,
  compareReady,
  comparePathA,
  comparePathB,
  compareExportSupportsV2,
  compareExportMaxPathsV2,
}: UseInspectorMetadataWorkflowParams): UseInspectorMetadataWorkflowResult {
  const singleMetadata = useInspectorSingleMetadata({
    path,
    sidecarUpdatedAt,
  })

  const compareMetadata = useInspectorCompareMetadata({
    compareReady,
    comparePathA,
    comparePathB,
  })

  const compareExport = useInspectorCompareExport({
    selectedPaths,
    compareReady,
    comparePathA,
    comparePathB,
    compareExportSupportsV2,
    compareExportMaxPathsV2,
  })

  return {
    metaRaw: singleMetadata.metaRaw,
    metaError: singleMetadata.metaError,
    metaState: singleMetadata.metaState,
    showPilInfo: singleMetadata.showPilInfo,
    setMetaError: singleMetadata.setMetaError,
    compareMetaState: compareMetadata.compareMetaState,
    compareMetaError: compareMetadata.compareMetaError,
    compareMetaA: compareMetadata.compareMetaA,
    compareMetaB: compareMetadata.compareMetaB,
    compareIncludePilInfo: compareMetadata.compareIncludePilInfo,
    compareShowPilInfoA: compareMetadata.compareShowPilInfoA,
    compareShowPilInfoB: compareMetadata.compareShowPilInfoB,
    compareExportLabelsText: compareExport.compareExportLabelsText,
    compareExportEmbedMetadata: compareExport.compareExportEmbedMetadata,
    compareExportMode: compareExport.compareExportMode,
    compareExportError: compareExport.compareExportError,
    compareExportBusy: compareExport.compareExportBusy,
    setShowPilInfo: singleMetadata.setShowPilInfo,
    setCompareIncludePilInfo: compareMetadata.setCompareIncludePilInfo,
    setCompareShowPilInfoA: compareMetadata.setCompareShowPilInfoA,
    setCompareShowPilInfoB: compareMetadata.setCompareShowPilInfoB,
    fetchMetadata: singleMetadata.fetchMetadata,
    reloadCompareMetadata: compareMetadata.reloadCompareMetadata,
    handleCompareExportLabelsTextChange: compareExport.handleCompareExportLabelsTextChange,
    handleCompareExportEmbedMetadataChange: compareExport.handleCompareExportEmbedMetadataChange,
    runComparisonExport: compareExport.runComparisonExport,
  }
}
