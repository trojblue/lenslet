import React from 'react'
import { fmtBytes } from '../../../lib/util'
import { InspectorSection } from './InspectorSection'

interface OverviewSectionProps {
  open: boolean
  onToggle: () => void
  multi: boolean
  selectedCount: number
  totalSize: number
  filename: string
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
