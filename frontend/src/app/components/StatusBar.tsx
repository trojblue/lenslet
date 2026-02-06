import type { RecentSummary } from '../presenceActivity'

type StatusBarProps = {
  persistenceEnabled: boolean
  offViewSummary: RecentSummary | null
  onRevealOffView?: () => void
  canRevealOffView?: boolean
  onClearOffView: () => void
  browserZoomPercent?: number | null
}

export default function StatusBar({
  persistenceEnabled,
  offViewSummary,
  onRevealOffView,
  canRevealOffView = false,
  onClearOffView,
  browserZoomPercent,
}: StatusBarProps): JSX.Element {
  const hasOffViewNames = !!offViewSummary?.names.length
  const offViewLabel = hasOffViewNames && offViewSummary
    ? ` (${offViewSummary.names.join(', ')}${offViewSummary.extra ? ` +${offViewSummary.extra}` : ''})`
    : ''
  const canReveal = canRevealOffView && onRevealOffView != null
  const zoomPercent = typeof browserZoomPercent === 'number' ? browserZoomPercent : null
  const showZoomWarning = zoomPercent !== null && Math.abs(zoomPercent - 100) >= 2
  const showAnyBanner = !persistenceEnabled || showZoomWarning || !!offViewSummary
  if (!showAnyBanner) return null
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
        {offViewSummary && (
          <div className="ui-banner ui-banner-accent text-xs flex items-center justify-between gap-3">
            <span>
              Updates outside current view: {offViewSummary.count} item{offViewSummary.count === 1 ? '' : 's'}
              {offViewLabel}
            </span>
            <div className="flex items-center gap-2">
              {canReveal && (
                <button
                  className="text-muted hover:text-text transition-colors"
                  onClick={() => onRevealOffView?.()}
                  aria-label="Reveal off-view updates"
                >
                  Reveal
                </button>
              )}
              <button
                className="text-muted hover:text-text transition-colors text-base leading-none"
                onClick={onClearOffView}
                aria-label="Clear off-view updates"
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
