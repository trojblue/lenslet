import React from 'react'
import { fmtBytes } from '../../../lib/util'
import { InspectorSection } from './InspectorSection'
import { SelectionActionsSection } from './SelectionActionsSection'
import { SelectionExportSection } from './SelectionExportSection'

interface OverviewSectionProps {
  open: boolean
  onToggle: () => void
  multi: boolean
  selectedCount: number
  totalSize: number
  filename: string
  compareActive: boolean
  compareReady: boolean
  onOpenCompare?: () => void
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
  onFindSimilar?: () => void
  canFindSimilar: boolean
  findSimilarDisabledReason: string | null
}

export function OverviewSection({
  open,
  onToggle,
  multi,
  selectedCount,
  totalSize,
  filename,
  compareActive,
  compareReady,
  onOpenCompare,
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
  onFindSimilar,
  canFindSimilar,
  findSimilarDisabledReason,
}: OverviewSectionProps): JSX.Element {
  return (
    <InspectorSection
      title={multi ? 'Selection' : 'Item'}
      open={open}
      onToggle={onToggle}
      contentClassName="px-3 pb-3 space-y-2"
      actions={onFindSimilar && (
        <button
          type="button"
          className="btn btn-sm"
          onClick={onFindSimilar}
          disabled={!canFindSimilar}
          title={findSimilarDisabledReason ?? 'Find similar'}
        >
          Find similar
        </button>
      )}
    >
      {multi ? (
        <div className="space-y-2">
          <div className="grid grid-cols-2 gap-2">
            <div className="inspector-field">
              <div className="inspector-field-label">Selected</div>
              <div className="inspector-field-value">{selectedCount} files</div>
            </div>
            <div className="inspector-field">
              <div className="inspector-field-label">Total size</div>
              <div className="inspector-field-value">{fmtBytes(totalSize)}</div>
            </div>
          </div>
          <SelectionActionsSection
            selectedCount={selectedCount}
            compareActive={compareActive}
            onOpenCompare={onOpenCompare}
          />
          {!compareActive && (
            <SelectionExportSection
              selectedCount={selectedCount}
              compareReady={compareReady}
              compareExportSupportsV2={compareExportSupportsV2}
              compareExportMaxPathsV2={compareExportMaxPathsV2}
              compareExportLabelsText={compareExportLabelsText}
              onCompareExportLabelsTextChange={onCompareExportLabelsTextChange}
              compareExportEmbedMetadata={compareExportEmbedMetadata}
              onCompareExportEmbedMetadataChange={onCompareExportEmbedMetadataChange}
              compareExportBusy={compareExportBusy}
              compareExportMode={compareExportMode}
              onComparisonExport={onComparisonExport}
              compareExportError={compareExportError}
            />
          )}
        </div>
      ) : (
        <div className="inspector-field">
          <div className="inspector-field-label">Filename</div>
          <div className="inspector-field-value break-all" title={filename}>
            {filename}
          </div>
        </div>
      )}
      {findSimilarDisabledReason && (
        <div className="text-[11px] text-muted">{findSimilarDisabledReason}</div>
      )}
    </InspectorSection>
  )
}
