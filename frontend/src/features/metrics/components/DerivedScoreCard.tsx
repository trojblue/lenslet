import { Plus, Sigma, Trash2 } from 'lucide-react'
import React, { useEffect, useMemo, useState } from 'react'
import type {
  BrowseFacetsPayload,
  BrowseItemPayload,
  DerivedMetricSpec,
  MetricDisplayNames,
} from '../../../lib/types'
import { getMetricDisplayName } from '../../../lib/metricDisplay'
import {
  isDerivedMetricKey,
  type DerivedMetricEvaluation,
} from '../model/derivedMetric'
import {
  applyDerivedMetricFormulaCode,
  buildDerivedMetricFormulaCode,
  buildDerivedMetricFormulaPreview,
  buildDerivedMetricSpecFromDraft,
  collectCategoricalValuesByKey,
  createCategoricalDraftTerm,
  createDerivedMetricDraft,
  createNumericDraftTerm,
  evaluateDerivedMetricDraft,
  type DerivedMetricFormulaDiagnostics,
  type DerivedMetricCategoricalDraftTerm,
  type DerivedMetricDraft,
  type DerivedMetricNumericDraftTerm,
} from '../model/derivedMetricDraft'
import { computeHistogramFromValues, type Histogram } from '../model/histogram'
import {
  collectMetricValuesByKey,
  getMetricValues,
  metricHistogramFromFacet,
} from '../model/metricValues'
import Dropdown from '../../../shared/ui/Dropdown'
import DerivedMetricMiniHistogram from './DerivedMetricMiniHistogram'

interface DerivedScoreCardProps {
  items: BrowseItemPayload[]
  metricKeys: string[]
  categoricalKeys: string[]
  metricDisplayNames?: MetricDisplayNames | null
  facets?: BrowseFacetsPayload | null
  categoricalValuesByKey?: Map<string, string[]>
  derivedMetric: DerivedMetricEvaluation
  rankDisabledReason?: string | null
  onApplyDerivedMetric: (spec: DerivedMetricSpec | null) => void
  onRankByDerivedMetric: (spec: DerivedMetricSpec) => void
}

export default function DerivedScoreCard({
  items,
  metricKeys,
  categoricalKeys,
  metricDisplayNames,
  facets = null,
  categoricalValuesByKey: categoricalValuesByKeyOverride,
  derivedMetric,
  rankDisabledReason = null,
  onApplyDerivedMetric,
  onRankByDerivedMetric,
}: DerivedScoreCardProps): JSX.Element {
  const sourceMetricKeys = useMemo(
    () => metricKeys.filter((key) => !isDerivedMetricKey(key)),
    [metricKeys],
  )
  const categoricalValuesByKey = useMemo(
    () => categoricalValuesByKeyOverride ?? collectCategoricalValuesByKey(items, categoricalKeys),
    [categoricalKeys, categoricalValuesByKeyOverride, items],
  )
  const [draft, setDraft] = useState<DerivedMetricDraft>(() => (
    createDerivedMetricDraft(derivedMetric.spec, sourceMetricKeys)
  ))
  const [formulaCode, setFormulaCode] = useState(() => buildDerivedMetricFormulaCode(draft))
  const [formulaDirty, setFormulaDirty] = useState(false)
  const [formulaDiagnostics, setFormulaDiagnostics] = useState<DerivedMetricFormulaDiagnostics | null>(null)
  const numericMetricOptions = useMemo(() => [
    { value: '', label: 'Metric', keywords: ['metric'] },
    ...sourceMetricKeys.map((key) => ({
      value: key,
      label: getMetricDisplayName(key, metricDisplayNames),
      keywords: [key],
    })),
  ], [metricDisplayNames, sourceMetricKeys])
  const categoricalKeyOptions = useMemo(() => [
    { value: '', label: 'Field', keywords: ['field'] },
    ...categoricalKeys.map((key) => ({
      value: key,
      label: key,
      keywords: [key],
    })),
  ], [categoricalKeys])

  useEffect(() => {
    setDraft(createDerivedMetricDraft(derivedMetric.spec, sourceMetricKeys))
  }, [derivedMetric.key, derivedMetric.spec, sourceMetricKeys])

  const formulaCodeFromDraft = useMemo(() => buildDerivedMetricFormulaCode(draft), [draft])
  useEffect(() => {
    if (!formulaDirty) setFormulaCode(formulaCodeFromDraft)
  }, [formulaCodeFromDraft, formulaDirty])

  const draftBuild = useMemo(() => buildDerivedMetricSpecFromDraft(draft), [draft])
  const draftRankState = useMemo(() => evaluateDerivedMetricDraft(draft, {
    items,
    metricKeys: sourceMetricKeys,
    categoricalKeys,
    rankDisabledReason,
  }), [categoricalKeys, draft, items, rankDisabledReason, sourceMetricKeys])
  const formulaPreview = useMemo(
    () => buildDerivedMetricFormulaPreview(draft, metricDisplayNames),
    [draft, metricDisplayNames],
  )
  const formulaDiagnosticText = useMemo(
    () => formatFormulaDiagnostics(formulaDiagnostics),
    [formulaDiagnostics],
  )
  const numericTermKeys = useMemo(
    () => uniqueNumericTermKeys(draft.numericTerms),
    [draft.numericTerms],
  )
  const histogramsByMetric = useMemo(
    () => buildNumericTermHistograms({
      facets,
      items,
      metricKeys: numericTermKeys,
    }),
    [facets, items, numericTermKeys],
  )
  const applyDisabledReason = draftBuild.errors[0] ?? null
  const rankReason = draftRankState.disabledReason
  const activeCounts = derivedMetric.status === 'none' ? draftRankState.evaluation : derivedMetric
  const validCount = activeCounts?.validCount ?? 0
  const invalidCount = activeCounts?.invalidCount ?? items.length
  const activeStatusText = useMemo(
    () => formatActiveDerivedMetricStatus(derivedMetric),
    [derivedMetric],
  )
  const scorePreview = useMemo(() => {
    const evaluation = draftRankState.evaluation
    if (!evaluation?.key || evaluation.status !== 'valid') return null
    const valuesByKey = collectMetricValuesByKey(evaluation.items, [evaluation.key])
    return {
      key: evaluation.key,
      histogram: computeHistogramFromValues(getMetricValues(valuesByKey, evaluation.key), 32),
    }
  }, [draftRankState.evaluation])
  const unavailableInputs = draftRankState.evaluation?.status === 'unavailable'
    ? [
      ...draftRankState.evaluation.missingMetricKeys,
      ...draftRankState.evaluation.missingCategoricalKeys,
    ].sort()
    : []

  const updateNumericTerm = (index: number, patch: Partial<DerivedMetricNumericDraftTerm>) => {
    setFormulaDiagnostics(null)
    setDraft((prev) => ({
      ...prev,
      numericTerms: prev.numericTerms.map((term, idx) => (
        idx === index ? { ...term, ...patch } : term
      )),
    }))
  }

  const updateCategoricalTerm = (index: number, patch: Partial<DerivedMetricCategoricalDraftTerm>) => {
    setFormulaDiagnostics(null)
    setDraft((prev) => ({
      ...prev,
      categoricalTerms: prev.categoricalTerms.map((term, idx) => (
        idx === index ? { ...term, ...patch } : term
      )),
    }))
  }

  const applyDraft = () => {
    if (!draftBuild.spec) return
    onApplyDerivedMetric(draftBuild.spec)
  }

  const rankDraft = () => {
    if (!draftBuild.spec || rankReason) return
    onRankByDerivedMetric(draftBuild.spec)
  }

  const handleApplyFormula = () => {
    const result = applyDerivedMetricFormulaCode(formulaCode, draft, {
      metricKeys: sourceMetricKeys,
      categoricalKeys,
    })
    setFormulaDiagnostics(result.diagnostics)
    if (!result.applied) return
    const nextCode = buildDerivedMetricFormulaCode(result.draft)
    setDraft(result.draft)
    setFormulaCode(nextCode)
    setFormulaDirty(false)
  }

  const handleUseCurrentFormula = () => {
    setFormulaCode(formulaCodeFromDraft)
    setFormulaDirty(false)
    setFormulaDiagnostics(null)
  }

  const hasInputs = sourceMetricKeys.length > 0 || categoricalKeys.length > 0

  return (
    <div className="ui-card" data-derived-score-card>
      <div className="ui-card-header">
        <div className="ui-section-title">Derived Score</div>
        <div className="text-[11px] text-muted tabular-nums">
          Valid: {validCount} Invalid: {invalidCount}
        </div>
      </div>

      <div className="space-y-3">
        <div>
          <label className="ui-label" htmlFor="derived-score-name">Score name</label>
          <input
            id="derived-score-name"
            data-derived-score-name
            className="ui-input w-full"
            value={draft.name}
            onChange={(event) => setDraft((prev) => ({ ...prev, name: event.currentTarget.value }))}
          />
        </div>

        <div>
          <label className="ui-label" htmlFor="derived-score-intercept">Intercept</label>
          <input
            id="derived-score-intercept"
            data-derived-score-intercept
            type="text"
            inputMode="decimal"
            autoComplete="off"
            spellCheck={false}
            className="ui-input ui-number w-full"
            value={draft.intercept}
            onChange={(event) => setDraft((prev) => ({ ...prev, intercept: event.currentTarget.value }))}
          />
        </div>

        <div className="space-y-2">
          <div className="flex items-center justify-between gap-2">
            <div className="ui-label mb-0">Numeric terms</div>
            <button
              type="button"
              className="btn btn-xs btn-ghost"
              onClick={() => setDraft((prev) => ({
                ...prev,
                numericTerms: [...prev.numericTerms, createNumericDraftTerm(sourceMetricKeys)],
              }))}
              disabled={!sourceMetricKeys.length}
              title="Add numeric term"
            >
              <Plus size={12} aria-hidden="true" />
              <span>Add</span>
            </button>
          </div>
          {draft.numericTerms.length ? (
            <div className="space-y-2">
              {draft.numericTerms.map((term, index) => (
                <div key={`numeric-${index}`} className="rounded-md border border-border/60 bg-surface-inset p-2">
                  <div className="flex flex-wrap items-end gap-2">
                    <div className="flex min-w-[14rem] flex-[1_1_16rem] flex-col gap-1">
                      <span className="ui-label mb-0 text-[10px]">Metric</span>
                      <div data-derived-numeric-key={index}>
                        <Dropdown
                          value={term.key}
                          onChange={(nextKey) => updateNumericTerm(index, { key: nextKey })}
                          options={numericMetricOptions}
                          aria-label={`Numeric metric ${index + 1}`}
                          title={term.key ? getMetricDisplayName(term.key, metricDisplayNames) : 'Metric'}
                          triggerClassName="w-full min-w-0 justify-between"
                          width="trigger"
                          searchable="auto"
                          searchPlaceholder="Search metrics..."
                          emptyMessage="No matching metrics"
                        />
                      </div>
                    </div>
                    <label className="flex w-24 flex-col gap-1">
                      <span className="ui-label mb-0 text-[10px]">Weight</span>
                      <input
                        className="ui-input ui-number w-full"
                        value={term.weight}
                        aria-label={`Numeric weight ${index + 1}`}
                        data-derived-numeric-weight={index}
                        type="text"
                        inputMode="decimal"
                        autoComplete="off"
                        spellCheck={false}
                        onChange={(event) => updateNumericTerm(index, { weight: event.currentTarget.value })}
                      />
                    </label>
                    <label className="flex min-w-[10rem] flex-[0_0_10.5rem] flex-col gap-1">
                      <span className="ui-label mb-0 text-[10px]">Missing</span>
                      <select
                        className="ui-select ui-select-compact w-full"
                        value={term.missing}
                        aria-label={`Numeric missing ${index + 1}`}
                        data-derived-numeric-missing={index}
                        onChange={(event) => updateNumericTerm(index, {
                          missing: event.currentTarget.value === 'zero' ? 'zero' : 'invalid',
                        })}
                      >
                        <option value="invalid">Require value</option>
                        <option value="zero">Missing = 0</option>
                      </select>
                    </label>
                    <div className="ml-auto flex items-center gap-1 self-end">
                      <button
                        type="button"
                        className={`btn btn-xs h-8 px-2 ${term.zNormalize ? 'btn-active' : 'btn-ghost'}`}
                        aria-label={`Z-normalize numeric term ${index + 1}`}
                        aria-pressed={term.zNormalize}
                        title="Z-normalize this metric"
                        data-derived-numeric-znormalize={index}
                        onClick={() => updateNumericTerm(index, { zNormalize: !term.zNormalize })}
                      >
                        <Sigma size={12} aria-hidden="true" />
                        <span>Z</span>
                      </button>
                      <button
                        type="button"
                        className="btn btn-xs btn-ghost h-8 w-8 px-0"
                        aria-label={`Remove numeric term ${index + 1}`}
                        title="Remove numeric term"
                        onClick={() => setDraft((prev) => ({
                          ...prev,
                          numericTerms: prev.numericTerms.filter((_term, idx) => idx !== index),
                        }))}
                      >
                        <Trash2 size={12} aria-hidden="true" />
                      </button>
                    </div>
                  </div>
                  {term.key.trim() && (
                    <div className="mt-2">
                      <DerivedMetricMiniHistogram
                        metricKey={term.key.trim()}
                        histogram={histogramsByMetric.get(term.key.trim()) ?? null}
                      />
                    </div>
                  )}
                </div>
              ))}
            </div>
          ) : (
            <div className="text-xs text-muted">No numeric terms.</div>
          )}
        </div>

        <div className="space-y-2">
          <div className="flex items-center justify-between gap-2">
            <div className="ui-label mb-0">Categorical bonuses</div>
            <button
              type="button"
              className="btn btn-xs btn-ghost"
              onClick={() => setDraft((prev) => ({
                ...prev,
                categoricalTerms: [
                  ...prev.categoricalTerms,
                  createCategoricalDraftTerm(categoricalKeys, categoricalValuesByKey),
                ],
              }))}
              disabled={!categoricalKeys.length}
              title="Add categorical bonus"
            >
              <Plus size={12} aria-hidden="true" />
              <span>Add</span>
            </button>
          </div>
          {draft.categoricalTerms.length ? (
            <div className="space-y-2">
              {draft.categoricalTerms.map((term, index) => {
                const values = categoricalValuesByKey.get(term.key) ?? []
                return (
                  <div key={`categorical-${index}`} className="rounded-md border border-border/60 bg-surface-inset p-2">
                    <div className="flex flex-wrap items-end gap-2">
                      <div className="flex min-w-[12rem] flex-[1_1_14rem] flex-col gap-1">
                        <span className="ui-label mb-0 text-[10px]">Field</span>
                        <div data-derived-categorical-key={index}>
                          <Dropdown
                            value={term.key}
                            onChange={(nextKey) => {
                              updateCategoricalTerm(index, {
                                key: nextKey,
                                value: categoricalValuesByKey.get(nextKey)?.[0] ?? '',
                              })
                            }}
                            options={categoricalKeyOptions}
                            aria-label={`Categorical field ${index + 1}`}
                            title={term.key || 'Field'}
                            triggerClassName="w-full min-w-0 justify-between"
                            width="trigger"
                            searchable="auto"
                            searchPlaceholder="Search fields..."
                            emptyMessage="No matching fields"
                          />
                        </div>
                      </div>
                      <label className="flex min-w-[12rem] flex-[1_1_14rem] flex-col gap-1">
                        <span className="ui-label mb-0 text-[10px]">Value</span>
                        {values.length ? (
                          <div data-derived-categorical-value={index}>
                            <Dropdown
                              value={term.value}
                              onChange={(nextValue) => updateCategoricalTerm(index, { value: nextValue })}
                              options={[
                                { value: '', label: 'Value', keywords: ['value'] },
                                ...values.map((value) => ({
                                  value,
                                  label: value,
                                  keywords: [value],
                                })),
                              ]}
                              aria-label={`Categorical value ${index + 1}`}
                              title={term.value || 'Value'}
                              triggerClassName="w-full min-w-0 justify-between"
                              width="trigger"
                              searchable="auto"
                              searchPlaceholder="Search values..."
                              emptyMessage="No matching values"
                            />
                          </div>
                        ) : (
                          <input
                            className="ui-input w-full min-w-0"
                            value={term.value}
                            aria-label={`Categorical value ${index + 1}`}
                            data-derived-categorical-value={index}
                            onChange={(event) => updateCategoricalTerm(index, { value: event.currentTarget.value })}
                          />
                        )}
                      </label>
                      <label className="flex w-24 flex-col gap-1">
                        <span className="ui-label mb-0 text-[10px]">Bonus</span>
                        <input
                          className="ui-input ui-number w-full"
                          value={term.weight}
                          aria-label={`Categorical weight ${index + 1}`}
                          data-derived-categorical-weight={index}
                          type="text"
                          inputMode="decimal"
                          autoComplete="off"
                          spellCheck={false}
                          onChange={(event) => updateCategoricalTerm(index, { weight: event.currentTarget.value })}
                        />
                      </label>
                      <button
                        type="button"
                        className="btn btn-xs btn-ghost h-8 w-8 px-0"
                        aria-label={`Remove categorical bonus ${index + 1}`}
                        title="Remove categorical bonus"
                        onClick={() => setDraft((prev) => ({
                          ...prev,
                          categoricalTerms: prev.categoricalTerms.filter((_term, idx) => idx !== index),
                        }))}
                      >
                        <Trash2 size={12} aria-hidden="true" />
                      </button>
                    </div>
                  </div>
                )
              })}
            </div>
          ) : (
            <div className="text-xs text-muted">No categorical bonuses.</div>
          )}
        </div>

        <div className="rounded-md border border-border/60 bg-surface-inset px-2 py-1.5 text-[12px] text-text break-words" data-derived-formula-preview>
          {formulaPreview}
        </div>

        <div className="min-h-4 text-[11px] text-muted" data-derived-score-status>
          {!hasInputs
            ? 'No score inputs in this view.'
            : unavailableInputs.length
              ? `Unavailable inputs: ${unavailableInputs.join(', ')}.`
              : applyDisabledReason ?? rankReason ?? activeStatusText ?? 'Score ready.'}
        </div>
        {scorePreview && (
          <div data-derived-score-preview-histogram>
            <DerivedMetricMiniHistogram
              metricKey={scorePreview.key}
              histogram={scorePreview.histogram}
            />
          </div>
        )}

        <div className="flex flex-wrap items-center gap-2">
          <button
            type="button"
            className="btn btn-sm"
            data-derived-score-apply
            disabled={!draftBuild.spec}
            title={applyDisabledReason ?? 'Apply score'}
            onClick={applyDraft}
          >
            Apply
          </button>
          <button
            type="button"
            className="btn btn-sm btn-active"
            data-derived-score-rank
            disabled={!draftBuild.spec || !!rankReason}
            title={rankReason ?? 'Sort by this score'}
            onClick={rankDraft}
          >
            Sort by score
          </button>
          <button
            type="button"
            className="btn btn-sm btn-ghost"
            data-derived-score-clear
            onClick={() => onApplyDerivedMetric(null)}
          >
            Clear
          </button>
        </div>

        <div className="space-y-2 border-t border-border/60 pt-3">
          <div className="flex items-center justify-between gap-2">
            <label className="ui-label mb-0" htmlFor="derived-formula-code">Formula code</label>
            <button
              type="button"
              className="btn btn-xs btn-ghost"
              data-derived-formula-use-current
              onClick={handleUseCurrentFormula}
            >
              Use current
            </button>
          </div>
          <textarea
            id="derived-formula-code"
            className="ui-textarea font-mono w-full min-h-[84px] text-[12px]"
            data-derived-formula-code
            value={formulaCode}
            spellCheck={false}
            onChange={(event) => {
              setFormulaCode(event.currentTarget.value)
              setFormulaDirty(true)
              setFormulaDiagnostics(null)
            }}
          />
          <div className="flex flex-wrap items-center gap-2">
            <button
              type="button"
              className="btn btn-sm"
              data-derived-formula-apply
              disabled={!formulaCode.trim()}
              onClick={handleApplyFormula}
            >
              Apply formula
            </button>
          </div>
          {formulaDiagnosticText && (
            <div className="min-h-4 text-[11px] text-muted" data-derived-formula-diagnostics>
              {formulaDiagnosticText}
            </div>
          )}
        </div>
      </div>
    </div>
  )
}

function uniqueNumericTermKeys(terms: readonly DerivedMetricNumericDraftTerm[]): string[] {
  const keys = new Set<string>()
  for (const term of terms) {
    const key = term.key.trim()
    if (key) keys.add(key)
  }
  return Array.from(keys).sort()
}

function buildNumericTermHistograms({
  facets,
  items,
  metricKeys,
}: {
  facets: BrowseFacetsPayload | null
  items: BrowseItemPayload[]
  metricKeys: readonly string[]
}): Map<string, Histogram | null> {
  const histograms = new Map<string, Histogram | null>()
  if (!metricKeys.length) return histograms

  const missingKeys: string[] = []
  for (const key of metricKeys) {
    const histogram = metricHistogramFromFacet(facets?.metrics[key]?.histogram)
    if (histogram) {
      histograms.set(key, histogram)
    } else {
      missingKeys.push(key)
    }
  }
  if (!missingKeys.length) return histograms

  const valuesByKey = collectMetricValuesByKey(items, missingKeys)
  for (const key of missingKeys) {
    histograms.set(key, computeHistogramFromValues(getMetricValues(valuesByKey, key), 32))
  }
  return histograms
}

function formatFormulaDiagnostics(diagnostics: DerivedMetricFormulaDiagnostics | null): string | null {
  if (!diagnostics) return null
  const parts: string[] = []
  if (diagnostics.errors.length) {
    parts.push(diagnostics.errors.join(' '))
  }
  if (diagnostics.missingMetricKeys.length) {
    parts.push(`Missing metrics: ${diagnostics.missingMetricKeys.join(', ')}.`)
  }
  if (diagnostics.missingCategoricalKeys.length) {
    parts.push(`Missing fields: ${diagnostics.missingCategoricalKeys.join(', ')}.`)
  }
  if (diagnostics.skippedTerms.length) {
    parts.push(`Skipped ${diagnostics.skippedTerms.length} term${diagnostics.skippedTerms.length === 1 ? '' : 's'}.`)
  }
  return parts.length ? parts.join(' ') : 'Formula applied.'
}

function formatActiveDerivedMetricStatus(derivedMetric: DerivedMetricEvaluation): string | null {
  if (derivedMetric.status === 'none') return null
  if (derivedMetric.status === 'invalid') {
    return derivedMetric.invalidReasons[0] ?? 'Saved score definition is invalid.'
  }
  if (derivedMetric.status === 'unavailable') {
    const missing = [
      ...derivedMetric.missingMetricKeys,
      ...derivedMetric.missingCategoricalKeys,
    ].sort()
    return `Unavailable inputs: ${missing.join(', ') || 'unknown inputs'}.`
  }
  const population = derivedMetric.scorePopulationCount ?? derivedMetric.totalItems
  if (population != null && population !== derivedMetric.loadedCount) {
    return `Score ready across ${population} query-filtered items.`
  }
  return 'Score ready.'
}
