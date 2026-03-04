import React from 'react'
import type { InspectorWidgetId } from '../model/inspectorWidgetOrder'
import type { QuickViewRow } from '../model/quickViewFields'
import { InspectorSection } from './InspectorSection'

interface QuickViewSectionProps {
  open: boolean
  onToggle: () => void
  rows: QuickViewRow[]
  reservationActive: boolean
  reservationRowCount: number
  metadataLoading: boolean
  quickViewCopiedRowId: string | null
  onCopyQuickViewValue: (rowId: string, value: string) => void
  quickViewCustomPathsDraft: string
  onQuickViewCustomPathsDraftChange: (value: string) => void
  onSaveQuickViewCustomPaths: () => void
  quickViewCustomPathsError: string | null
  sortableId?: InspectorWidgetId
  sortableEnabled?: boolean
}

function QuickViewSectionComponent({
  open,
  onToggle,
  rows,
  reservationActive,
  reservationRowCount,
  metadataLoading,
  quickViewCopiedRowId,
  onCopyQuickViewValue,
  quickViewCustomPathsDraft,
  onQuickViewCustomPathsDraftChange,
  onSaveQuickViewCustomPaths,
  quickViewCustomPathsError,
  sortableId,
  sortableEnabled = false,
}: QuickViewSectionProps): JSX.Element {
  const [customPathsOpen, setCustomPathsOpen] = React.useState(() => Boolean(quickViewCustomPathsError))
  const placeholderRows = React.useMemo(
    () => Array.from({ length: Math.max(1, reservationRowCount) }, (_, idx) => `quick-view-placeholder-${idx}`),
    [reservationRowCount],
  )

  React.useEffect(() => {
    if (quickViewCustomPathsError) {
      setCustomPathsOpen(true)
    }
  }, [quickViewCustomPathsError])

  return (
    <InspectorSection
      title="Quick View"
      open={open}
      onToggle={onToggle}
      sortableId={sortableId}
      sortableEnabled={sortableEnabled}
      contentClassName="px-3 pb-3 space-y-2"
    >
      <div className="text-[11px] text-muted">
        {reservationActive && metadataLoading ? 'Loading metadata…' : 'Auto-loaded PNG metadata fields.'}
      </div>
      <div className="space-y-1.5 text-[12px]">
        {reservationActive && rows.length === 0
          ? placeholderRows.map((placeholderId) => (
            <div key={placeholderId} className="ui-kv-row min-h-[39px] items-start gap-2" aria-hidden>
              <span className="ui-kv-label w-20 shrink-0">
                <span className="block h-3 w-12 rounded bg-surface-inset/80" />
              </span>
              <span className="ui-kv-value flex-1">
                <span className="block h-4 rounded bg-surface-inset/80" />
              </span>
              <span className="inline-flex h-7 w-7 shrink-0 rounded border border-border/60 bg-surface-inset/80" />
            </div>
          ))
          : rows.map((row) => (
            <div key={row.id} className="ui-kv-row items-start gap-2">
              <span className="ui-kv-label w-20 shrink-0 break-words" title={row.sourcePath}>
                {row.label}
              </span>
              <span className="ui-kv-value inspector-scroll-value flex-1 text-left">
                {row.value || '—'}
              </span>
              <button
                type="button"
                className="btn btn-sm inline-flex h-7 w-7 items-center justify-center p-0"
                onClick={() => onCopyQuickViewValue(row.id, row.value)}
                disabled={!row.value}
                aria-label={`Copy ${row.label}`}
                title={quickViewCopiedRowId === row.id ? `${row.label} copied` : `Copy ${row.label}`}
              >
                {quickViewCopiedRowId === row.id ? (
                  <svg
                    width="12"
                    height="12"
                    viewBox="0 0 24 24"
                    fill="none"
                    stroke="currentColor"
                    strokeWidth="2"
                    strokeLinecap="round"
                    strokeLinejoin="round"
                    aria-hidden="true"
                  >
                    <path d="M20 6 9 17l-5-5" />
                  </svg>
                ) : (
                  <svg
                    width="12"
                    height="12"
                    viewBox="0 0 24 24"
                    fill="none"
                    stroke="currentColor"
                    strokeWidth="2"
                    strokeLinecap="round"
                    strokeLinejoin="round"
                    aria-hidden="true"
                  >
                    <rect x="9" y="9" width="13" height="13" rx="2" ry="2" />
                    <path d="M5 15H4a2 2 0 0 1-2-2V4a2 2 0 0 1 2-2h9a2 2 0 0 1 2 2v1" />
                  </svg>
                )}
              </button>
            </div>
          ))}
      </div>

      <div className="rounded-md border border-border/60 bg-surface-inset/40">
        <button
          type="button"
          className="flex w-full items-center justify-between gap-2 px-2 py-1.5 text-left text-[10px] uppercase tracking-wide text-muted hover:text-text"
          onClick={() => setCustomPathsOpen((prev) => !prev)}
          aria-expanded={customPathsOpen}
          aria-label="Toggle custom JSON paths"
        >
          <span>Custom JSON paths</span>
          <span aria-hidden>{customPathsOpen ? '▾' : '▸'}</span>
        </button>
        {customPathsOpen && (
          <div className="space-y-1.5 border-t border-border/60 p-2">
            <textarea
              className="ui-textarea inspector-input w-full h-20 scrollbar-thin"
              value={quickViewCustomPathsDraft}
              onChange={(event) => onQuickViewCustomPathsDraftChange(event.target.value)}
              placeholder="quick_fields.parameters\nfound_text_chunks[0].keyword"
              aria-label="Quick View custom JSON paths"
            />
            <div className="flex items-center justify-between gap-2">
              <div className="text-[11px] text-muted">Supported syntax: dot paths and [index].</div>
              <button
                type="button"
                className="btn btn-sm"
                onClick={onSaveQuickViewCustomPaths}
              >
                Save fields
              </button>
            </div>
            {quickViewCustomPathsError && (
              <div className="text-[11px] text-danger break-words">{quickViewCustomPathsError}</div>
            )}
          </div>
        )}
      </div>
    </InspectorSection>
  )
}

export const QuickViewSection = React.memo(QuickViewSectionComponent)

QuickViewSection.displayName = 'QuickViewSection'
