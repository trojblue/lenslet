import type { RecentSummary } from '../presenceActivity'
import type { HealthResponse } from '../../lib/types'

type HealthIndexing = HealthResponse['indexing'] | null

type StatusBarProps = {
  persistenceEnabled: boolean
  indexing?: HealthIndexing
  offViewSummary: RecentSummary | null
  onRevealOffView?: () => void
  canRevealOffView?: boolean
  onClearOffView: () => void
  browserZoomPercent?: number | null
}

export default function StatusBar({
  persistenceEnabled,
  indexing = null,
  offViewSummary,
  onRevealOffView,
  canRevealOffView = false,
  onClearOffView,
  browserZoomPercent,
}: StatusBarProps): JSX.Element | null {
  const hasOffViewNames = !!offViewSummary?.names.length
  const offViewLabel = hasOffViewNames && offViewSummary
    ? ` (${offViewSummary.names.join(', ')}${offViewSummary.extra ? ` +${offViewSummary.extra}` : ''})`
    : ''
  const canReveal = canRevealOffView && onRevealOffView != null
  const zoomPercent = typeof browserZoomPercent === 'number' ? browserZoomPercent : null
  const showZoomWarning = zoomPercent !== null && Math.abs(zoomPercent - 100) >= 2
  const showIndexingRunning = indexing?.state === 'running'
  const showIndexingError = indexing?.state === 'error'
  const indexingScopeLabel = indexing?.scope && indexing.scope !== '/' ? ` (${indexing.scope})` : ''
  const indexingProgressLabel = (() => {
    if (!showIndexingRunning) return null
    const done = typeof indexing?.done === 'number' ? indexing.done : null
    const total = typeof indexing?.total === 'number' ? indexing.total : null
    if (done === null && total === null) return null
    if (total === null) return `${done ?? 0} indexed`
    return `${Math.min(done ?? 0, total)} / ${total}`
  })()
  const showAnyBanner =
    !persistenceEnabled || showIndexingRunning || showIndexingError || showZoomWarning || !!offViewSummary
  if (!showAnyBanner) return null
  return (
    <div className="border-b border-border bg-panel">
      <div className="px-3 py-2 flex flex-col gap-2">
        {!persistenceEnabled && (
          <div className="ui-banner ui-banner-danger text-xs">
            <span className="font-semibold">Not persisted.</span> Workspace is read-only; edits stay in memory until restart.
          </div>
        )}
        {showIndexingRunning && (
          <div className="ui-banner ui-banner-accent text-xs">
            <span className="font-semibold">Indexing in progress{indexingScopeLabel}.</span>
            {' '}
            {indexingProgressLabel
              ? `${indexingProgressLabel} complete.`
              : 'Preparing searchable index.'}
          </div>
        )}
        {showIndexingError && (
          <div className="ui-banner ui-banner-danger text-xs">
            <span className="font-semibold">Indexing failed.</span>
            {' '}
            {indexing?.error || 'Open server logs for details.'}
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
