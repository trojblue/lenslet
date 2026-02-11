import React, { useEffect, useMemo, useState } from 'react'
import type { FilterAST } from '../../../lib/types'
import {
  getCommentsContainsFilter,
  getCommentsNotContainsFilter,
  getDateRangeFilter,
  getHeightCompareFilter,
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
} from '../../browse/model/filters'

type CompareOp = '<' | '<=' | '>' | '>='

interface AttributesPanelProps {
  filters: FilterAST
  onChangeFilters: (filters: FilterAST) => void
}

const STAR_VALUES = [5, 4, 3, 2, 1]
const COMPARE_OPS: CompareOp[] = ['<', '<=', '>', '>=']

export default function AttributesPanel({ filters, onChangeFilters }: AttributesPanelProps) {
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

function toDateInputValue(value?: string): string {
  if (!value) return ''
  if (value.length >= 10) return value.slice(0, 10)
  return value
}
