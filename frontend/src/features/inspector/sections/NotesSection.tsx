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
            <div
              className="ui-banner ui-banner-danger h-full min-w-0 text-xs"
              title="Your text below is not saved. Save mine overwrites their notes; Use latest discards your text."
            >
              <div className="font-semibold truncate">Someone else changed these notes.</div>
              <div className="text-[11px] text-muted mt-0.5 truncate">Your text below is unsaved.</div>
              <div className="flex items-center gap-2 mt-1">
                <button className="btn btn-sm" title="Overwrite their notes with your text" onClick={onApplyConflict}>
                  Save mine
                </button>
                <button className="btn btn-sm btn-ghost" onClick={onKeepTheirs}>
                  Use latest
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
          placeholder={multi ? "Add a note to each selected item" : "Add notes"}
          value={notes}
          onChange={(e) => onNotesChange(e.target.value)}
          onBlur={onNotesBlur}
          disabled={disabled}
          aria-label={multi ? 'Note to add to each selected item' : 'Notes'}
        />
        <div>
          <div className="ui-label">{multi ? 'Tags to add to each item (comma-separated)' : 'Tags (comma-separated)'}</div>
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
