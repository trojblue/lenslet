import React from 'react'
import {
  buildExportComparisonV2MaxPathsMessage,
  EXPORT_COMPARISON_PAIR_ONLY_MESSAGE,
  EXPORT_COMPARISON_V2_CAPABILITY_MESSAGE,
} from '../compareExportBoundary'

interface SelectionExportSectionProps {
  selectedCount: number
  compareReady: boolean
  compareExportSupportsV2: boolean
  compareExportMaxPathsV2: number | null
  compareExportLabelsText: string
  onCompareExportLabelsTextChange: (value: string) => void
  compareExportEmbedMetadata: boolean
  onCompareExportEmbedMetadataChange: (checked: boolean) => void
  compareExportBusy: boolean
  compareExportMode: 'normal' | 'reverse' | null
  onComparisonExport: (reverseOrder: boolean) => void
  compareExportError: string | null
}

export function getSelectionExportDisabledReason({
  selectedCount,
  compareReady,
  compareExportSupportsV2,
  compareExportMaxPathsV2,
}: {
  selectedCount: number
  compareReady: boolean
  compareExportSupportsV2: boolean
  compareExportMaxPathsV2: number | null
}): string | null {
  if (selectedCount < 2) {
    return `Comparison export requires at least 2 selections (selected ${selectedCount}).`
  }
  if (selectedCount === 2) {
    if (!compareReady) return EXPORT_COMPARISON_PAIR_ONLY_MESSAGE
    return null
  }
  if (!compareExportSupportsV2 || compareExportMaxPathsV2 === null) {
    return EXPORT_COMPARISON_V2_CAPABILITY_MESSAGE
  }
  if (selectedCount > compareExportMaxPathsV2) {
    return buildExportComparisonV2MaxPathsMessage(compareExportMaxPathsV2, selectedCount)
  }
  return null
}

export function SelectionExportSection({
  selectedCount,
  compareReady,
  compareExportSupportsV2,
  compareExportMaxPathsV2,
  compareExportLabelsText,
  onCompareExportLabelsTextChange,
  compareExportEmbedMetadata,
  onCompareExportEmbedMetadataChange,
  compareExportBusy,
  compareExportMode,
  onComparisonExport,
  compareExportError,
}: SelectionExportSectionProps): JSX.Element {
  const disabledReason = getSelectionExportDisabledReason({
    selectedCount,
    compareReady,
    compareExportSupportsV2,
    compareExportMaxPathsV2,
  })
  const exportDisabled = compareExportBusy || disabledReason !== null
  const labelsPlaceholder = selectedCount > 2
    ? 'Label for image 1\nLabel for image 2\n...'
    : 'Label for A\nLabel for B'

  return (
    <div className="space-y-2 rounded-md border border-border/60 bg-surface-inset/40 p-3">
      <div className="text-[10px] uppercase tracking-wide text-muted">Selection Export</div>
      <textarea
        className="ui-textarea inspector-input w-full h-20 scrollbar-thin"
        placeholder={labelsPlaceholder}
        value={compareExportLabelsText}
        onChange={(e) => onCompareExportLabelsTextChange(e.target.value)}
        disabled={exportDisabled}
        aria-label="Selection export labels"
      />
      <label className="inline-flex items-center gap-2 text-[11px] text-muted">
        <input
          type="checkbox"
          checked={compareExportEmbedMetadata}
          onChange={(e) => onCompareExportEmbedMetadataChange(e.target.checked)}
          disabled={exportDisabled}
        />
        <span>Embed metadata</span>
      </label>
      <div className="flex flex-wrap items-center gap-2">
        <button
          type="button"
          className="btn btn-sm"
          onClick={() => onComparisonExport(false)}
          disabled={exportDisabled}
        >
          {compareExportMode === 'normal' ? 'Exporting…' : 'Export comparison'}
        </button>
        <button
          type="button"
          className="btn btn-sm btn-ghost"
          onClick={() => onComparisonExport(true)}
          disabled={exportDisabled}
        >
          {compareExportMode === 'reverse' ? 'Exporting…' : 'Export (reverse order)'}
        </button>
      </div>
      {disabledReason && (
        <div className="text-[11px] text-muted">{disabledReason}</div>
      )}
      {compareExportError && (
        <div className="text-danger break-words">{compareExportError}</div>
      )}
    </div>
  )
}
