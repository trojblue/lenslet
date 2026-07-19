import React from 'react'
import { formatNumber, type Histogram } from '../model/histogram'
import type { FacetFieldState } from '../model/facetPresentation'

interface DerivedMetricMiniHistogramProps {
  histogram: Histogram | null
  metricKey: string
  state?: FacetFieldState
}

export default function DerivedMetricMiniHistogram({
  histogram,
  metricKey,
  state = histogram ? 'ready' : 'empty',
}: DerivedMetricMiniHistogramProps): JSX.Element {
  if (state !== 'ready' || !histogram) {
    return (
      <div
        className="flex h-[3.25rem] items-center justify-center rounded-sm border border-border/50 bg-surface/60 px-2 py-1 text-[10px] text-muted"
        data-derived-metric-histogram={metricKey}
        data-facet-state={state}
        role="status"
      >
        {state === 'pending'
          ? 'Loading values…'
          : state === 'error'
            ? 'Could not load values'
            : 'No finite values'}
      </div>
    )
  }

  const bins = histogram.bins
  const width = Math.max(1, bins.length)
  const maxCount = Math.max(1, ...bins)

  return (
    <div
      className="h-[3.25rem] space-y-0.5"
      data-derived-metric-histogram={metricKey}
      data-facet-state="ready"
    >
      <svg
        viewBox={`0 0 ${width} 32`}
        preserveAspectRatio="none"
        className="h-8 w-full rounded-sm border border-border/50 bg-surface/60"
        aria-label={`${metricKey} distribution`}
        role="img"
      >
        <line x1="0" y1="31.5" x2={width} y2="31.5" stroke="var(--border-strong)" strokeWidth="0.35" />
        {bins.map((count, index) => {
          const height = Math.max(0.75, (count / maxCount) * 29)
          return (
            <rect
              key={`${metricKey}-${index}`}
              x={index + 0.15}
              y={31 - height}
              width={0.7}
              height={height}
              fill="#7dd3fc"
              opacity={0.68}
            />
          )
        })}
      </svg>
      <div className="flex items-center justify-between gap-2 text-[10px] text-muted tabular-nums">
        <span>{formatNumber(histogram.min)}</span>
        <span>{histogram.count} values</span>
        <span>{formatNumber(histogram.max)}</span>
      </div>
    </div>
  )
}
