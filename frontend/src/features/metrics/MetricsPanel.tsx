import React, { useEffect, useMemo, useRef, useState } from 'react'
import type { FilterAST, Item } from '../../lib/types'
import {
  getCommentsContainsFilter,
  getCommentsNotContainsFilter,
  getDateRangeFilter,
  getHeightCompareFilter,
  getMetricRangeFilter,
  getNameContainsFilter,
  getNameNotContainsFilter,
  getStarsInFilter,
  getStarsNotInFilter,
  getUrlContainsFilter,
  getUrlNotContainsFilter,
  getWidthCompareFilter,
  setCommentsContainsFilter,
  setCommentsNotContainsFilter,
  setDateRangeFilter,
  setHeightCompareFilter,
  setNameContainsFilter,
  setNameNotContainsFilter,
  setStarsInFilter,
  setStarsNotInFilter,
  setUrlContainsFilter,
  setUrlNotContainsFilter,
  setWidthCompareFilter,
} from '../browse/model/filters'

type Range = { min: number; max: number }

type CompareOp = '<' | '<=' | '>' | '>='

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
  onChangeFilters: (filters: FilterAST) => void
}

interface AttributesPanelProps {
  filters: FilterAST
  onChangeFilters: (filters: FilterAST) => void
}

interface MetricRangePanelProps {
  items: Item[]
  filteredItems: Item[]
  metricKeys: string[]
  selectedMetric?: string
  onSelectMetric: (key: string) => void
  filters: FilterAST
  onChangeRange: (key: string, range: Range | null) => void
}

const BIN_COUNT = 40
const STAR_VALUES = [5, 4, 3, 2, 1]
const COMPARE_OPS: CompareOp[] = ['<', '<=', '>', '>=']

export default function MetricsPanel({
  items,
  filteredItems,
  metricKeys,
  selectedMetric,
  onSelectMetric,
  filters,
  onChangeRange,
  onChangeFilters,
}: MetricsPanelProps) {
  const attributesPanel = (
    <AttributesPanel
      filters={filters}
      onChangeFilters={onChangeFilters}
    />
  )

  if (!metricKeys.length) {
    return (
      <div className="h-full flex flex-col gap-3 p-3 overflow-auto scrollbar-thin">
        {attributesPanel}
        <div className="p-4 text-sm text-muted">
          No metrics found in this dataset.
        </div>
      </div>
    )
  }

  return (
    <div className="h-full flex flex-col gap-3 p-3 overflow-auto scrollbar-thin">
      {attributesPanel}
      <MetricRangePanel
        items={items}
        filteredItems={filteredItems}
        metricKeys={metricKeys}
        selectedMetric={selectedMetric}
        onSelectMetric={onSelectMetric}
        filters={filters}
        onChangeRange={onChangeRange}
      />
    </div>
  )
}

function AttributesPanel({ filters, onChangeFilters }: AttributesPanelProps) {
  const starsIn = useMemo(() => getStarsInFilter(filters), [filters])
  const starsNotIn = useMemo(() => getStarsNotInFilter(filters), [filters])
  const nameContains = useMemo(() => getNameContainsFilter(filters) ?? '', [filters])
  const nameNotContains = useMemo(() => getNameNotContainsFilter(filters) ?? '', [filters])
  const commentsContains = useMemo(() => getCommentsContainsFilter(filters) ?? '', [filters])
  const commentsNotContains = useMemo(() => getCommentsNotContainsFilter(filters) ?? '', [filters])
  const urlContains = useMemo(() => getUrlContainsFilter(filters) ?? '', [filters])
  const urlNotContains = useMemo(() => getUrlNotContainsFilter(filters) ?? '', [filters])
  const dateRange = useMemo(() => getDateRangeFilter(filters) ?? {}, [filters])
  const dateFromValue = useMemo(() => toDateInputValue(dateRange.from), [dateRange.from])
  const dateToValue = useMemo(() => toDateInputValue(dateRange.to), [dateRange.to])
  const widthCompare = useMemo(() => getWidthCompareFilter(filters), [filters])
  const heightCompare = useMemo(() => getHeightCompareFilter(filters), [filters])

  const [widthOp, setWidthOp] = useState<CompareOp>(widthCompare?.op ?? '>=')
  const [heightOp, setHeightOp] = useState<CompareOp>(heightCompare?.op ?? '>=')

  useEffect(() => {
    if (widthCompare?.op) setWidthOp(widthCompare.op)
  }, [widthCompare?.op])

  useEffect(() => {
    if (heightCompare?.op) setHeightOp(heightCompare.op)
  }, [heightCompare?.op])

  const toggleStar = (kind: 'include' | 'exclude', value: number) => {
    const includeSet = new Set(starsIn)
    const excludeSet = new Set(starsNotIn)
    if (kind === 'include') {
      if (includeSet.has(value)) {
        includeSet.delete(value)
      } else {
        includeSet.add(value)
        excludeSet.delete(value)
      }
    } else {
      if (excludeSet.has(value)) {
        excludeSet.delete(value)
      } else {
        excludeSet.add(value)
        includeSet.delete(value)
      }
    }
    let next = setStarsInFilter(filters, Array.from(includeSet))
    next = setStarsNotInFilter(next, Array.from(excludeSet))
    onChangeFilters(next)
  }

  return (
    <div className="rounded-xl border border-border bg-panel p-3">
      <div className="text-[11px] uppercase tracking-wide text-muted mb-3">Attributes</div>
      <div className="space-y-4">
        <div>
          <div className="text-xs uppercase tracking-wide text-muted mb-2">Rating</div>
          <div className="space-y-2">
            <div>
              <div className="text-[11px] text-muted mb-1">Include</div>
              <div className="flex flex-wrap gap-1">
                {STAR_VALUES.map((v) => {
                  const active = starsIn.includes(v)
                  return (
                    <button
                      key={`stars-in-${v}`}
                      className={`h-7 min-w-[32px] px-2 rounded border text-[11px] flex items-center justify-center transition-colors ${
                        active
                          ? 'bg-accent-muted text-star-active border-border'
                          : 'bg-surface text-text border-border/70 hover:bg-surface-hover'
                      }`}
                      onClick={() => toggleStar('include', v)}
                      aria-pressed={active}
                      title={`Include ${v} star${v > 1 ? 's' : ''}`}
                    >
                      {v}★
                    </button>
                  )
                })}
                <button
                  className={`h-7 min-w-[48px] px-2 rounded border text-[11px] flex items-center justify-center transition-colors ${
                    starsIn.includes(0)
                      ? 'bg-accent-muted text-star-active border-border'
                      : 'bg-surface text-text border-border/70 hover:bg-surface-hover'
                  }`}
                  onClick={() => toggleStar('include', 0)}
                  aria-pressed={starsIn.includes(0)}
                  title="Include unrated"
                >
                  None
                </button>
              </div>
            </div>
            <div>
              <div className="text-[11px] text-muted mb-1">Exclude</div>
              <div className="flex flex-wrap gap-1">
                {STAR_VALUES.map((v) => {
                  const active = starsNotIn.includes(v)
                  return (
                    <button
                      key={`stars-out-${v}`}
                      className={`h-7 min-w-[32px] px-2 rounded border text-[11px] flex items-center justify-center transition-colors ${
                        active
                          ? 'bg-accent-muted text-star-active border-border'
                          : 'bg-surface text-text border-border/70 hover:bg-surface-hover'
                      }`}
                      onClick={() => toggleStar('exclude', v)}
                      aria-pressed={active}
                      title={`Exclude ${v} star${v > 1 ? 's' : ''}`}
                    >
                      {v}★
                    </button>
                  )
                })}
                <button
                  className={`h-7 min-w-[48px] px-2 rounded border text-[11px] flex items-center justify-center transition-colors ${
                    starsNotIn.includes(0)
                      ? 'bg-accent-muted text-star-active border-border'
                      : 'bg-surface text-text border-border/70 hover:bg-surface-hover'
                  }`}
                  onClick={() => toggleStar('exclude', 0)}
                  aria-pressed={starsNotIn.includes(0)}
                  title="Exclude unrated"
                >
                  None
                </button>
              </div>
            </div>
          </div>
        </div>

        <div>
          <div className="text-xs uppercase tracking-wide text-muted mb-2">Filename</div>
          <div className="grid grid-cols-1 gap-2">
            <div>
              <label className="block text-[11px] text-muted mb-1">Contains</label>
              <input
                className="h-8 w-full rounded-lg px-2.5 border border-border bg-surface text-text"
                value={nameContains}
                placeholder="e.g. draft"
                onChange={(e) => onChangeFilters(setNameContainsFilter(filters, e.target.value))}
              />
            </div>
            <div>
              <label className="block text-[11px] text-muted mb-1">Does not contain</label>
              <input
                className="h-8 w-full rounded-lg px-2.5 border border-border bg-surface text-text"
                value={nameNotContains}
                placeholder="e.g. v1"
                onChange={(e) => onChangeFilters(setNameNotContainsFilter(filters, e.target.value))}
              />
            </div>
          </div>
        </div>

        <div>
          <div className="text-xs uppercase tracking-wide text-muted mb-2">Comments</div>
          <div className="grid grid-cols-1 gap-2">
            <div>
              <label className="block text-[11px] text-muted mb-1">Contains</label>
              <input
                className="h-8 w-full rounded-lg px-2.5 border border-border bg-surface text-text"
                value={commentsContains}
                placeholder="e.g. hero"
                onChange={(e) => onChangeFilters(setCommentsContainsFilter(filters, e.target.value))}
              />
            </div>
            <div>
              <label className="block text-[11px] text-muted mb-1">Does not contain</label>
              <input
                className="h-8 w-full rounded-lg px-2.5 border border-border bg-surface text-text"
                value={commentsNotContains}
                placeholder="e.g. todo"
                onChange={(e) => onChangeFilters(setCommentsNotContainsFilter(filters, e.target.value))}
              />
            </div>
          </div>
        </div>

        <div>
          <div className="text-xs uppercase tracking-wide text-muted mb-2">URL</div>
          <div className="grid grid-cols-1 gap-2">
            <div>
              <label className="block text-[11px] text-muted mb-1">Contains</label>
              <input
                className="h-8 w-full rounded-lg px-2.5 border border-border bg-surface text-text"
                value={urlContains}
                placeholder="e.g. s3://bucket"
                onChange={(e) => onChangeFilters(setUrlContainsFilter(filters, e.target.value))}
              />
            </div>
            <div>
              <label className="block text-[11px] text-muted mb-1">Does not contain</label>
              <input
                className="h-8 w-full rounded-lg px-2.5 border border-border bg-surface text-text"
                value={urlNotContains}
                placeholder="e.g. http://"
                onChange={(e) => onChangeFilters(setUrlNotContainsFilter(filters, e.target.value))}
              />
            </div>
          </div>
        </div>

        <div>
          <div className="text-xs uppercase tracking-wide text-muted mb-2">Date Added</div>
          <div className="grid grid-cols-2 gap-2">
            <div>
              <label className="block text-[11px] text-muted mb-1">From</label>
              <input
                type="date"
                className="h-8 w-full rounded-lg px-2.5 border border-border bg-surface text-text"
                value={dateFromValue}
                onChange={(e) => onChangeFilters(setDateRangeFilter(filters, { from: e.target.value || null, to: dateRange.to ?? null }))}
              />
            </div>
            <div>
              <label className="block text-[11px] text-muted mb-1">To</label>
              <input
                type="date"
                className="h-8 w-full rounded-lg px-2.5 border border-border bg-surface text-text"
                value={dateToValue}
                onChange={(e) => onChangeFilters(setDateRangeFilter(filters, { from: dateRange.from ?? null, to: e.target.value || null }))}
              />
            </div>
          </div>
        </div>

        <div>
          <div className="text-xs uppercase tracking-wide text-muted mb-2">Dimensions</div>
          <div className="grid grid-cols-1 gap-2">
            <div>
              <label className="block text-[11px] text-muted mb-1">Width</label>
              <div className="flex gap-2">
                <select
                  className="h-8 w-16 rounded-lg px-1 border border-border bg-surface text-text"
                  value={widthOp}
                  onChange={(e) => {
                    const nextOp = e.target.value as CompareOp
                    setWidthOp(nextOp)
                    if (widthCompare) {
                      onChangeFilters(setWidthCompareFilter(filters, { op: nextOp, value: widthCompare.value }))
                    }
                  }}
                >
                  {COMPARE_OPS.map((op) => (
                    <option key={`w-${op}`} value={op}>{op}</option>
                  ))}
                </select>
                <input
                  type="number"
                  className="h-8 w-full rounded-lg px-2.5 border border-border bg-surface text-text"
                  value={widthCompare ? String(widthCompare.value) : ''}
                  min={0}
                  placeholder="px"
                  onChange={(e) => {
                    const raw = e.target.value
                    if (!raw) {
                      onChangeFilters(setWidthCompareFilter(filters, null))
                      return
                    }
                    const value = Number(raw)
                    if (!Number.isFinite(value)) return
                    onChangeFilters(setWidthCompareFilter(filters, { op: widthOp, value }))
                  }}
                />
              </div>
            </div>
            <div>
              <label className="block text-[11px] text-muted mb-1">Height</label>
              <div className="flex gap-2">
                <select
                  className="h-8 w-16 rounded-lg px-1 border border-border bg-surface text-text"
                  value={heightOp}
                  onChange={(e) => {
                    const nextOp = e.target.value as CompareOp
                    setHeightOp(nextOp)
                    if (heightCompare) {
                      onChangeFilters(setHeightCompareFilter(filters, { op: nextOp, value: heightCompare.value }))
                    }
                  }}
                >
                  {COMPARE_OPS.map((op) => (
                    <option key={`h-${op}`} value={op}>{op}</option>
                  ))}
                </select>
                <input
                  type="number"
                  className="h-8 w-full rounded-lg px-2.5 border border-border bg-surface text-text"
                  value={heightCompare ? String(heightCompare.value) : ''}
                  min={0}
                  placeholder="px"
                  onChange={(e) => {
                    const raw = e.target.value
                    if (!raw) {
                      onChangeFilters(setHeightCompareFilter(filters, null))
                      return
                    }
                    const value = Number(raw)
                    if (!Number.isFinite(value)) return
                    onChangeFilters(setHeightCompareFilter(filters, { op: heightOp, value }))
                  }}
                />
              </div>
            </div>
          </div>
        </div>
      </div>
    </div>
  )
}

function MetricRangePanel({
  items,
  filteredItems,
  metricKeys,
  selectedMetric,
  onSelectMetric,
  filters,
  onChangeRange,
}: MetricRangePanelProps) {
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

  return (
    <>
      <div>
        <label className="block text-xs uppercase tracking-wide text-muted mb-1">Metric</label>
        <select
          className="h-8 w-full rounded-lg px-2.5 border border-border bg-surface text-text"
          value={activeMetric}
          onChange={(e) => onSelectMetric(e.target.value)}
        >
          {metricKeys.map((key) => (
            <option key={key} value={key}>{key}</option>
          ))}
        </select>
      </div>

      {population ? (
        <div className="rounded-xl border border-border bg-panel p-3">
          <div className="flex items-center justify-between text-xs text-muted mb-2">
            <span>Population: {population.count}</span>
            <span>Filtered: {filtered?.count ?? 0}</span>
          </div>
          <svg
            ref={svgRef}
            viewBox={`0 0 ${BIN_COUNT} 100`}
            preserveAspectRatio="none"
            className="w-full h-28 cursor-crosshair rounded-md bg-surface-inset"
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
              className="btn btn-sm"
              onClick={() => activeMetric && onChangeRange(activeMetric, null)}
            >
              Clear
            </button>
          </div>
        </div>
      ) : (
        <div className="text-sm text-muted">No values found for this metric.</div>
      )}
    </>
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

function toDateInputValue(value?: string): string {
  if (!value) return ''
  if (value.length >= 10) return value.slice(0, 10)
  return value
}
