import type { RecentSummary } from '../presenceActivity'
import type { HealthResponse } from '../../lib/types'

type HealthIndexing = HealthResponse['indexing'] | null

export type StatusBarProps = {
  persistenceEnabled: boolean
  showPersistenceWarning?: boolean
  onDismissPersistenceWarning?: () => void
  indexing?: HealthIndexing
  showSwitchToMostRecentBanner?: boolean
  onSwitchToMostRecent?: () => void
  offViewSummary: RecentSummary | null
  onRevealOffView?: () => void
  canRevealOffView?: boolean
  onClearOffView: () => void
  browserZoomPercent?: number | null
  onDismissBrowserZoomWarning?: () => void
  tableSourceWarning?: string | null
  derivedMetricWarning?: string | null
  onDismissTableSourceWarning?: () => void
}

type StatusBarStateInput = Omit<
  StatusBarProps,
  'onClearOffView' | 'onDismissBrowserZoomWarning' | 'onDismissTableSourceWarning'
  | 'onDismissPersistenceWarning'
>

type StatusBarState = {
  offViewLabel: string
  canReveal: boolean
  zoomPercent: number | null
  showZoomWarning: boolean
  showTableSourceWarning: boolean
  showIndexingRunning: boolean
  showIndexingError: boolean
  indexingScopeLabel: string
  indexingProgressLabel: string | null
  showSwitchBanner: boolean
  showReadOnlyWarning: boolean
  showAnyBanner: boolean
}

function deriveStatusBarState({
  persistenceEnabled,
  showPersistenceWarning,
  indexing = null,
  showSwitchToMostRecentBanner = false,
  onSwitchToMostRecent,
  offViewSummary,
  onRevealOffView,
  canRevealOffView = false,
  browserZoomPercent,
  tableSourceWarning,
  derivedMetricWarning,
}: StatusBarStateInput): StatusBarState {
  const offViewLabel = offViewSummary?.names.length
    ? ` (${offViewSummary.names.join(', ')}${offViewSummary.extra ? ` +${offViewSummary.extra}` : ''})`
    : ''
  const canReveal = canRevealOffView && onRevealOffView != null
  const zoomPercent = typeof browserZoomPercent === 'number' ? browserZoomPercent : null
  const showZoomWarning = zoomPercent !== null && Math.abs(zoomPercent - 100) >= 2
  const showTableSourceWarning = !!tableSourceWarning
  const showDerivedMetricWarning = !!derivedMetricWarning
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
  const showSwitchBanner = showSwitchToMostRecentBanner && onSwitchToMostRecent != null
  const showReadOnlyWarning = !persistenceEnabled && showPersistenceWarning !== false
  const showAnyBanner = (
    showReadOnlyWarning
    || showIndexingRunning
    || showIndexingError
    || showSwitchBanner
    || showZoomWarning
    || !!offViewSummary
    || showTableSourceWarning
    || showDerivedMetricWarning
  )
  return {
    offViewLabel,
    canReveal,
    zoomPercent,
    showZoomWarning,
    showTableSourceWarning,
    showIndexingRunning,
    showIndexingError,
    indexingScopeLabel,
    indexingProgressLabel,
    showSwitchBanner,
    showAnyBanner,
    showReadOnlyWarning,
  }
}

export function hasStatusBarContent(props: StatusBarProps): boolean {
  return deriveStatusBarState(props).showAnyBanner
}

export default function StatusBar({
  persistenceEnabled,
  showPersistenceWarning,
  onDismissPersistenceWarning,
  indexing = null,
  showSwitchToMostRecentBanner = false,
  onSwitchToMostRecent,
  offViewSummary,
  onRevealOffView,
  canRevealOffView = false,
  onClearOffView,
  browserZoomPercent,
  onDismissBrowserZoomWarning,
  tableSourceWarning,
  derivedMetricWarning,
  onDismissTableSourceWarning,
}: StatusBarProps): JSX.Element | null {
  const {
    offViewLabel,
    canReveal,
    zoomPercent,
    showZoomWarning,
    showTableSourceWarning,
    showIndexingRunning,
    showIndexingError,
    indexingScopeLabel,
    indexingProgressLabel,
    showSwitchBanner,
    showAnyBanner,
    showReadOnlyWarning,
  } = deriveStatusBarState({
    persistenceEnabled,
    showPersistenceWarning,
    indexing,
    showSwitchToMostRecentBanner,
    onSwitchToMostRecent,
    offViewSummary,
    onRevealOffView,
    canRevealOffView,
    browserZoomPercent,
    tableSourceWarning,
    derivedMetricWarning,
  })
  if (!showAnyBanner) return null
  return (
    <div className="border-b border-border bg-panel">
      <div className="px-3 py-2 flex flex-col gap-2">
        {showReadOnlyWarning && (
          <div className="ui-banner ui-banner-danger text-xs flex items-center justify-between gap-3">
            <span>
              <span className="font-semibold">Not persisted.</span> Workspace is read-only; edits stay in memory until restart.
            </span>
            {onDismissPersistenceWarning && (
              <button
                type="button"
                className="text-muted hover:text-text transition-colors text-base leading-none shrink-0"
                onClick={onDismissPersistenceWarning}
                aria-label="Dismiss persistence warning"
              >
                ×
              </button>
            )}
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
        {showTableSourceWarning && (
          <div className="ui-banner ui-banner-accent text-xs flex items-center justify-between gap-3">
            <span>
              <span className="font-semibold">Image source warning.</span>
              {' '}
              {tableSourceWarning}
            </span>
            {onDismissTableSourceWarning && (
              <button
                type="button"
                className="text-muted hover:text-text transition-colors text-base leading-none shrink-0"
                onClick={onDismissTableSourceWarning}
                aria-label="Dismiss image source warning"
              >
                ×
              </button>
            )}
          </div>
        )}
        {derivedMetricWarning && (
          <div className="ui-banner ui-banner-danger text-xs">
            <span className="font-semibold">Derived score.</span>
            {' '}
            {derivedMetricWarning}
          </div>
        )}
        {showSwitchBanner && (
          <div className="ui-banner ui-banner-accent text-xs flex flex-wrap items-center justify-between gap-3">
            <span>
              <span className="font-semibold">Indexing complete.</span>
              {' '}
              Scan-stable ordering is active for this generation.
            </span>
            <button
              className="text-muted hover:text-text transition-colors"
              onClick={onSwitchToMostRecent}
            >
              Switch to Most recent
            </button>
          </div>
        )}
        {showZoomWarning && (
          <div className="ui-banner ui-banner-accent text-xs flex items-center justify-between gap-3">
            <span>
              <span className="font-semibold">Browser zoom {Math.round(zoomPercent ?? 100)}%.</span> For best results, set it to 100% so UI elements stay in correct proportions.
            </span>
            {onDismissBrowserZoomWarning && (
              <button
                type="button"
                className="text-muted hover:text-text transition-colors text-base leading-none shrink-0"
                onClick={onDismissBrowserZoomWarning}
                aria-label="Dismiss browser zoom warning"
              >
                ×
              </button>
            )}
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
                  onClick={onRevealOffView}
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
