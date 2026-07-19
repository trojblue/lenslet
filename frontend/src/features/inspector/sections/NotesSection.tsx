import React from 'react'
import type { InspectorWidgetId } from '../model/inspectorWidgetOrder'
import { InspectorSection } from './InspectorSection'

interface NotesSectionProps {
  open: boolean
  onToggle: () => void
  multi: boolean
  showConflictBanner: boolean
  onApplyConflict: () => void
  onKeepTheirs: () => void
  notes: string
  onNotesChange: (value: string) => void
  onNotesBlur: () => void
  tags: string
  onTagsChange: (value: string) => void
  onTagsBlur: () => void
  disabled?: boolean
  statusMessage?: string | null
  sortableId?: InspectorWidgetId
  sortableEnabled?: boolean
}

export function NotesSection({
  open,
  onToggle,
  multi,
  showConflictBanner,
  onApplyConflict,
  onKeepTheirs,
  notes,
  onNotesChange,
  onNotesBlur,
  tags,
  onTagsChange,
  onTagsBlur,
  disabled = false,
  statusMessage = null,
  sortableId,
  sortableEnabled = false,
}: NotesSectionProps): JSX.Element {
  return (
    <InspectorSection
      title="Notes & Tags"
      open={open}
      onToggle={onToggle}
      sortableId={sortableId}
      sortableEnabled={sortableEnabled}
      contentClassName="px-3 pb-3 space-y-2"
    >
      <div className="space-y-2" data-inspector-terminal-error={statusMessage ? 'true' : 'false'}>
        <div className="h-20 min-w-0 overflow-hidden" data-inspector-conflict-slot="notes">
          {showConflictBanner ? (
            <div className="ui-banner ui-banner-danger h-full text-xs">
              <div className="font-semibold">Conflicting edits detected.</div>
              <div className="text-[11px] text-muted mt-0.5">Notes or tags changed elsewhere.</div>
              <div className="flex items-center gap-2 mt-1">
                <button className="btn btn-sm" onClick={onApplyConflict}>
                  Apply again
                </button>
                <button className="btn btn-sm btn-ghost" onClick={onKeepTheirs}>
                  Keep theirs
                </button>
              </div>
            </div>
          ) : (
            <div className="min-w-0 truncate text-[11px] text-danger" role="status" title={statusMessage ?? undefined}>
              {statusMessage ?? ''}
            </div>
          )}
        </div>
        <textarea
          className="ui-textarea inspector-input w-full scrollbar-thin"
          placeholder="Add notes"
          value={notes}
          onChange={(e) => onNotesChange(e.target.value)}
          onBlur={onNotesBlur}
          disabled={disabled}
          aria-label={multi ? 'Notes for selected items' : 'Notes'}
        />
        <div>
          <div className="ui-label">{multi ? 'Tags (apply to all, comma-separated)' : 'Tags (comma-separated)'}</div>
          <input
            className="ui-input inspector-input w-full"
            placeholder="tag1, tag2"
            value={tags}
            onChange={(e) => onTagsChange(e.target.value)}
            onBlur={onTagsBlur}
            disabled={disabled}
            aria-label={multi ? 'Tags for selected items' : 'Tags'}
          />
        </div>
      </div>
    </InspectorSection>
  )
}
