import React, { useEffect, useMemo, useState } from 'react'
import type { FilterAST, Item } from '../../../lib/types'
import { getMetricRangeFilter } from '../../browse/model/filters'
import { useMetricHistogramInteraction } from '../hooks/useMetricHistogramInteraction'
import {
  clamp,
  clamp01,
  collectMetricValues,
  computeHistogramFromValues,
  formatInputValue,
  formatNumber,
  isApprox,
  normalizeRange,
  parseNumberInput,
  type Range,
} from '../model/histogram'

export type { Range } from '../model/histogram'

export interface MetricHistogramCardProps {
  items: Item[]
  filteredItems: Item[]
  metricKey: string
  selectedItems?: Item[]
  filters: FilterAST
  onChangeRange: (key: string, range: Range | null) => void
  showTitle?: boolean
}

const BIN_COUNT = 40

export default function MetricHistogramCard({
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
  const domain = population ? { min: population.min, max: population.max } : null
  const {
    svgRef,
    hoverValue,
    displayRange,
    onPointerDown,
    onPointerMove,
    onPointerUp,
    onPointerLeave,
  } = useMetricHistogramInteraction({
    metricKey,
    domain,
    activeRange,
    onChangeRange: (range) => onChangeRange(metricKey, range),
  })
  const [minInput, setMinInput] = useState('')
  const [maxInput, setMaxInput] = useState('')
  const [editingField, setEditingField] = useState<'min' | 'max' | null>(null)

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
        onPointerLeave={onPointerLeave}
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
        <span>{formatNumber(domain.min)}</span>
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
        <span>{formatNumber(domain.max)}</span>
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
          className="btn btn-xs btn-ghost text-muted hover:text-text"
          onClick={() => onChangeRange(metricKey, null)}
        >
          Clear
        </button>
      </div>
    </div>
  )
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
