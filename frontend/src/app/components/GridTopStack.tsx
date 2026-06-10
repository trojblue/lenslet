import { type ReactNode } from 'react'
import StatusBar, { hasStatusBarContent, type StatusBarProps } from './StatusBar'
import type { ActionFeedback } from '../model/actionFeedback'

export type GridTopFilterChip = {
  id: string
  label: string
  onRemove: () => void
}

export type GridTopSimilarity = {
  embedding: string
  topK: number
  minScore: number | null
  queryLabel: string | null
  countLabel: string | null
}

type GridTopStackProps = {
  statusBarProps: StatusBarProps
  actionFeedback: ActionFeedback | null
  onDismissActionFeedback?: () => void
  similarity: GridTopSimilarity | null
  onExitSimilarity: () => void
  filterChips: GridTopFilterChip[]
  onClearFilters: () => void
}

type BandName = 'status' | 'similarity' | 'filters'

type GridTopBandProps = {
  name: BandName
  visible: boolean
  children: ReactNode
}

function GridTopBand({
  name,
  visible,
  children,
}: GridTopBandProps): JSX.Element {
  return (
    <section
      data-grid-top-band={name}
      aria-hidden={visible ? undefined : true}
      className={`grid-top-band${visible ? '' : ' is-hidden'}`}
    >
      {visible ? (
        children
      ) : (
        <div
          className="grid-top-band-reserve"
          aria-hidden="true"
        />
      )}
    </section>
  )
}

export default function GridTopStack({
  statusBarProps,
  actionFeedback,
  onDismissActionFeedback,
  similarity,
  onExitSimilarity,
  filterChips,
  onClearFilters,
}: GridTopStackProps): JSX.Element {
  const showStatusBand = hasStatusBarContent(statusBarProps) || Boolean(actionFeedback)
  const showSimilarityBand = similarity !== null
  const showFiltersBand = filterChips.length > 0

  return (
    <div data-grid-top-stack className="grid-top-stack">
      <GridTopBand
        name="status"
        visible={showStatusBand}
      >
        <StatusBar {...statusBarProps} />
        {actionFeedback && (
          <div className="border-b border-border bg-panel px-3 py-2">
            <div
              className={`ui-banner ${actionFeedback.kind === 'error' ? 'ui-banner-danger' : 'ui-banner-accent'} text-xs flex items-center justify-between gap-3`}
              role="status"
            >
              <span>{actionFeedback.message}</span>
              {onDismissActionFeedback && (
                <button
                  type="button"
                  className="text-muted hover:text-text transition-colors text-base leading-none shrink-0"
                  onClick={onDismissActionFeedback}
                  aria-label="Dismiss action status"
                >
                  ×
                </button>
              )}
            </div>
          </div>
        )}
      </GridTopBand>
      <GridTopBand
        name="similarity"
        visible={showSimilarityBand}
      >
        {similarity && (
          <div className="border-b border-border bg-panel">
            <div className="px-3 py-2 flex flex-wrap items-center gap-2">
              <div className="ui-banner ui-banner-accent text-xs flex flex-wrap items-center gap-2">
                <span className="font-semibold">Similarity mode</span>
                <span className="text-muted">Embedding: {similarity.embedding}</span>
                {similarity.queryLabel && (
                  <span className="text-muted">Query: {similarity.queryLabel}</span>
                )}
                {similarity.countLabel && (
                  <span className="text-muted">Results: {similarity.countLabel}</span>
                )}
                <span className="text-muted">Top K: {similarity.topK}</span>
                {similarity.minScore != null && (
                  <span className="text-muted">Min score: {similarity.minScore}</span>
                )}
              </div>
              <button className="btn btn-sm" onClick={onExitSimilarity}>
                Exit similarity
              </button>
            </div>
          </div>
        )}
      </GridTopBand>
      <GridTopBand
        name="filters"
        visible={showFiltersBand}
      >
        <div className="px-3 py-2 bg-panel border-b border-border">
          <div className="flex flex-wrap items-center gap-2">
            <span className="text-[11px] uppercase tracking-wide text-muted">Filters</span>
            {filterChips.map((chip) => (
              <span key={chip.id} className="filter-chip">
                <span className="truncate max-w-[240px]" title={chip.label}>{chip.label}</span>
                <button
                  className="filter-chip-remove"
                  aria-label={`Clear filter ${chip.label}`}
                  onClick={chip.onRemove}
                >
                  ×
                </button>
              </span>
            ))}
            <button className="btn btn-sm btn-ghost text-xs" onClick={onClearFilters}>
              Clear all
            </button>
          </div>
        </div>
      </GridTopBand>
    </div>
  )
}
