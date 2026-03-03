import type { JSX } from 'react'

interface SelectionActionsSectionProps {
  selectedCount: number
  viewerCompareActive: boolean
  metadataCompareActive: boolean
  metadataCompareAvailable: boolean
  onOpenCompare?: () => void
  onToggleMetadataCompare?: () => void
}

export function getSideBySideDisabledReason(selectedCount: number): string | null {
  if (selectedCount === 2) return null
  if (selectedCount > 2) {
    return `Side-by-side view supports exactly 2 selections (selected ${selectedCount}).`
  }
  return 'Select exactly 2 images to open side-by-side view.'
}

export function getMetadataCompareDisabledReason(
  selectedCount: number,
  metadataCompareAvailable: boolean,
): string | null {
  if (selectedCount >= 2 && metadataCompareAvailable) return null
  if (selectedCount >= 2) {
    return 'Select at least 2 images in the current view to compare metadata.'
  }
  return 'Select at least 2 images to compare metadata in the inspector.'
}

export function SelectionActionsSection({
  selectedCount,
  viewerCompareActive,
  metadataCompareActive,
  metadataCompareAvailable,
  onOpenCompare,
  onToggleMetadataCompare,
}: SelectionActionsSectionProps): JSX.Element {
  const sideBySideDisabledReason = getSideBySideDisabledReason(selectedCount)
  const metadataCompareDisabledReason = getMetadataCompareDisabledReason(
    selectedCount,
    metadataCompareAvailable,
  )
  const sideBySideDisabled = !onOpenCompare || viewerCompareActive || sideBySideDisabledReason !== null
  const metadataCompareDisabled = !onToggleMetadataCompare || metadataCompareDisabledReason !== null
  const sideBySideHelperText = viewerCompareActive
    ? 'Side-by-side viewer is already open.'
    : (sideBySideDisabledReason ?? 'Open side by side to compare selected images.')
  const metadataCompareHelperText = metadataCompareActive
    ? 'Inspector metadata compare is active.'
    : (metadataCompareDisabledReason ?? 'Open metadata compare in the inspector.')

  return (
    <div className="space-y-2 rounded-md border border-border/60 bg-surface-inset/40 p-3">
      <div className="text-[10px] uppercase tracking-wide text-muted">Selection Actions</div>
      <div className="flex flex-wrap items-center gap-2">
        <button
          type="button"
          className="btn btn-sm"
          onClick={onOpenCompare}
          disabled={sideBySideDisabled}
        >
          Side by side view
        </button>
        <button
          type="button"
          className="btn btn-sm"
          onClick={onToggleMetadataCompare}
          disabled={metadataCompareDisabled}
        >
          {metadataCompareActive ? 'Hide metadata compare' : 'Compare metadata'}
        </button>
      </div>
      <div className="text-[11px] text-muted">{sideBySideHelperText}</div>
      <div className="text-[11px] text-muted">
        {metadataCompareHelperText}
      </div>
    </div>
  )
}
