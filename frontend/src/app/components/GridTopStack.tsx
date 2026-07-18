import { useLayoutEffect, useRef } from 'react'
import StatusBar, { statusBarContentKey, type StatusBarProps } from './StatusBar'
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

export default function GridTopStack({
  statusBarProps,
  actionFeedback,
  onDismissActionFeedback,
  similarity,
  onExitSimilarity,
  filterChips,
  onClearFilters,
}: GridTopStackProps): JSX.Element {
  const railRef = useRef<HTMLDivElement>(null)
  const previousContextRef = useRef({
    status: '',
    action: null as string | null,
    similarity: null as string | null,
  })
  const statusKey = statusBarContentKey(statusBarProps)
  const actionKey = actionFeedback
    ? `${actionFeedback.kind}\u0000${actionFeedback.message}`
    : null
  const similarityKey = similarity
    ? `${similarity.embedding}\u0000${similarity.queryLabel ?? ''}`
    : null

  useLayoutEffect(() => {
    const previous = previousContextRef.current
    const statusIntroduced = statusKey !== '' && statusKey !== previous.status
    const actionIntroduced = actionKey !== null && actionKey !== previous.action
    const similarityIntroduced = (
      similarityKey !== null && similarityKey !== previous.similarity
    )
    previousContextRef.current = {
      status: statusKey,
      action: actionKey,
      similarity: similarityKey,
    }
    const rail = railRef.current
    if (!rail) return
    const introducedContext = similarityIntroduced
      ? rail.querySelector<HTMLElement>('[data-grid-top-similarity]')
      : actionIntroduced
        ? rail.querySelector<HTMLElement>('[data-grid-top-action]')
        : null
    if (introducedContext) {
      introducedContext.scrollIntoView({ block: 'nearest', inline: 'nearest' })
    } else if (statusIntroduced) {
      rail.scrollLeft = 0
    }
  }, [actionKey, similarityKey, statusKey])

  return (
    <div
      data-grid-top-stack
      data-filter-count={filterChips.length}
      className="grid-top-stack"
    >
      <div
        ref={railRef}
        data-grid-top-rail
        className="grid-top-rail scrollbar-thin"
        role="region"
        aria-label="Gallery filters and status"
        tabIndex={0}
      >
        <StatusBar {...statusBarProps} />
        {actionFeedback && (
          <div
            data-grid-top-action
            className={`grid-top-context-item ui-banner ${actionFeedback.kind === 'error' ? 'ui-banner-danger' : 'ui-banner-accent'} text-xs flex items-center justify-between gap-3`}
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
        )}
        {similarity && (
          <div
            data-grid-top-similarity
            className="grid-top-context-item ui-banner ui-banner-accent text-xs flex items-center gap-2"
          >
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
            <button className="btn btn-sm" onClick={onExitSimilarity}>
              Exit similarity
            </button>
          </div>
        )}
        <span className="grid-top-filter-label text-[11px] uppercase tracking-wide text-muted">
          Filters
        </span>
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
        {filterChips.length > 0 && (
          <button className="btn btn-sm btn-ghost text-xs shrink-0" onClick={onClearFilters}>
            Clear all
          </button>
        )}
      </div>
    </div>
  )
}
