import React from 'react'

interface SelectionExportSectionProps {
  selectedCount: number
  compareActive: boolean
  compareReady: boolean
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
  compareActive,
}: {
  selectedCount: number
  compareActive: boolean
}): string | null {
  if (selectedCount !== 2) {
    return `Comparison export (v1) supports exactly 2 selections (selected ${selectedCount}).`
  }
  if (!compareActive) {
    return 'Open side-by-side view to enable comparison export.'
  }
  return null
}

export function SelectionExportSection({
  selectedCount,
  compareActive,
  compareReady,
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
    compareActive,
  })
  const exportDisabled = !compareReady || compareExportBusy

  return (
    <div className="space-y-2 rounded-md border border-border/60 bg-surface-inset/40 p-3">
      <div className="text-[10px] uppercase tracking-wide text-muted">Selection Export</div>
      <textarea
        className="ui-textarea inspector-input w-full h-20 scrollbar-thin"
        placeholder={'Label for A\nLabel for B'}
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
