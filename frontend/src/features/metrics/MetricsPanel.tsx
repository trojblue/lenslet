import React, { useMemo, useRef, useState } from 'react'
import type { FilterAST, Item } from '../../lib/types'
import { getMetricRangeFilter } from '../browse/model/filters'

type Range = { min: number; max: number }

interface Histogram {
  bins: number[]
  min: number
  max: number
  count: number
}

interface MetricsPanelProps {
  items: Item[]
  filteredItems: Item[]
  metricKeys: string[]
  selectedMetric?: string
  onSelectMetric: (key: string) => void
  filters: FilterAST
  onChangeRange: (key: string, range: Range | null) => void
}

const BIN_COUNT = 40

export default function MetricsPanel({
  items,
  filteredItems,
  metricKeys,
  selectedMetric,
  onSelectMetric,
  filters,
  onChangeRange,
}: MetricsPanelProps) {
  const activeMetric = selectedMetric && metricKeys.includes(selectedMetric) ? selectedMetric : metricKeys[0]
  const population = useMemo(() => (
    activeMetric ? computeHistogram(items, activeMetric, BIN_COUNT) : null
  ), [items, activeMetric])
  const filtered = useMemo(() => (
    activeMetric && population ? computeHistogram(filteredItems, activeMetric, BIN_COUNT, population) : null
  ), [filteredItems, activeMetric, population])

  const activeRange = activeMetric ? getMetricRangeFilter(filters, activeMetric) : null
  const [dragRange, setDragRange] = useState<Range | null>(null)
  const [dragging, setDragging] = useState(false)
  const svgRef = useRef<SVGSVGElement | null>(null)

  const displayRange = dragRange ?? activeRange
  const domain = population ? { min: population.min, max: population.max } : null

  const setRangeFromEvent = (e: React.PointerEvent<SVGSVGElement>, commit: boolean) => {
    if (!domain || !activeMetric) return
    const rect = svgRef.current?.getBoundingClientRect()
    if (!rect) return
    const t = clamp01((e.clientX - rect.left) / rect.width)
    const value = domain.min + (domain.max - domain.min) * t
    setDragRange((prev) => {
      const start = prev?.min ?? value
      const end = value
      const next = normalizeRange(start, end)
      if (commit) {
        onChangeRange(activeMetric, next)
      }
      return next
    })
  }

  const onPointerDown = (e: React.PointerEvent<SVGSVGElement>) => {
    if (!domain || !activeMetric) return
    e.preventDefault()
    setDragging(true)
    setDragRange(null)
    svgRef.current?.setPointerCapture(e.pointerId)
    setRangeFromEvent(e, false)
  }

  const onPointerMove = (e: React.PointerEvent<SVGSVGElement>) => {
    if (!dragging) return
    setRangeFromEvent(e, false)
  }

  const onPointerUp = (e: React.PointerEvent<SVGSVGElement>) => {
    if (!dragging) return
    setDragging(false)
    svgRef.current?.releasePointerCapture(e.pointerId)
    setRangeFromEvent(e, true)
    setTimeout(() => setDragRange(null), 0)
  }

  if (!metricKeys.length) {
    return (
      <div className="p-4 text-sm text-muted">
        No metrics found in this dataset.
      </div>
    )
  }

  return (
    <div className="h-full flex flex-col gap-3 p-3 overflow-auto scrollbar-thin">
      <div>
        <label className="block text-xs uppercase tracking-wide text-muted mb-1">Metric</label>
        <select
          className="h-8 w-full rounded-lg px-2.5 border border-border bg-[#1b1b1b] text-text"
          value={activeMetric}
          onChange={(e) => onSelectMetric(e.target.value)}
        >
          {metricKeys.map((key) => (
            <option key={key} value={key}>{key}</option>
          ))}
        </select>
      </div>

      {population ? (
        <div className="rounded-xl border border-border bg-[#161616] p-3">
          <div className="flex items-center justify-between text-xs text-muted mb-2">
            <span>Population: {population.count}</span>
            <span>Filtered: {filtered?.count ?? 0}</span>
          </div>
          <svg
            ref={svgRef}
            viewBox={`0 0 ${BIN_COUNT} 100`}
            preserveAspectRatio="none"
            className="w-full h-28 cursor-crosshair rounded-md bg-[#121212]"
            onPointerDown={onPointerDown}
            onPointerMove={onPointerMove}
            onPointerUp={onPointerUp}
          >
            {renderBars(population.bins, '#2e3a4b')}
            {filtered && renderBars(filtered.bins, '#3a8fff')}
            {displayRange && domain && renderRange(displayRange, domain)}
          </svg>
          <div className="flex items-center justify-between text-[11px] text-muted mt-2">
            <span>{formatNumber(domain?.min)}</span>
            {displayRange ? (
              <span className="text-text">{formatNumber(displayRange.min)} – {formatNumber(displayRange.max)}</span>
            ) : (
              <span>Drag to filter</span>
            )}
            <span>{formatNumber(domain?.max)}</span>
          </div>
          <div className="flex items-center gap-2 mt-2">
            <button
              className="h-7 px-2.5 bg-[#1b1b1b] text-text border border-border rounded-lg cursor-pointer"
              onClick={() => activeMetric && onChangeRange(activeMetric, null)}
            >
              Clear
            </button>
          </div>
        </div>
      ) : (
        <div className="text-sm text-muted">No values found for this metric.</div>
      )}
    </div>
  )
}

function computeHistogram(items: Item[], key: string, bins: number, base?: Histogram): Histogram | null {
  const values: number[] = []
  for (const it of items) {
    const val = it.metrics?.[key]
    if (val == null || Number.isNaN(val)) continue
    values.push(val)
  }
  if (!values.length) return null
  const min = base ? base.min : Math.min(...values)
  let max = base ? base.max : Math.max(...values)
  if (min === max) max = min + 1

  const counts = new Array(bins).fill(0)
  const scale = bins / (max - min)
  for (const v of values) {
    const idx = Math.max(0, Math.min(bins - 1, Math.floor((v - min) * scale)))
    counts[idx] += 1
  }
  return { bins: counts, min, max, count: values.length }
}

function renderBars(bins: number[], color: string) {
  const max = Math.max(1, ...bins)
  return bins.map((count, i) => {
    const height = (count / max) * 100
    return (
      <rect
        key={`${color}-${i}`}
        x={i + 0.05}
        y={100 - height}
        width={0.9}
        height={height}
        fill={color}
        opacity={0.9}
      />
    )
  })
}

function renderRange(range: Range, domain: { min: number; max: number }) {
  const start = (range.min - domain.min) / (domain.max - domain.min)
  const end = (range.max - domain.min) / (domain.max - domain.min)
  const x = BIN_COUNT * clamp01(Math.min(start, end))
  const w = BIN_COUNT * Math.abs(end - start)
  return (
    <rect
      x={x}
      y={0}
      width={Math.max(0.5, w)}
      height={100}
      fill="rgba(255,255,255,0.08)"
      stroke="rgba(255,255,255,0.4)"
      strokeWidth={0.4}
    />
  )
}

function normalizeRange(a: number, b: number): Range {
  return a < b ? { min: a, max: b } : { min: b, max: a }
}

function clamp01(v: number): number {
  if (v < 0) return 0
  if (v > 1) return 1
  return v
}

function formatNumber(value?: number | null): string {
  if (value == null || Number.isNaN(value)) return '–'
  const abs = Math.abs(value)
  if (abs >= 1000) return value.toFixed(0)
  if (abs >= 10) return value.toFixed(2)
  return value.toFixed(3)
}
