import React, { useEffect, useMemo, useRef, useState } from 'react'
import type { BrowseItemPayload } from '../../../lib/types'
import { finiteMetricValue } from '../../../lib/metrics'
import {
  clamp01,
  computeMetricRailHistogram,
  type MetricRailHistogram,
  type MetricRailState,
  metricRailProgressFromValue,
  metricValueAtProgress,
  metricValueFromRailProgress,
} from '../model/metricRail'

const BIN_COUNT = 48
const QUANTILES = [0.1, 0.24, 0.5, 0.74, 0.9]

interface MetricScrollbarProps {
  items: BrowseItemPayload[]
  metricKey: string
  metricLabel?: string
  scrollRef: React.RefObject<HTMLDivElement>
  sortDir: 'asc' | 'desc'
  currentPath?: string | null
  state?: MetricRailState
  histogramOverride?: MetricRailHistogram | null
  populationComplete?: boolean
  onJumpToMetricValue: (value: number) => void
  onRetry?: () => void
}

export default function MetricScrollbar({
  items,
  metricKey,
  metricLabel,
  scrollRef,
  sortDir,
  currentPath = null,
  state = 'ready',
  histogramOverride = null,
  populationComplete = true,
  onJumpToMetricValue,
  onRetry,
}: MetricScrollbarProps) {
  const { orderedValues, numericValues } = useMemo(() => {
    const ordered: Array<number | null> = []
    const numeric: number[] = []
    for (const it of items) {
      const value = finiteMetricValue(it.metrics?.[metricKey])
      ordered.push(value)
      if (value != null) numeric.push(value)
    }
    return { orderedValues: ordered, numericValues: numeric }
  }, [items, metricKey])
  const loadedHistogram = useMemo(() => (
    computeMetricRailHistogram(numericValues, BIN_COUNT)
  ), [numericValues])
  const histogram = histogramOverride ?? loadedHistogram
  const quantiles = useMemo(
    () => histogram ? computeHistogramQuantiles(histogram, QUANTILES) : [],
    [histogram],
  )

  const [scrollProgress, setScrollProgress] = useState(0)
  const [hoverProgress, setHoverProgress] = useState<number | null>(null)
  const [scrubbing, setScrubbing] = useState(false)
  const svgRef = useRef<SVGSVGElement | null>(null)

  useEffect(() => {
    const el = scrollRef.current
    if (!el) return

    const update = () => {
      const max = Math.max(1, el.scrollHeight - el.clientHeight)
      const next = clamp01(max > 0 ? el.scrollTop / max : 0)
      setScrollProgress(next)
    }

    update()
    el.addEventListener('scroll', update, { passive: true })
    window.addEventListener('resize', update)
    return () => {
      el.removeEventListener('scroll', update)
      window.removeEventListener('resize', update)
    }
  }, [scrollRef, items.length])

  useEffect(() => {
    setHoverProgress(null)
  }, [metricKey, items.length])

  const domain = histogram ? { min: histogram.min, max: histogram.max } : null
  const scrollValue = useMemo(
    () => {
      if (currentPath) {
        const current = items.find((item) => item.path === currentPath)
        const value = finiteMetricValue(current?.metrics?.[metricKey])
        if (value != null) return value
      }
      return metricValueAtProgress(orderedValues, scrollProgress)
    },
    [currentPath, items, metricKey, orderedValues, scrollProgress],
  )
  const hoverValue = useMemo(() => {
    if (hoverProgress == null || domain == null) return null
    return metricValueFromRailProgress(hoverProgress, domain, sortDir)
  }, [domain?.max, domain?.min, hoverProgress, sortDir])

  const label = metricLabel ?? metricKey
  if (state !== 'ready' || !histogram || !domain) {
    return (
      <div
        className="relative h-full w-full flex items-center justify-center rounded bg-surface-inset border border-border/60"
        data-metric-rail={metricKey}
        data-metric-rail-state={state}
        aria-busy={state === 'pending' || undefined}
      >
        {state === 'error' && onRetry ? (
          <button
            type="button"
            className="btn btn-ghost h-full w-full min-w-0 px-0 text-danger"
            aria-label={`Retry ${label} metric distribution`}
            title={`Retry ${label} metric distribution`}
            onClick={onRetry}
          >
            !
          </button>
        ) : (
          <span
            className="text-[10px] text-muted"
            aria-label={state === 'empty'
              ? `No finite values for ${label} metric distribution`
              : `Loading ${label} metric distribution`}
          >
            {state === 'empty' ? '—' : ''}
          </span>
        )}
      </div>
    )
  }
  const railDomain = domain

  const hoverY = hoverProgress != null ? progressToY(hoverProgress) : null
  const isDesc = sortDir === 'desc'
  const jumpEnabled = populationComplete
  const railClassName = `w-full h-full rounded bg-surface-inset border border-border/60 ${
    jumpEnabled ? 'cursor-crosshair' : 'cursor-default'
  }`
  const scrollY = scrollValue == null
    ? progressToY(scrollProgress)
    : progressToY(metricRailProgressFromValue(scrollValue, railDomain, sortDir))

  function updateHover(progress: number) {
    setHoverProgress(clamp01(progress))
  }

  function clearHover() {
    setHoverProgress(null)
  }

  function jumpToProgress(progress: number) {
    if (!jumpEnabled) return
    onJumpToMetricValue(metricValueFromRailProgress(progress, railDomain, sortDir))
  }

  function getProgressFromEvent(e: React.PointerEvent<SVGSVGElement>): number | null {
    const rect = svgRef.current?.getBoundingClientRect()
    if (!rect) return null
    return clamp01((e.clientY - rect.top) / rect.height)
  }

  return (
    <div
      className="relative h-full w-full flex items-stretch pointer-events-auto"
      data-metric-rail={metricKey}
      data-metric-rail-state="ready"
      data-metric-rail-count={histogram.count}
      data-metric-rail-min={histogram.min}
      data-metric-rail-max={histogram.max}
      data-metric-rail-bins={histogram.bins.join(',')}
      data-metric-rail-quantiles={quantiles.join(',')}
    >
      <svg
        ref={svgRef}
        viewBox="0 0 10 100"
        preserveAspectRatio="none"
        className={railClassName}
        aria-label={`${label} metric distribution rail`}
        onPointerDown={(e) => {
          e.preventDefault()
          const progress = getProgressFromEvent(e)
          if (progress == null) return
          setScrubbing(true)
          updateHover(progress)
          jumpToProgress(progress)
          svgRef.current?.setPointerCapture(e.pointerId)
        }}
        onPointerMove={(e) => {
          const progress = getProgressFromEvent(e)
          if (progress == null) {
            if (!scrubbing) clearHover()
            return
          }
          updateHover(progress)
          if (scrubbing) jumpToProgress(progress)
        }}
        onPointerUp={(e) => {
          setScrubbing(false)
          svgRef.current?.releasePointerCapture(e.pointerId)
        }}
        onPointerLeave={() => {
          if (!scrubbing) clearHover()
        }}
      >
        <title>{jumpEnabled ? label : `${label} backend summary`}</title>
        {renderScrollbarBars(histogram.bins, 'var(--border-strong)', { flip: isDesc })}
        {renderQuantileTicks(quantiles, railDomain, { sortDir, color: 'var(--muted)' })}
        {renderLine(scrollY, { color: 'var(--highlight)', strokeWidth: 0.8 })}
        {hoverY != null && renderLine(hoverY, { color: 'var(--text-secondary)', strokeWidth: 0.6, dashed: true })}
      </svg>
      {hoverValue != null && hoverProgress != null && (
        <div
          className="pointer-events-none absolute right-full mr-2 px-1.5 py-0.5 rounded border border-border bg-surface text-[10px] text-text shadow"
          style={{ top: `calc(${(hoverProgress * 100).toFixed(2)}% - 8px)` }}
        >
          {formatNumber(hoverValue)}
        </div>
      )}
    </div>
  )
}

function computeHistogramQuantiles(
  histogram: MetricRailHistogram,
  quantiles: readonly number[],
): number[] {
  const total = histogram.bins.reduce((sum, count) => sum + count, 0)
  if (!total || !histogram.bins.length) return []
  const binWidth = (histogram.max - histogram.min) / histogram.bins.length
  return quantiles.map((quantile) => {
    const target = clamp01(quantile) * Math.max(0, total - 1)
    let cumulative = 0
    for (let index = 0; index < histogram.bins.length; index += 1) {
      cumulative += histogram.bins[index]
      if (cumulative > target) return histogram.min + ((index + 0.5) * binWidth)
    }
    return histogram.max
  })
}

function renderScrollbarBars(bins: number[], color: string, options?: { flip?: boolean }) {
  const max = Math.max(1, ...bins)
  const binH = 100 / bins.length
  const flip = options?.flip ?? false
  return bins.map((count, i) => {
    const width = Math.max(0.8, (count / max) * 10)
    const y = (flip ? (bins.length - 1 - i) : i) * binH
    return (
      <rect
        key={`sb-${i}`}
        x={10 - width}
        y={y}
        width={width}
        height={Math.max(0.2, binH - 0.2)}
        fill={color}
        opacity={0.9}
      />
    )
  })
}

function renderQuantileTicks(
  values: number[],
  domain: { min: number; max: number },
  options?: { sortDir?: 'asc' | 'desc'; color?: string }
) {
  const sortDir = options?.sortDir ?? 'asc'
  const color = options?.color ?? 'currentColor'
  return values.map((value, idx) => {
    const y = progressToY(metricRailProgressFromValue(value, domain, sortDir))
    const isMedian = idx === 2
    return (
      <line
        key={`qt-${idx}-${value}`}
        x1={0}
        y1={y}
        x2={10}
        y2={y}
        stroke={color}
        strokeWidth={isMedian ? 0.8 : 0.5}
        opacity={isMedian ? 0.9 : 0.6}
        vectorEffect="non-scaling-stroke"
      />
    )
  })
}

function renderLine(y: number, options: { color: string; strokeWidth?: number; dashed?: boolean }) {
  return (
    <line
      x1={0}
      y1={y}
      x2={10}
      y2={y}
      stroke={options.color}
      strokeWidth={options.strokeWidth ?? 0.6}
      strokeDasharray={options.dashed ? '1.2 1.2' : undefined}
      opacity={0.95}
      vectorEffect="non-scaling-stroke"
    />
  )
}

function progressToY(progress: number): number {
  return clamp01(progress) * 100
}

function formatNumber(value?: number | null): string {
  const metricValue = finiteMetricValue(value)
  if (metricValue == null) return '-'
  const abs = Math.abs(metricValue)
  if (abs >= 1000) return metricValue.toFixed(0)
  if (abs >= 10) return metricValue.toFixed(2)
  return metricValue.toFixed(3)
}
