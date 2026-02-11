import React from 'react'
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
}: NotesSectionProps): JSX.Element {
  return (
    <InspectorSection
      title="Notes & Tags"
      open={open}
      onToggle={onToggle}
      contentClassName="px-3 pb-3 space-y-2"
    >
      {showConflictBanner && (
        <div className="ui-banner ui-banner-danger text-xs">
          <div className="font-semibold">Conflicting edits detected.</div>
          <div className="text-[11px] text-muted mt-0.5">
            Your changes were not saved because this item was updated elsewhere.
          </div>
          <div className="flex items-center gap-2 mt-2">
            <button className="btn btn-sm" onClick={onApplyConflict}>
              Apply my changes again
            </button>
            <button className="btn btn-sm btn-ghost" onClick={onKeepTheirs}>
              Keep theirs
            </button>
          </div>
        </div>
      )}
      <textarea
        className="ui-textarea inspector-input w-full scrollbar-thin"
        placeholder="Add notes"
        value={notes}
        onChange={(e) => onNotesChange(e.target.value)}
        onBlur={onNotesBlur}
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
          aria-label={multi ? 'Tags for selected items' : 'Tags'}
        />
      </div>
    </InspectorSection>
  )
}
