import React from 'react'

interface SelectionActionsSectionProps {
  selectedCount: number
  compareActive: boolean
  onOpenCompare?: () => void
}

export function getSideBySideDisabledReason(selectedCount: number): string | null {
  if (selectedCount === 2) return null
  if (selectedCount > 2) {
    return `Side-by-side view supports exactly 2 selections (selected ${selectedCount}).`
  }
  return 'Select exactly 2 images to open side-by-side view.'
}

export function SelectionActionsSection({
  selectedCount,
  compareActive,
  onOpenCompare,
}: SelectionActionsSectionProps): JSX.Element {
  const disabledReason = getSideBySideDisabledReason(selectedCount)
  const openDisabled = !onOpenCompare || compareActive || disabledReason !== null
  const helperText = compareActive
    ? 'Side-by-side viewer is already open.'
    : (disabledReason ?? 'Open side by side to compare selected images.')

  return (
    <div className="space-y-2 rounded-md border border-border/60 bg-surface-inset/40 p-3">
      <div className="text-[10px] uppercase tracking-wide text-muted">Selection Actions</div>
      <div className="flex flex-wrap items-center gap-2">
        <button
          type="button"
          className="btn btn-sm"
          onClick={() => onOpenCompare?.()}
          disabled={openDisabled}
        >
          Side by side view
        </button>
      </div>
      <div className="text-[11px] text-muted">{helperText}</div>
    </div>
  )
}
