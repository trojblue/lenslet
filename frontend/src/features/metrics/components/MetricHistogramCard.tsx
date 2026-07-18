import React, { useEffect, useMemo, useState } from 'react'
import type { FilterAST } from '../../../lib/types'
import { getMetricRangeFilter } from '../../browse/model/filters'
import { useMetricHistogramInteraction } from '../hooks/useMetricHistogramInteraction'
import {
  clamp,
  clamp01,
  computeHistogramFromValues,
  formatInputValue,
  formatNumber,
  histogramBarHeights,
  isApprox,
  normalizeRange,
  parseNumberInput,
  type Range,
} from '../model/histogram'
import type { FacetFieldState } from '../model/facetPresentation'

export type { Range } from '../model/histogram'

export interface MetricHistogramCardProps {
  metricKey: string
  metricLabel?: string
  populationValues: number[]
  filteredValues: number[]
  populationHistogram?: ReturnType<typeof computeHistogramFromValues>
  selectedValues?: number[]
  filters: FilterAST
  onChangeRange: (key: string, range: Range | null) => void
  showTitle?: boolean
  showFilteredCounts?: boolean
  state?: FacetFieldState
  embedded?: boolean
}

const BIN_COUNT = 40

export default function MetricHistogramCard({
  metricKey,
  metricLabel,
  populationValues,
  filteredValues,
  populationHistogram,
  selectedValues = [],
  filters,
  onChangeRange,
  showTitle = false,
  showFilteredCounts = true,
  state = 'ready',
  embedded = false,
}: MetricHistogramCardProps) {
  const population = useMemo(() => (
    populationHistogram ?? computeHistogramFromValues(populationValues, BIN_COUNT)
  ), [populationHistogram, populationValues])
  const filtered = useMemo(() => (
    showFilteredCounts && population ? computeHistogramFromValues(filteredValues, BIN_COUNT, population) : null
  ), [filteredValues, population, showFilteredCounts])

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
  const selectedValue = selectedValues.length === 1 ? selectedValues[0] : null
  const displayLabel = metricLabel ?? metricKey
  const selectedHistogram = useMemo(() => {
    if (!population || selectedValues.length < 2) return null
    return computeHistogramFromValues(selectedValues, BIN_COUNT, population)
  }, [selectedValues, population])
  const displayState = population && domain ? 'ready' : state === 'ready' ? 'empty' : state

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

  const selectedCount = selectedValues.length
  const populationMaxBin = population ? Math.max(1, ...population.bins) : 1
  const footerInfo = domain
    ? histogramFooterInfo(displayRange, domain, hoverValue)
    : { text: '', emphasized: false }
  const selectionText = selectedValues.length === 1
    ? `Selected: ${formatNumber(selectedValues[0])}`
    : `Selected: ${selectedValues.length}`
  return (
    <div
      className={embedded ? 'flex h-full flex-col' : 'ui-card flex h-96 flex-col'}
      data-metric-histogram-card={metricKey}
      data-facet-state={displayState}
    >
      {showTitle && (
        <div className="ui-section-title mb-2">{displayLabel}</div>
      )}
      <div className="flex h-4 shrink-0 items-center justify-between gap-2 text-[11px] text-muted mb-2 tabular-nums whitespace-nowrap">
        <div className="flex min-w-0 items-center gap-2 overflow-hidden">
          <span>Population: {displayState === 'ready' ? population?.count : '—'}</span>
          {showFilteredCounts && <span>Filtered: {displayState === 'ready' ? filtered?.count ?? 0 : '—'}</span>}
        </div>
        <span
          className={`w-28 shrink-0 truncate text-right text-text ${selectedCount > 0 ? '' : 'invisible'}`}
          title={selectedCount > 0 ? selectionText : undefined}
          aria-hidden={selectedCount > 0 ? undefined : true}
        >
          {selectedCount > 0 ? selectionText : 'Selected: 0'}
        </span>
      </div>
      {displayState === 'ready' && population && domain ? (
        <svg
          ref={svgRef}
          viewBox={`0 0 ${BIN_COUNT} 100`}
          preserveAspectRatio="none"
          className="w-full h-28 shrink-0 cursor-crosshair rounded-md bg-surface-inset"
          onPointerDown={onPointerDown}
          onPointerMove={onPointerMove}
          onPointerUp={onPointerUp}
          onPointerLeave={onPointerLeave}
        >
          {renderBars(population.bins, '#2e3a4b', { scaleMax: populationMaxBin })}
          {showFilteredCounts && filtered && renderBars(filtered.bins, '#3a8fff', { scaleMax: populationMaxBin })}
          {selectedHistogram && renderBars(selectedHistogram.bins, '#f59e0b', {
            opacity: 0.55,
            scaleMax: populationMaxBin,
          })}
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
      ) : (
        <div className="flex h-28 shrink-0 items-center justify-center rounded-md bg-surface-inset px-3 text-center text-sm text-muted" role="status">
          {displayState === 'pending'
            ? 'Loading values for this metric…'
            : displayState === 'error'
              ? 'Could not load values for this metric.'
              : 'No values found for this metric.'}
        </div>
      )}
      <div
        className="flex h-4 items-center justify-between gap-2 text-[11px] text-muted mt-2 tabular-nums whitespace-nowrap"
        data-histogram-footer
      >
        <span className="w-12 shrink-0">{domain ? formatNumber(domain.min) : ''}</span>
        <span
          className={`min-w-0 flex-1 truncate text-center ${footerInfo.emphasized ? 'text-text' : ''}`}
          title={footerInfo.text}
          aria-label={footerInfo.text}
        >
          {footerInfo.text}
        </span>
        <span className="w-12 shrink-0 text-right">{domain ? formatNumber(domain.max) : ''}</span>
      </div>
      <div className="grid grid-cols-2 gap-2 mt-auto items-end">
        <div>
          <label className="ui-label">Min</label>
          <input
            type="number"
            step="any"
            className="ui-input ui-number w-full"
            value={minInput}
            placeholder={domain ? formatInputValue(domain.min) : ''}
            disabled={!domain}
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
            placeholder={domain ? formatInputValue(domain.max) : ''}
            disabled={!domain}
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
          className={`btn btn-xs btn-ghost text-muted hover:text-text col-span-2 justify-self-start ${activeRange ? '' : 'invisible'}`}
          onClick={() => onChangeRange(metricKey, null)}
          disabled={!activeRange}
          aria-hidden={!activeRange}
          data-card-action="clear"
        >
          Clear
        </button>
      </div>
    </div>
  )
}

function histogramFooterInfo(
  displayRange: Range | null,
  domain: { min: number; max: number },
  hoverValue: number | null,
): { text: string; emphasized: boolean } {
  if (!displayRange) {
    return hoverValue == null
      ? { text: 'Drag to filter', emphasized: false }
      : { text: `Cursor: ${formatNumber(hoverValue)}`, emphasized: true }
  }
  const rangeText = isApprox(displayRange.min, domain.min)
    ? `≤ ${formatNumber(displayRange.max)}`
    : isApprox(displayRange.max, domain.max)
      ? `≥ ${formatNumber(displayRange.min)}`
      : `${formatNumber(displayRange.min)} – ${formatNumber(displayRange.max)}`
  return {
    text: hoverValue == null ? rangeText : `${rangeText} · Cursor: ${formatNumber(hoverValue)}`,
    emphasized: true,
  }
}

function renderBars(
  bins: number[],
  color: string,
  options: { opacity?: number; scaleMax: number },
) {
  const opacity = options.opacity ?? 0.9
  const heights = histogramBarHeights(bins, options.scaleMax)
  return heights.map((height, i) => {
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
