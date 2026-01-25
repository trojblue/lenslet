export type RecentSummary = {
  count: number
  names: string[]
  extra: number
}

type StatusBarProps = {
  persistenceEnabled: boolean
  recentSummary: RecentSummary | null
  onDismissRecent: () => void
  onCloseRecent: () => void
  browserZoomPercent?: number | null
}

export default function StatusBar({
  persistenceEnabled,
  recentSummary,
  onDismissRecent,
  onCloseRecent,
  browserZoomPercent,
}: StatusBarProps): JSX.Element {
  const recentLabel = recentSummary
    ? ` (${recentSummary.names.join(', ')}${recentSummary.extra ? ` +${recentSummary.extra}` : ''})`
    : ''
  const hasRecentNames = !!recentSummary?.names.length
  const zoomPercent = typeof browserZoomPercent === 'number' ? browserZoomPercent : null
  const showZoomWarning = zoomPercent !== null && Math.abs(zoomPercent - 100) >= 2
  const showBanner = !persistenceEnabled || showZoomWarning || !!recentSummary
  if (!showBanner) return <></>
  return (
    <div className="border-b border-border bg-panel">
      <div className="px-3 py-2 flex flex-col gap-2">
        {!persistenceEnabled && (
          <div className="ui-banner ui-banner-danger text-xs">
            <span className="font-semibold">Not persisted.</span> Workspace is read-only; edits stay in memory until restart.
          </div>
        )}
        {showZoomWarning && (
          <div className="ui-banner ui-banner-accent text-xs">
            <span className="font-semibold">Browser zoom {Math.round(zoomPercent)}%.</span> For best results, set it to 100% so UI elements stay in correct proportions.
          </div>
        )}
        {recentSummary && (
          <div className="ui-banner ui-banner-accent text-xs flex items-center justify-between gap-3">
            <span>
              Recent updates: {recentSummary.count} item{recentSummary.count === 1 ? '' : 's'}
              {hasRecentNames ? recentLabel : ''}
            </span>
            <div className="flex items-center gap-2">
              <button
                className="text-muted hover:text-text transition-colors"
                onClick={onDismissRecent}
                aria-label="Hide recent activity until refresh"
              >
                Hide until refresh
              </button>
              <button
                className="text-muted hover:text-text transition-colors text-base leading-none"
                onClick={onCloseRecent}
                aria-label="Close recent activity"
              >
                ×
              </button>
            </div>
          </div>
        )}
      </div>
    </div>
  )
}
