import React from 'react'
import { fmtBytes } from '../../../lib/util'
import type { SortSpec, StarRating } from '../../../lib/types'
import { InspectorSection } from './InspectorSection'

function formatMetricValue(value: number | null | undefined): string {
  if (value == null || Number.isNaN(value)) return '–'
  const abs = Math.abs(value)
  if (abs >= 1000) return value.toFixed(0)
  if (abs >= 10) return value.toFixed(2)
  return value.toFixed(3)
}

interface BasicsInspectorItem {
  path: string
  size: number
  w: number
  h: number
  type: string
  source?: string | null
  star?: number | null
  metrics?: Record<string, number | null> | null
}

interface BasicsSectionProps {
  open: boolean
  onToggle: () => void
  multi: boolean
  star: StarRating | null
  onSelectStar: (value: StarRating) => void
  hasStarConflict: boolean
  onApplyConflict: () => void
  onKeepTheirs: () => void
  currentItem: BasicsInspectorItem | null
  sourceValue: string
  sortSpec?: SortSpec
  copiedField: string | null
  onCopyInfo: (key: string, text: string) => void
  valueHeights: Record<string, number>
  onRememberHeight: (key: string, element: HTMLSpanElement | null) => void
  metricsExpanded: boolean
  onToggleMetricsExpanded: () => void
  metricsPreviewLimit: number
}

export function BasicsSection({
  open,
  onToggle,
  multi,
  star,
  onSelectStar,
  hasStarConflict,
  onApplyConflict,
  onKeepTheirs,
  currentItem,
  sourceValue,
  sortSpec,
  copiedField,
  onCopyInfo,
  valueHeights,
  onRememberHeight,
  metricsExpanded,
  onToggleMetricsExpanded,
  metricsPreviewLimit,
}: BasicsSectionProps): JSX.Element {
  return (
    <InspectorSection
      title="Basics"
      open={open}
      onToggle={onToggle}
    >
      <div className="flex items-center gap-2 text-xs mb-1" role="radiogroup" aria-label="Star rating">
        <span className="ui-kv-label w-16 shrink-0">{multi ? 'Rating (all)' : 'Rating'}</span>
        <div className="flex items-center gap-1">
          {[1, 2, 3, 4, 5].map((v) => {
            const filled = (star ?? 0) >= v
            return (
              <button
                key={v}
                className={`w-6 h-6 flex items-center justify-center rounded-lg border border-border/60 bg-transparent text-[13px] ${filled ? 'text-star-active' : 'text-star-inactive'} hover:border-border hover:text-star-hover transition-colors`}
                onClick={() => {
                  const value: StarRating = star === v && !multi ? null : (v as 1 | 2 | 3 | 4 | 5)
                  onSelectStar(value)
                }}
                title={`${v} star${v > 1 ? 's' : ''} (key ${v})`}
                aria-label={`${v} star${v > 1 ? 's' : ''}`}
                aria-pressed={star === v}
              >
                {filled ? '★' : '☆'}
              </button>
            )
          })}
        </div>
      </div>

      {hasStarConflict && (
        <div className="ui-banner ui-banner-danger mt-2 text-[11px] flex items-center justify-between gap-2">
          <span>Rating conflict.</span>
          <div className="flex items-center gap-2">
            <button className="btn btn-sm" onClick={onApplyConflict}>
              Apply again
            </button>
            <button className="btn btn-sm btn-ghost" onClick={onKeepTheirs}>
              Keep theirs
            </button>
          </div>
        </div>
      )}

      {!multi && currentItem && (
        <div className="text-[12px] space-y-1.5 leading-relaxed">
          <div className="ui-kv-row">
            <span
              className="ui-kv-label ui-kv-label-action w-20 shrink-0"
              onClick={() => onCopyInfo('dimensions', `${currentItem.w}×${currentItem.h}`)}
            >
              Dimensions
            </span>
            <span
              className="ui-kv-value inline-block text-right min-w-[80px]"
              ref={(el) => onRememberHeight('dimensions', el)}
              style={valueHeights.dimensions ? { minHeight: valueHeights.dimensions } : undefined}
            >
              {copiedField === 'dimensions' ? 'Copied' : `${currentItem.w}×${currentItem.h}`}
            </span>
          </div>
          <div className="ui-kv-row">
            <span
              className="ui-kv-label ui-kv-label-action w-20 shrink-0"
              onClick={() => onCopyInfo('size', fmtBytes(currentItem.size))}
            >
              Size
            </span>
            <span
              className="ui-kv-value inline-block text-right min-w-[80px]"
              ref={(el) => onRememberHeight('size', el)}
              style={valueHeights.size ? { minHeight: valueHeights.size } : undefined}
            >
              {copiedField === 'size' ? 'Copied' : fmtBytes(currentItem.size)}
            </span>
          </div>
          <div className="ui-kv-row">
            <span
              className="ui-kv-label ui-kv-label-action w-20 shrink-0"
              onClick={() => onCopyInfo('type', currentItem.type)}
            >
              Type
            </span>
            <span
              className="ui-kv-value break-all text-right inline-block min-w-[80px]"
              ref={(el) => onRememberHeight('type', el)}
              style={valueHeights.type ? { minHeight: valueHeights.type } : undefined}
            >
              {copiedField === 'type' ? 'Copied' : currentItem.type}
            </span>
          </div>
          <div className="ui-kv-row">
            <span
              className="ui-kv-label ui-kv-label-action w-20 shrink-0"
              onClick={() => sourceValue && onCopyInfo('source', sourceValue)}
            >
              Source
            </span>
            <span
              className="ui-kv-value inspector-value-clamp break-words text-right max-w-[70%] inline-block min-w-[80px]"
              ref={(el) => onRememberHeight('source', el)}
              style={valueHeights.source ? { minHeight: valueHeights.source } : undefined}
              title={sourceValue}
            >
              {copiedField === 'source' ? 'Copied' : sourceValue}
            </span>
          </div>
          {(() => {
            const metrics = currentItem.metrics || null
            if (!metrics) return null
            const entries = Object.entries(metrics).filter(([, v]) => v != null)
            if (!entries.length) return null
            const highlightKey = sortSpec?.kind === 'metric' ? sortSpec.key : null
            const sorted = [...entries].sort(([a], [b]) => a.localeCompare(b))
            let ordered = sorted
            if (highlightKey) {
              const idx = sorted.findIndex(([key]) => key === highlightKey)
              if (idx > 0) {
                ordered = [sorted[idx], ...sorted.slice(0, idx), ...sorted.slice(idx + 1)]
              }
            }
            const canToggle = ordered.length > metricsPreviewLimit
            const showAll = metricsExpanded || !canToggle
            const show = showAll ? ordered : ordered.slice(0, metricsPreviewLimit)
            const remaining = ordered.length - metricsPreviewLimit
            return (
              <div className="mt-3">
                <div className="ui-subsection-title mb-1">Metrics</div>
                <div className="space-y-1">
                  {show.map(([key, val]) => {
                    const isHighlighted = highlightKey === key
                    return (
                      <div key={key} className="ui-kv-row">
                        <span className={`w-24 shrink-0 ${isHighlighted ? 'text-accent font-medium' : 'ui-kv-label'}`}>
                          {key}
                        </span>
                        <span className={`ui-kv-value text-right ${isHighlighted ? 'text-accent font-medium' : ''}`}>
                          {formatMetricValue(val)}
                        </span>
                      </div>
                    )
                  })}
                  {canToggle && (
                    <button
                      type="button"
                      className="text-[11px] text-muted underline underline-offset-2 hover:text-text"
                      onClick={onToggleMetricsExpanded}
                      aria-expanded={metricsExpanded}
                    >
                      {metricsExpanded ? 'Show less' : `+${remaining} more`}
                    </button>
                  )}
                </div>
              </div>
            )
          })()}
        </div>
      )}
    </InspectorSection>
  )
}
