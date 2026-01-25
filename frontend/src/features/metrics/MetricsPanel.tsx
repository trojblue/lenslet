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
  selectedItems?: Item[]
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
  selectedItems?: Item[]
  selectedMetric?: string
  onSelectMetric: (key: string) => void
  filters: FilterAST
  onChangeRange: (key: string, range: Range | null) => void
}

interface SelectedMetricsPanelProps {
  selectedItems: Item[]
  metricKeys: string[]
}

const BIN_COUNT = 40
const MAX_SELECTED_METRICS = 12
const STAR_VALUES = [5, 4, 3, 2, 1]
const COMPARE_OPS: CompareOp[] = ['<', '<=', '>', '>=']

export default function MetricsPanel({
  items,
  filteredItems,
  metricKeys,
  selectedItems,
  selectedMetric,
  onSelectMetric,
  filters,
  onChangeRange,
  onChangeFilters,
}: MetricsPanelProps) {
  const metricsSummary = selectedItems && selectedItems.length
    ? (
      <SelectedMetricsPanel
        selectedItems={selectedItems}
        metricKeys={metricKeys}
      />
    )
    : null
  const attributesPanel = (
    <AttributesPanel
      filters={filters}
      onChangeFilters={onChangeFilters}
    />
  )

  if (!metricKeys.length) {
    return (
      <div className="h-full flex flex-col gap-3 p-3 overflow-auto scrollbar-thin">
        {metricsSummary}
        {attributesPanel}
        <div className="p-4 text-sm text-muted">
          No metrics found in this dataset.
        </div>
      </div>
    )
  }

  return (
    <div className="h-full flex flex-col gap-3 p-3 overflow-auto scrollbar-thin">
      {metricsSummary}
      <MetricRangePanel
        items={items}
        filteredItems={filteredItems}
        metricKeys={metricKeys}
        selectedItems={selectedItems}
        selectedMetric={selectedMetric}
        onSelectMetric={onSelectMetric}
        filters={filters}
        onChangeRange={onChangeRange}
      />
      {attributesPanel}
    </div>
  )
}

function SelectedMetricsPanel({ selectedItems, metricKeys }: SelectedMetricsPanelProps) {
  const summary = useMemo(() => {
    if (!selectedItems.length) return null
    const valuesByKey = new Map<string, number[]>()
    for (const it of selectedItems) {
      const metrics = it.metrics
      if (!metrics) continue
      for (const [key, raw] of Object.entries(metrics)) {
        if (raw == null || Number.isNaN(raw)) continue
        const existing = valuesByKey.get(key)
        if (existing) existing.push(raw)
        else valuesByKey.set(key, [raw])
      }
    }
    if (!valuesByKey.size) return null
    const keys = metricKeys.length
      ? metricKeys.filter((key) => valuesByKey.has(key))
      : Array.from(valuesByKey.keys()).sort()
    const entries = keys.map((key) => {
      const values = valuesByKey.get(key) ?? []
      const min = Math.min(...values)
      const max = Math.max(...values)
      const avg = values.reduce((sum, v) => sum + v, 0) / Math.max(1, values.length)
      return { key, value: values[0], min, max, avg, count: values.length }
    })
    return { entries, totalItems: selectedItems.length }
  }, [selectedItems, metricKeys])

  if (!summary) return null

  const { entries, totalItems } = summary
  const show = entries.slice(0, MAX_SELECTED_METRICS)
  const remaining = entries.length - show.length
  const isMulti = totalItems > 1

  return (
    <div className="ui-card">
      <div className="ui-card-header">
        <div className="ui-section-title">Selected metrics</div>
        <div className="text-[11px] text-muted">{totalItems} item{totalItems === 1 ? '' : 's'}</div>
      </div>
      <div className="space-y-1 text-[12px]">
        {show.map((entry) => (
          <div key={entry.key} className="flex items-center justify-between gap-2">
            <span className="text-muted w-28 shrink-0 truncate" title={entry.key}>{entry.key}</span>
            <span className="font-mono text-text text-right tabular-nums">
              {isMulti ? `${formatNumber(entry.min)} – ${formatNumber(entry.max)}` : formatNumber(entry.value)}
              {isMulti && (
                <span className="text-[11px] text-muted ml-2">
                  avg {formatNumber(entry.avg)}
                  {entry.count !== totalItems ? ` · ${entry.count}/${totalItems}` : ''}
                </span>
              )}
            </span>
          </div>
        ))}
        {remaining > 0 && (
          <div className="text-[11px] text-muted">+{remaining} more</div>
        )}
      </div>
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
    <div className="ui-card">
      <div className="ui-section-title mb-3">Attributes</div>
      <div className="space-y-3">
        <div>
          <div className="ui-subsection-title mb-2">Rating</div>
          <div className="space-y-2">
            <div>
              <div className="ui-label">Include</div>
              <div className="flex flex-wrap gap-1">
                {STAR_VALUES.map((v) => {
                  const active = starsIn.includes(v)
                  return (
                    <button
                      key={`stars-in-${v}`}
                      className={`h-7 min-w-[32px] px-2 rounded-lg border text-[11px] flex items-center justify-center transition-colors ${
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
                  className={`h-7 min-w-[48px] px-2 rounded-lg border text-[11px] flex items-center justify-center transition-colors ${
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
              <div className="ui-label">Exclude</div>
              <div className="flex flex-wrap gap-1">
                {STAR_VALUES.map((v) => {
                  const active = starsNotIn.includes(v)
                  return (
                    <button
                      key={`stars-out-${v}`}
                      className={`h-7 min-w-[32px] px-2 rounded-lg border text-[11px] flex items-center justify-center transition-colors ${
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
                  className={`h-7 min-w-[48px] px-2 rounded-lg border text-[11px] flex items-center justify-center transition-colors ${
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
          <div className="ui-subsection-title mb-2">Filename</div>
          <div className="grid grid-cols-1 gap-2">
            <div>
              <label className="ui-label">Contains</label>
              <input
                className="ui-input w-full"
                value={nameContains}
                placeholder="e.g. draft"
                onChange={(e) => onChangeFilters(setNameContainsFilter(filters, e.target.value))}
              />
            </div>
            <div>
              <label className="ui-label">Does not contain</label>
              <input
                className="ui-input w-full"
                value={nameNotContains}
                placeholder="e.g. v1"
                onChange={(e) => onChangeFilters(setNameNotContainsFilter(filters, e.target.value))}
              />
            </div>
          </div>
        </div>

        <div>
          <div className="ui-subsection-title mb-2">Comments</div>
          <div className="grid grid-cols-1 gap-2">
            <div>
              <label className="ui-label">Contains</label>
              <input
                className="ui-input w-full"
                value={commentsContains}
                placeholder="e.g. hero"
                onChange={(e) => onChangeFilters(setCommentsContainsFilter(filters, e.target.value))}
              />
            </div>
            <div>
              <label className="ui-label">Does not contain</label>
              <input
                className="ui-input w-full"
                value={commentsNotContains}
                placeholder="e.g. todo"
                onChange={(e) => onChangeFilters(setCommentsNotContainsFilter(filters, e.target.value))}
              />
            </div>
          </div>
        </div>

        <div>
          <div className="ui-subsection-title mb-2">URL</div>
          <div className="grid grid-cols-1 gap-2">
            <div>
              <label className="ui-label">Contains</label>
              <input
                className="ui-input w-full"
                value={urlContains}
                placeholder="e.g. s3://bucket"
                onChange={(e) => onChangeFilters(setUrlContainsFilter(filters, e.target.value))}
              />
            </div>
            <div>
              <label className="ui-label">Does not contain</label>
              <input
                className="ui-input w-full"
                value={urlNotContains}
                placeholder="e.g. http://"
                onChange={(e) => onChangeFilters(setUrlNotContainsFilter(filters, e.target.value))}
              />
            </div>
          </div>
        </div>

        <div>
          <div className="ui-subsection-title mb-2">Date Added</div>
          <div className="grid grid-cols-2 gap-2">
            <div>
              <label className="ui-label">From</label>
              <input
                type="date"
                className="ui-input w-full"
                value={dateFromValue}
                onChange={(e) => onChangeFilters(setDateRangeFilter(filters, { from: e.target.value || null, to: dateRange.to ?? null }))}
              />
            </div>
            <div>
              <label className="ui-label">To</label>
              <input
                type="date"
                className="ui-input w-full"
                value={dateToValue}
                onChange={(e) => onChangeFilters(setDateRangeFilter(filters, { from: dateRange.from ?? null, to: e.target.value || null }))}
              />
            </div>
          </div>
        </div>

        <div>
          <div className="ui-subsection-title mb-2">Dimensions</div>
          <div className="grid grid-cols-1 gap-2">
            <div>
              <label className="ui-label">Width</label>
              <div className="flex gap-2">
                <select
                  className="ui-select ui-select-compact w-16"
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
                  className="ui-input ui-number w-full"
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
              <label className="ui-label">Height</label>
              <div className="flex gap-2">
                <select
                  className="ui-select ui-select-compact w-16"
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
                  className="ui-input ui-number w-full"
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
  selectedItems,
  selectedMetric,
  onSelectMetric,
  filters,
  onChangeRange,
}: MetricRangePanelProps) {
  const [showAll, setShowAll] = useState(false)
  const activeMetric = selectedMetric && metricKeys.includes(selectedMetric) ? selectedMetric : metricKeys[0]

  return (
    <>
      <div>
        <div className="flex items-center justify-between gap-2">
          <label className="ui-label">Metric</label>
          <button
            className="btn btn-sm btn-ghost text-[11px]"
            onClick={() => setShowAll((v) => !v)}
            aria-pressed={showAll}
          >
            {showAll ? 'Show one' : 'Show all'}
          </button>
        </div>
        {showAll ? (
          <div className="ui-input ui-input-readonly w-full flex items-center text-xs">
            All metrics
          </div>
        ) : (
          <select
            className="ui-select w-full"
            value={activeMetric}
            onChange={(e) => onSelectMetric(e.target.value)}
          >
            {metricKeys.map((key) => (
              <option key={key} value={key}>{key}</option>
            ))}
          </select>
        )}
      </div>

      {showAll ? (
        <div className="space-y-3">
          {metricKeys.map((key) => (
            <MetricHistogramCard
              key={key}
              metricKey={key}
              items={items}
              filteredItems={filteredItems}
              selectedItems={selectedItems}
              filters={filters}
              onChangeRange={onChangeRange}
              showTitle
            />
          ))}
        </div>
      ) : (
        activeMetric ? (
          <MetricHistogramCard
            metricKey={activeMetric}
            items={items}
            filteredItems={filteredItems}
            selectedItems={selectedItems}
            filters={filters}
            onChangeRange={onChangeRange}
          />
        ) : (
          <div className="text-sm text-muted">No values found for this metric.</div>
        )
      )}
    </>
  )
}

interface MetricHistogramCardProps {
  items: Item[]
  filteredItems: Item[]
  metricKey: string
  selectedItems?: Item[]
  filters: FilterAST
  onChangeRange: (key: string, range: Range | null) => void
  showTitle?: boolean
}

function MetricHistogramCard({
  items,
  filteredItems,
  metricKey,
  selectedItems,
  filters,
  onChangeRange,
  showTitle = false,
}: MetricHistogramCardProps) {
  const populationValues = useMemo(() => collectMetricValues(items, metricKey), [items, metricKey])
  const population = useMemo(() => (
    computeHistogramFromValues(populationValues, BIN_COUNT)
  ), [populationValues])
  const filteredValues = useMemo(() => collectMetricValues(filteredItems, metricKey), [filteredItems, metricKey])
  const filtered = useMemo(() => (
    population ? computeHistogramFromValues(filteredValues, BIN_COUNT, population) : null
  ), [filteredValues, population])

  const activeRange = getMetricRangeFilter(filters, metricKey)
  const [dragRange, setDragRange] = useState<Range | null>(null)
  const [dragging, setDragging] = useState(false)
  const dragStartRef = useRef<number | null>(null)
  const svgRef = useRef<SVGSVGElement | null>(null)
  const [hoverValue, setHoverValue] = useState<number | null>(null)
  const [minInput, setMinInput] = useState('')
  const [maxInput, setMaxInput] = useState('')
  const [editingField, setEditingField] = useState<'min' | 'max' | null>(null)

  const displayRange = dragRange ?? activeRange
  const domain = population ? { min: population.min, max: population.max } : null
  const selectedValues = useMemo(() => {
    if (!selectedItems?.length) return []
    const values: number[] = []
    for (const it of selectedItems) {
      const raw = it.metrics?.[metricKey]
      if (raw == null || Number.isNaN(raw)) continue
      values.push(raw)
    }
    return values
  }, [selectedItems, metricKey])
  const selectedValue = selectedValues.length === 1 ? selectedValues[0] : null
  const selectedHistogram = useMemo(() => {
    if (!population || selectedValues.length < 2) return null
    return computeHistogramFromValues(selectedValues, BIN_COUNT, population)
  }, [selectedValues, population])

  useEffect(() => {
    if (!activeRange || !domain) {
      if (editingField !== 'min') setMinInput(activeRange ? formatInputValue(activeRange.min) : '')
      if (editingField !== 'max') setMaxInput(activeRange ? formatInputValue(activeRange.max) : '')
      return
    }
    if (editingField !== 'min') {
      const nextMin = isApprox(activeRange.min, domain.min) ? '' : formatInputValue(activeRange.min)
      setMinInput(nextMin)
    }
    if (editingField !== 'max') {
      const nextMax = isApprox(activeRange.max, domain.max) ? '' : formatInputValue(activeRange.max)
      setMaxInput(nextMax)
    }
  }, [activeRange, domain, editingField])

  useEffect(() => {
    setHoverValue(null)
  }, [metricKey, domain?.min, domain?.max])

  const getValueFromHistogramEvent = (e: React.PointerEvent<SVGSVGElement>): number | null => {
    if (!domain) return null
    const rect = svgRef.current?.getBoundingClientRect()
    if (!rect) return null
    const t = clamp01((e.clientX - rect.left) / rect.width)
    return domain.min + (domain.max - domain.min) * t
  }

  const setRangeFromValue = (value: number, commit: boolean) => {
    if (!domain) return
    const start = dragStartRef.current ?? value
    const next = normalizeRange(start, value)
    setDragRange(next)
    if (commit) {
      onChangeRange(metricKey, next)
    }
  }

  const onPointerDown = (e: React.PointerEvent<SVGSVGElement>) => {
    if (!domain) return
    e.preventDefault()
    const value = getValueFromHistogramEvent(e)
    if (value == null) return
    setDragging(true)
    setDragRange(null)
    dragStartRef.current = value
    setHoverValue(value)
    svgRef.current?.setPointerCapture(e.pointerId)
    setRangeFromValue(value, false)
  }

  const onPointerMove = (e: React.PointerEvent<SVGSVGElement>) => {
    const value = getValueFromHistogramEvent(e)
    if (value == null) {
      if (!dragging) setHoverValue(null)
      return
    }
    setHoverValue(value)
    if (dragging) setRangeFromValue(value, false)
  }

  const onPointerUp = (e: React.PointerEvent<SVGSVGElement>) => {
    if (!dragging) return
    setDragging(false)
    svgRef.current?.releasePointerCapture(e.pointerId)
    const value = getValueFromHistogramEvent(e)
    if (value != null) {
      setHoverValue(value)
      setRangeFromValue(value, true)
    }
    dragStartRef.current = null
    setTimeout(() => setDragRange(null), 0)
  }

  const commitInputRange = (nextMinRaw: string, nextMaxRaw: string) => {
    if (!domain) return
    const minParsed = parseNumberInput(nextMinRaw)
    const maxParsed = parseNumberInput(nextMaxRaw)
    if (!minParsed.valid || !maxParsed.valid) {
      if (!minParsed.valid) {
        setMinInput(activeRange ? formatInputValue(activeRange.min) : '')
      }
      if (!maxParsed.valid) {
        setMaxInput(activeRange ? formatInputValue(activeRange.max) : '')
      }
      return
    }
    if (minParsed.value == null && maxParsed.value == null) {
      onChangeRange(metricKey, null)
      return
    }
    const minValue = minParsed.value ?? domain.min
    const maxValue = maxParsed.value ?? domain.max
    const clampedMin = clamp(minValue, domain.min, domain.max)
    const clampedMax = clamp(maxValue, domain.min, domain.max)
    const next = normalizeRange(clampedMin, clampedMax)
    if (isApprox(next.min, domain.min) && isApprox(next.max, domain.max)) {
      onChangeRange(metricKey, null)
      return
    }
    onChangeRange(metricKey, next)
  }

  if (!population || !domain) {
    return (
      <div className="ui-card">
        {showTitle && (
          <div className="ui-section-title mb-2">{metricKey}</div>
        )}
        <div className="text-sm text-muted">No values found for this metric.</div>
      </div>
    )
  }

  const selectedCount = selectedValues.length
  return (
    <div className="ui-card">
      {showTitle && (
        <div className="ui-section-title mb-2">{metricKey}</div>
      )}
      <div className="flex items-center justify-between text-[11px] text-muted mb-2 tabular-nums">
        <div className="flex items-center gap-3">
          <span>Population: {population.count}</span>
          <span>Filtered: {filtered?.count ?? 0}</span>
          {selectedCount > 1 && <span className="text-text">Selected: {selectedCount}</span>}
        </div>
        {selectedValue != null && (
          <span className="text-text">Selected: {formatNumber(selectedValue)}</span>
        )}
      </div>
      <svg
        ref={svgRef}
        viewBox={`0 0 ${BIN_COUNT} 100`}
        preserveAspectRatio="none"
        className="w-full h-28 cursor-crosshair rounded-md bg-surface-inset"
        onPointerDown={onPointerDown}
        onPointerMove={onPointerMove}
        onPointerUp={onPointerUp}
        onPointerLeave={() => setHoverValue(null)}
      >
        {renderBars(population.bins, '#2e3a4b')}
        {filtered && renderBars(filtered.bins, '#3a8fff')}
        {selectedHistogram && renderBars(selectedHistogram.bins, '#f59e0b', { opacity: 0.55 })}
        {displayRange && renderRange(displayRange, domain)}
        {selectedValue != null && renderValueMarker(selectedValue, domain, {
          color: 'var(--highlight)',
          strokeWidth: 0.7,
        })}
        {hoverValue != null && renderValueMarker(hoverValue, domain, {
          color: 'rgba(255,255,255,0.75)',
          strokeWidth: 0.5,
          dashed: true,
        })}
      </svg>
      <div className="flex items-center justify-between text-[11px] text-muted mt-2 tabular-nums">
        <span>{formatNumber(domain?.min)}</span>
        <div className="flex flex-col items-center text-center leading-tight">
          {displayRange ? (
            <span className="text-text">
              {isApprox(displayRange.min, domain.min)
                ? `≤ ${formatNumber(displayRange.max)}`
                : isApprox(displayRange.max, domain.max)
                  ? `≥ ${formatNumber(displayRange.min)}`
                  : `${formatNumber(displayRange.min)} – ${formatNumber(displayRange.max)}`}
            </span>
          ) : hoverValue != null ? (
            <span className="text-text">Cursor: {formatNumber(hoverValue)}</span>
          ) : (
            <span>Drag to filter</span>
          )}
          {displayRange && hoverValue != null && (
            <span className="text-[11px] text-muted">Cursor: {formatNumber(hoverValue)}</span>
          )}
        </div>
        <span>{formatNumber(domain?.max)}</span>
      </div>
      <div className="grid grid-cols-[1fr_1fr_auto] gap-2 mt-3 items-end">
        <div>
          <label className="ui-label">Min</label>
          <input
            type="number"
            step="any"
            className="ui-input ui-number w-full"
            value={minInput}
            placeholder={formatInputValue(domain.min)}
            onFocus={() => setEditingField('min')}
            onBlur={() => {
              setEditingField(null)
              commitInputRange(minInput, maxInput)
            }}
            onChange={(e) => setMinInput(e.target.value)}
            onKeyDown={(e) => {
              if (e.key === 'Enter') {
                e.currentTarget.blur()
              }
            }}
          />
        </div>
        <div>
          <label className="ui-label">Max</label>
          <input
            type="number"
            step="any"
            className="ui-input ui-number w-full"
            value={maxInput}
            placeholder={formatInputValue(domain.max)}
            onFocus={() => setEditingField('max')}
            onBlur={() => {
              setEditingField(null)
              commitInputRange(minInput, maxInput)
            }}
            onChange={(e) => setMaxInput(e.target.value)}
            onKeyDown={(e) => {
              if (e.key === 'Enter') {
                e.currentTarget.blur()
              }
            }}
          />
        </div>
        <button
          className="btn btn-sm btn-ghost h-8"
          onClick={() => onChangeRange(metricKey, null)}
        >
          Clear
        </button>
      </div>
    </div>
  )
}

function computeHistogramFromValues(values: number[], bins: number, base?: Histogram): Histogram | null {
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

function collectMetricValues(items: Item[], key: string): number[] {
  const values: number[] = []
  for (const it of items) {
    const val = it.metrics?.[key]
    if (val == null || Number.isNaN(val)) continue
    values.push(val)
  }
  return values
}

function renderBars(bins: number[], color: string, options?: { opacity?: number }) {
  const max = Math.max(1, ...bins)
  const opacity = options?.opacity ?? 0.9
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
        opacity={opacity}
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


function renderValueMarker(
  value: number,
  domain: { min: number; max: number },
  options: { color: string; strokeWidth?: number; dashed?: boolean }
) {
  const t = clamp01((value - domain.min) / (domain.max - domain.min))
  const x = BIN_COUNT * t
  return (
    <line
      x1={x}
      y1={0}
      x2={x}
      y2={100}
      stroke={options.color}
      strokeWidth={options.strokeWidth ?? 0.5}
      strokeDasharray={options.dashed ? '1.2 1.2' : undefined}
      opacity={0.95}
      vectorEffect="non-scaling-stroke"
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

function formatInputValue(value: number): string {
  if (!Number.isFinite(value)) return ''
  const trimmed = value.toString()
  return trimmed.includes('e') ? value.toFixed(6) : trimmed
}

function parseNumberInput(raw: string): { value: number | null; valid: boolean } {
  const trimmed = raw.trim()
  if (!trimmed) return { value: null, valid: true }
  const parsed = Number(trimmed)
  if (!Number.isFinite(parsed)) return { value: null, valid: false }
  return { value: parsed, valid: true }
}

function clamp(value: number, min: number, max: number): number {
  if (value < min) return min
  if (value > max) return max
  return value
}

function isApprox(a: number, b: number): boolean {
  const scale = Math.max(1, Math.abs(a), Math.abs(b))
  return Math.abs(a - b) <= 1e-6 * scale
}

function toDateInputValue(value?: string): string {
  if (!value) return ''
  if (value.length >= 10) return value.slice(0, 10)
  return value
}
