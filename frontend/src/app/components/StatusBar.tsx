import type { PresenceEvent } from '../../lib/types'

export type RecentSummary = {
  count: number
  names: string[]
  extra: number
}

type StatusBarProps = {
  persistenceEnabled: boolean
  recentSummary: RecentSummary | null
  onDismissRecent: () => void
  syncTone: string
  syncLabel: string
  connectionTone: string
  connectionLabel: string
  presence?: PresenceEvent
  browserZoomPercent?: number | null
}

export default function StatusBar({
  persistenceEnabled,
  recentSummary,
  onDismissRecent,
  syncTone,
  syncLabel,
  connectionTone,
  connectionLabel,
  presence,
  browserZoomPercent,
}: StatusBarProps): JSX.Element {
  const recentLabel = recentSummary
    ? ` (${recentSummary.names.join(', ')}${recentSummary.extra ? ` +${recentSummary.extra}` : ''})`
    : ''
  const hasRecentNames = !!recentSummary?.names.length
  const zoomPercent = typeof browserZoomPercent === 'number' ? browserZoomPercent : null
  const showZoomWarning = zoomPercent !== null && Math.abs(zoomPercent - 100) >= 2
  return (
    <div className="border-b border-border bg-panel">
      <div className="px-3 py-2 flex flex-col gap-2">
        {!persistenceEnabled && (
          <div className="rounded-md border border-danger/40 bg-danger/10 text-danger text-xs px-2.5 py-1.5">
            <span className="font-semibold">Not persisted.</span> Workspace is read-only; edits stay in memory until restart.
          </div>
        )}
        {showZoomWarning && (
          <div className="rounded-md border border-accent/30 bg-accent/10 text-text text-xs px-2.5 py-1.5">
            <span className="font-semibold">Browser zoom {Math.round(zoomPercent)}%.</span> For best results, set it to 100% so UI elements stay in correct proportions.
          </div>
        )}
        {recentSummary && (
          <div className="rounded-md border border-accent/30 bg-accent/10 text-text text-xs px-2.5 py-1.5 flex items-center justify-between gap-3">
            <span>
              Recent updates: {recentSummary.count} item{recentSummary.count === 1 ? '' : 's'}
              {hasRecentNames ? recentLabel : ''}
            </span>
            <button
              className="text-muted hover:text-text transition-colors"
              onClick={onDismissRecent}
              aria-label="Dismiss recent activity"
            >
              Dismiss
            </button>
          </div>
        )}
        <div className="flex flex-wrap items-center gap-2 text-xs">
          <span className={`inline-flex items-center gap-1.5 px-2 py-1 rounded-full border ${syncTone}`}>
            {syncLabel}
          </span>
          <span className="inline-flex items-center gap-2 px-2 py-1 rounded-full border border-border text-muted">
            <span className={`inline-block w-2 h-2 rounded-full ${connectionTone}`} />
            {connectionLabel}
          </span>
          {presence ? (
            <span className="inline-flex items-center gap-1 px-2 py-1 rounded-full border border-border text-muted">
              {presence.viewing} viewing · {presence.editing} editing
            </span>
          ) : (
            <span className="inline-flex items-center gap-1 px-2 py-1 rounded-full border border-border text-muted">
              Presence: —
            </span>
          )}
        </div>
      </div>
    </div>
  )
}
