import React, { useEffect, useMemo, useRef, useState } from 'react'
import type { Item } from '../../../lib/types'

const BIN_COUNT = 48
const QUANTILES = [0.1, 0.24, 0.5, 0.74, 0.9]

interface MetricScrollbarProps {
  items: Item[]
  metricKey: string
  scrollRef: React.RefObject<HTMLDivElement>
  sortDir: 'asc' | 'desc'
}

export default function MetricScrollbar({ items, metricKey, scrollRef, sortDir }: MetricScrollbarProps) {
  const orderedValues = useMemo(() => (
    items.map((it) => {
      const raw = it.metrics?.[metricKey]
      if (raw == null || Number.isNaN(raw)) return null
      return raw
    })
  ), [items, metricKey])
  const numericValues = useMemo(() => orderedValues.filter((v): v is number => v != null), [orderedValues])
  const histogram = useMemo(() => computeHistogram(numericValues, BIN_COUNT), [numericValues])
  const quantiles = useMemo(() => computeQuantiles(numericValues, QUANTILES), [numericValues])

  const [scrollProgress, setScrollProgress] = useState(0)
  const [hoverProgress, setHoverProgress] = useState<number | null>(null)
  const [hoverValue, setHoverValue] = useState<number | null>(null)
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
    el.addEventListener('scroll', update, { passive: true } as any)
    window.addEventListener('resize', update)
    return () => {
      el.removeEventListener('scroll', update as any)
      window.removeEventListener('resize', update)
    }
  }, [scrollRef, items.length])

  useEffect(() => {
    setHoverProgress(null)
    setHoverValue(null)
  }, [metricKey, items.length])

  if (!histogram) return null

  const domain = { min: histogram.min, max: histogram.max }
  const hoverY = hoverProgress != null ? progressToY(hoverProgress) : null
  const scrollY = progressToY(scrollProgress)
  const isDesc = sortDir === 'desc'

  const updateHover = (progress: number) => {
    const clamped = clamp01(progress)
    setHoverProgress(clamped)
    setHoverValue(valueAtProgress(orderedValues, clamped))
  }

  const scrollToProgress = (progress: number) => {
    const el = scrollRef.current
    if (!el) return
    const max = Math.max(0, el.scrollHeight - el.clientHeight)
    el.scrollTop = clamp01(progress) * max
  }

  const getProgressFromEvent = (e: React.PointerEvent<SVGSVGElement>): number | null => {
    const rect = svgRef.current?.getBoundingClientRect()
    if (!rect) return null
    return clamp01((e.clientY - rect.top) / rect.height)
  }

  return (
    <div className="absolute right-3 top-3 bottom-3 w-3 flex items-stretch pointer-events-auto">
      <svg
        ref={svgRef}
        viewBox="0 0 10 100"
        preserveAspectRatio="none"
        className="w-full h-full rounded bg-surface-inset border border-border/60 cursor-ns-resize"
        onPointerDown={(e) => {
          e.preventDefault()
          const progress = getProgressFromEvent(e)
          if (progress == null) return
          setScrubbing(true)
          updateHover(progress)
          scrollToProgress(progress)
          svgRef.current?.setPointerCapture(e.pointerId)
        }}
        onPointerMove={(e) => {
          const progress = getProgressFromEvent(e)
          if (progress == null) {
            if (!scrubbing) {
              setHoverProgress(null)
              setHoverValue(null)
            }
            return
          }
          updateHover(progress)
          if (scrubbing) scrollToProgress(progress)
        }}
        onPointerUp={(e) => {
          setScrubbing(false)
          svgRef.current?.releasePointerCapture(e.pointerId)
        }}
        onPointerLeave={() => {
          if (!scrubbing) {
            setHoverProgress(null)
            setHoverValue(null)
          }
        }}
      >
        {renderScrollbarBars(histogram.bins, '#2e3a4b', { flip: isDesc })}
        {renderQuantileTicks(quantiles, domain, { flip: isDesc })}
        {renderLine(scrollY, { color: 'var(--accent)', strokeWidth: 0.8 })}
        {hoverY != null && renderLine(hoverY, { color: 'rgba(255,255,255,0.75)', strokeWidth: 0.6, dashed: true })}
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

function computeHistogram(values: number[], bins: number) {
  if (!values.length) return null
  const min = Math.min(...values)
  let max = Math.max(...values)
  if (min === max) max = min + 1

  const counts = new Array(bins).fill(0)
  const scale = bins / (max - min)
  for (const v of values) {
    const idx = Math.max(0, Math.min(bins - 1, Math.floor((v - min) * scale)))
    counts[idx] += 1
  }
  return { bins: counts, min, max }
}

function computeQuantiles(values: number[], quantiles: number[]): number[] {
  if (!values.length) return []
  const sorted = [...values].sort((a, b) => a - b)
  const maxIndex = sorted.length - 1
  return quantiles.map((q) => {
    const idx = maxIndex * q
    const low = Math.floor(idx)
    const high = Math.ceil(idx)
    if (low === high) return sorted[low]
    const t = idx - low
    return sorted[low] + (sorted[high] - sorted[low]) * t
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

function renderQuantileTicks(values: number[], domain: { min: number; max: number }, options?: { flip?: boolean }) {
  const flip = options?.flip ?? false
  return values.map((value, idx) => {
    const y = valueToY(value, domain, flip)
    const isMedian = idx === 2
    return (
      <line
        key={`qt-${idx}-${value}`}
        x1={0}
        y1={y}
        x2={10}
        y2={y}
        stroke="rgba(255,255,255,0.45)"
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

function valueAtProgress(values: Array<number | null>, progress: number): number | null {
  if (!values.length) return null
  const idx = Math.round(clamp01(progress) * (values.length - 1))
  const direct = values[idx]
  if (direct != null) return direct
  for (let offset = 1; offset < values.length; offset++) {
    const up = idx - offset
    if (up >= 0 && values[up] != null) return values[up] as number
    const down = idx + offset
    if (down < values.length && values[down] != null) return values[down] as number
  }
  return null
}

function valueToY(value: number, domain: { min: number; max: number }, flip: boolean): number {
  const range = domain.max - domain.min
  if (range === 0) return 0
  const t = clamp01((value - domain.min) / range)
  return (flip ? (1 - t) : t) * 100
}

function progressToY(progress: number): number {
  return clamp01(progress) * 100
}

function clamp01(value: number): number {
  if (value < 0) return 0
  if (value > 1) return 1
  return value
}

function formatNumber(value?: number | null): string {
  if (value == null || Number.isNaN(value)) return '-'
  const abs = Math.abs(value)
  if (abs >= 1000) return value.toFixed(0)
  if (abs >= 10) return value.toFixed(2)
  return value.toFixed(3)
}
