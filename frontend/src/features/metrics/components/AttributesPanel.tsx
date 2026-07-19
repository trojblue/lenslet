import React, { useCallback, useEffect, useMemo, useRef, useState } from 'react'
import type { FilterAST } from '../../../lib/types'
import {
  getDateRangeFilter,
  getHeightCompareFilter,
  getNameContainsFilter,
  getNameNotContainsFilter,
  getNotesContainsFilter,
  getNotesNotContainsFilter,
  getStarsInFilter,
  getStarsNotInFilter,
  getUrlContainsFilter,
  getUrlNotContainsFilter,
  getWidthCompareFilter,
  setDateRangeFilter,
  setHeightCompareFilter,
  setNameContainsFilter,
  setNameNotContainsFilter,
  setNotesContainsFilter,
  setNotesNotContainsFilter,
  setStarsInFilter,
  setStarsNotInFilter,
  setUrlContainsFilter,
  setUrlNotContainsFilter,
  setWidthCompareFilter,
} from '../../browse/model/filters'
import Dropdown from '../../../shared/ui/Dropdown'

type CompareOp = '<' | '<=' | '>' | '>='

interface AttributesPanelProps {
  filters: FilterAST
  onChangeFilters: (filters: FilterAST) => void
}

const STAR_VALUES = [5, 4, 3, 2, 1]
const COMPARE_OPS: CompareOp[] = ['<', '<=', '>', '>=']
const COMPARE_OPTIONS = COMPARE_OPS.map((op) => ({ value: op, label: op }))
const TEXT_COMMIT_DELAY_MS = 250

export default function AttributesPanel({ filters, onChangeFilters }: AttributesPanelProps) {
  const starsIn = useMemo(() => getStarsInFilter(filters), [filters])
  const starsNotIn = useMemo(() => getStarsNotInFilter(filters), [filters])
  const nameContains = useMemo(() => getNameContainsFilter(filters) ?? '', [filters])
  const nameNotContains = useMemo(() => getNameNotContainsFilter(filters) ?? '', [filters])
  const notesContains = useMemo(() => getNotesContainsFilter(filters) ?? '', [filters])
  const notesNotContains = useMemo(() => getNotesNotContainsFilter(filters) ?? '', [filters])
  const urlContains = useMemo(() => getUrlContainsFilter(filters) ?? '', [filters])
  const urlNotContains = useMemo(() => getUrlNotContainsFilter(filters) ?? '', [filters])
  const dateRange = useMemo(() => getDateRangeFilter(filters) ?? {}, [filters])
  const dateFromValue = useMemo(() => toDateInputValue(dateRange.from), [dateRange.from])
  const dateToValue = useMemo(() => toDateInputValue(dateRange.to), [dateRange.to])
  const widthCompare = useMemo(() => getWidthCompareFilter(filters), [filters])
  const heightCompare = useMemo(() => getHeightCompareFilter(filters), [filters])

  const widthIdentity = compareIdentity(widthCompare)
  const heightIdentity = compareIdentity(heightCompare)
  const [widthOpDraft, setWidthOpDraft] = useState<CompareOperatorDraft | null>(null)
  const [heightOpDraft, setHeightOpDraft] = useState<CompareOperatorDraft | null>(null)
  const widthOp = projectCompareOperator(widthCompare?.op, widthIdentity, widthOpDraft)
  const heightOp = projectCompareOperator(heightCompare?.op, heightIdentity, heightOpDraft)

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
    <div className="ui-card" data-attributes-card>
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
              <CommittedTextInput
                label="Filename contains"
                value={nameContains}
                placeholder="e.g. draft"
                onCommit={(value) => onChangeFilters(setNameContainsFilter(filters, value))}
              />
            </div>
            <div>
              <CommittedTextInput
                label="Filename does not contain"
                value={nameNotContains}
                placeholder="e.g. v1"
                onCommit={(value) => onChangeFilters(setNameNotContainsFilter(filters, value))}
              />
            </div>
          </div>
        </div>

        <div>
          <div className="ui-subsection-title mb-2">Notes</div>
          <div className="grid grid-cols-1 gap-2">
            <div>
              <CommittedTextInput
                label="Notes contain"
                value={notesContains}
                placeholder="e.g. hero"
                onCommit={(value) => onChangeFilters(setNotesContainsFilter(filters, value))}
              />
            </div>
            <div>
              <CommittedTextInput
                label="Notes do not contain"
                value={notesNotContains}
                placeholder="e.g. todo"
                onCommit={(value) => onChangeFilters(setNotesNotContainsFilter(filters, value))}
              />
            </div>
          </div>
        </div>

        <div>
          <div className="ui-subsection-title mb-2">URL</div>
          <div className="grid grid-cols-1 gap-2">
            <div>
              <CommittedTextInput
                label="URL contains"
                value={urlContains}
                placeholder="e.g. s3://bucket"
                onCommit={(value) => onChangeFilters(setUrlContainsFilter(filters, value))}
              />
            </div>
            <div>
              <CommittedTextInput
                label="URL does not contain"
                value={urlNotContains}
                placeholder="e.g. http://"
                onCommit={(value) => onChangeFilters(setUrlNotContainsFilter(filters, value))}
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
                <div className="w-16 shrink-0" data-dimension-operator="width">
                  <Dropdown
                    value={widthOp}
                    onChange={(value) => {
                      const nextOp = value as CompareOp
                      if (widthCompare) {
                        onChangeFilters(setWidthCompareFilter(filters, { op: nextOp, value: widthCompare.value }))
                        setWidthOpDraft(null)
                      } else {
                        setWidthOpDraft({ filterIdentity: widthIdentity, value: nextOp })
                      }
                    }}
                    options={COMPARE_OPTIONS}
                    aria-label="Width operator"
                    title={`Width ${widthOp}`}
                    triggerClassName="w-16 justify-between px-2"
                    width="trigger"
                  />
                </div>
                <input
                  type="number"
                  aria-label="Width pixels"
                  className="ui-input ui-number w-full"
                  value={widthCompare ? String(widthCompare.value) : ''}
                  min={0}
                  placeholder="px"
                  onChange={(e) => {
                    const raw = e.target.value
                    if (!raw) {
                      setWidthOpDraft(null)
                      onChangeFilters(setWidthCompareFilter(filters, null))
                      return
                    }
                    const value = Number(raw)
                    if (!Number.isFinite(value)) return
                    setWidthOpDraft(null)
                    onChangeFilters(setWidthCompareFilter(filters, { op: widthOp, value }))
                  }}
                />
              </div>
            </div>
            <div>
              <label className="ui-label">Height</label>
              <div className="flex gap-2">
                <div className="w-16 shrink-0" data-dimension-operator="height">
                  <Dropdown
                    value={heightOp}
                    onChange={(value) => {
                      const nextOp = value as CompareOp
                      if (heightCompare) {
                        onChangeFilters(setHeightCompareFilter(filters, { op: nextOp, value: heightCompare.value }))
                        setHeightOpDraft(null)
                      } else {
                        setHeightOpDraft({ filterIdentity: heightIdentity, value: nextOp })
                      }
                    }}
                    options={COMPARE_OPTIONS}
                    aria-label="Height operator"
                    title={`Height ${heightOp}`}
                    triggerClassName="w-16 justify-between px-2"
                    width="trigger"
                  />
                </div>
                <input
                  type="number"
                  aria-label="Height pixels"
                  className="ui-input ui-number w-full"
                  value={heightCompare ? String(heightCompare.value) : ''}
                  min={0}
                  placeholder="px"
                  onChange={(e) => {
                    const raw = e.target.value
                    if (!raw) {
                      setHeightOpDraft(null)
                      onChangeFilters(setHeightCompareFilter(filters, null))
                      return
                    }
                    const value = Number(raw)
                    if (!Number.isFinite(value)) return
                    setHeightOpDraft(null)
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

interface CommittedTextInputProps {
  label: string
  value: string
  placeholder: string
  onCommit: (value: string) => void
}

type CompareOperatorDraft = {
  filterIdentity: string
  value: CompareOp
}

function compareIdentity(compare: { op: CompareOp; value: number } | null): string {
  return compare ? `${compare.op}:${compare.value}` : 'none'
}

export function projectCompareOperator(
  committed: CompareOp | undefined,
  filterIdentity: string,
  draft: CompareOperatorDraft | null,
): CompareOp {
  return draft?.filterIdentity === filterIdentity ? draft.value : committed ?? '>='
}

export function commitTextDraft(
  activeDraft: string | null,
  value: string,
  onCommit: (value: string) => void,
): null {
  if (activeDraft !== null && activeDraft !== value) onCommit(activeDraft)
  return null
}

function CommittedTextInput({
  label,
  value,
  placeholder,
  onCommit,
}: CommittedTextInputProps): JSX.Element {
  const [activeDraft, setActiveDraft] = useState<string | null>(null)
  const onCommitRef = useRef(onCommit)
  onCommitRef.current = onCommit
  const displayedValue = activeDraft ?? value

  const commit = useCallback(() => {
    const nextDraft = commitTextDraft(activeDraft, value, onCommitRef.current)
    if (nextDraft !== activeDraft) setActiveDraft(nextDraft)
  }, [activeDraft, value])

  useEffect(() => {
    if (activeDraft === null || activeDraft === value) return
    return scheduleCommittedText(commit, TEXT_COMMIT_DELAY_MS)
  }, [activeDraft, commit, value])

  return (
    <label className="block">
      <span className="ui-label">{label.replace(/^(Filename|Notes|URL) /, '')}</span>
      <div className="flex gap-1">
        <input
          className="ui-input min-w-0 flex-1"
          aria-label={label}
          value={displayedValue}
          placeholder={placeholder}
          onChange={(event) => setActiveDraft(event.currentTarget.value)}
          onBlur={() => {
            commit()
            setActiveDraft(null)
          }}
          onKeyDown={(event) => {
            if (event.key !== 'Enter') return
            event.preventDefault()
            commit()
          }}
        />
        <button
          type="button"
          className="btn btn-sm btn-ghost px-2 text-[11px]"
          disabled={activeDraft === null || activeDraft === value}
          onClick={commit}
          aria-label={`Apply ${label}`}
        >
          Apply
        </button>
      </div>
    </label>
  )
}

export function scheduleCommittedText(
  commit: () => void,
  delayMs = TEXT_COMMIT_DELAY_MS,
): () => void {
  const timer = globalThis.setTimeout(commit, Math.max(0, delayMs))
  return () => globalThis.clearTimeout(timer)
}
