import { Plus, Sigma, Trash2 } from 'lucide-react'
import React, { useEffect, useMemo, useState } from 'react'
import type {
  BrowseFacetsPayload,
  BrowseFacetFields,
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
  derivedMetricDraftResetToken,
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
import {
  facetFieldQueryState,
  resolveFacetFieldState,
  type FacetFieldQueryStates,
  type FacetQueryState,
} from '../model/facetPresentation'

interface DerivedScoreCardProps {
  items: BrowseItemPayload[]
  metricKeys: string[]
  categoricalKeys: string[]
  metricDisplayNames?: MetricDisplayNames | null
  facets?: BrowseFacetsPayload | null
  facetsState?: FacetQueryState
  facetFieldStates?: FacetFieldQueryStates
  populationItemsComplete?: boolean
  derivedMetric: DerivedMetricEvaluation
  backendAuthoritative?: boolean
  rankDisabledReason?: string | null
  onApplyDerivedMetric: (spec: DerivedMetricSpec | null) => void
  onRankByDerivedMetric: (spec: DerivedMetricSpec) => void
  onFacetFieldsChange?: (fields: BrowseFacetFields) => void
}

type DerivedScoreCardEditorProps = Omit<DerivedScoreCardProps, 'metricKeys'> & {
  sourceMetricKeys: string[]
}

const MISSING_VALUE_OPTIONS = [
  { value: 'invalid', label: 'Require value' },
  { value: 'zero', label: 'Missing = 0' },
]

export default function DerivedScoreCard(props: DerivedScoreCardProps): JSX.Element {
  const sourceMetricKeys = props.metricKeys.filter((key) => !isDerivedMetricKey(key))
  const resetToken = derivedMetricDraftResetToken(
    props.derivedMetric,
    sourceMetricKeys,
    props.categoricalKeys,
  )
  return (
    <DerivedScoreCardEditor
      key={resetToken}
      {...props}
      sourceMetricKeys={sourceMetricKeys}
    />
  )
}

function DerivedScoreCardEditor({
  items,
  sourceMetricKeys,
  categoricalKeys,
  metricDisplayNames,
  facets = null,
  facetsState = 'settled',
  facetFieldStates,
  populationItemsComplete = true,
  derivedMetric,
  backendAuthoritative = false,
  rankDisabledReason = null,
  onApplyDerivedMetric,
  onRankByDerivedMetric,
  onFacetFieldsChange,
}: DerivedScoreCardEditorProps): JSX.Element {
  const categoricalValuesByKey = useMemo(() => {
    const values = populationItemsComplete
      ? collectCategoricalValuesByKey(items, categoricalKeys)
      : new Map<string, string[]>()
    categoricalKeys.forEach((key) => {
      const facet = facets?.categoricals[key]
      if (facet) values.set(key, facet.values.map((entry) => entry.value))
    })
    return values
  },
    [categoricalKeys, facets, items, populationItemsComplete],
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
    () => uniqueTermKeys(draft.numericTerms),
    [draft.numericTerms],
  )
  const categoricalTermKeys = useMemo(
    () => uniqueTermKeys(draft.categoricalTerms),
    [draft.categoricalTerms],
  )
  useEffect(() => {
    onFacetFieldsChange?.({
      metric_keys: numericTermKeys,
      categorical_keys: categoricalTermKeys,
    })
  }, [categoricalTermKeys, numericTermKeys, onFacetFieldsChange])
  const histogramsByMetric = useMemo(
    () => buildNumericTermHistograms({
      facets,
      items,
      metricKeys: numericTermKeys,
    }),
    [facets, items, numericTermKeys],
  )
  const applyDisabledReason = draftBuild.errors[0] ?? null
  const backendSchemaReason = !draftRankState.evaluation
    || draftRankState.evaluation.status === 'unavailable'
    || draftRankState.evaluation.status === 'invalid'
    ? draftRankState.disabledReason
    : null
  const rankReason = backendAuthoritative
    ? rankDisabledReason ?? backendSchemaReason
    : draftRankState.disabledReason
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
                    <div className="flex min-w-[10rem] flex-[0_0_10.5rem] flex-col gap-1">
                      <span className="ui-label mb-0 text-[10px]">Missing</span>
                      <div data-derived-numeric-missing={index}>
                        <Dropdown
                          value={term.missing}
                          onChange={(nextValue) => updateNumericTerm(index, {
                            missing: nextValue === 'zero' ? 'zero' : 'invalid',
                          })}
                          options={MISSING_VALUE_OPTIONS}
                          aria-label={`Numeric missing ${index + 1}`}
                          title={term.missing === 'zero' ? 'Missing = 0' : 'Require value'}
                          triggerClassName="w-full justify-between"
                          width="trigger"
                        />
                      </div>
                    </div>
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
                  <div className="mt-2">
                    <DerivedMetricMiniHistogram
                      metricKey={term.key.trim() || 'Unselected metric'}
                      histogram={term.key.trim()
                        ? histogramsByMetric.get(term.key.trim()) ?? null
                        : null}
                    />
                  </div>
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
                const hasFacet = !!term.key && Object.prototype.hasOwnProperty.call(
                  facets?.categoricals ?? {},
                  term.key,
                )
                const valueState = term.key
                  ? resolveFacetFieldState({
                    facetDataState: !hasFacet
                      ? 'absent'
                      : values.length > 0
                        ? 'ready'
                        : 'empty',
                    localDataState: hasFacet || !populationItemsComplete
                      ? 'absent'
                      : values.length > 0
                        ? 'ready'
                        : 'empty',
                    queryState: facetFieldQueryState(
                      facetFieldStates,
                      'categoricals',
                      term.key,
                      facetsState,
                    ),
                  })
                  : 'empty'
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
                        <div data-derived-categorical-value={index} data-facet-state={valueState}>
                          <Dropdown
                            value={term.value}
                            onChange={(nextValue) => updateCategoricalTerm(index, { value: nextValue })}
                            options={values.map((value) => ({
                              value,
                              label: value,
                              keywords: [value],
                            }))}
                            aria-label={`Categorical value ${index + 1}`}
                            title={valueState === 'pending' ? 'Loading known values…' : term.value || 'Value'}
                            placeholder={valueControlPlaceholder(valueState)}
                            triggerClassName="w-full min-w-0"
                            panelClassName="min-w-[12rem]"
                            width="trigger"
                            editable
                            disabled={valueState === 'pending'}
                            emptyMessage={valueState === 'error'
                              ? 'Known values could not be loaded; enter a custom value.'
                              : 'No known values; enter a custom value.'}
                          />
                        </div>
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

        <div
          className="h-16 overflow-auto scrollbar-thin rounded-md border border-border/60 bg-surface-inset px-2 py-1.5 text-[12px] text-text break-words"
          data-derived-formula-preview
          tabIndex={0}
          title={formulaPreview}
        >
          {formulaPreview}
        </div>

        <div className="h-10 overflow-auto scrollbar-thin text-[11px] text-muted" data-derived-score-status tabIndex={0}>
          {!hasInputs
            ? 'No score inputs in this view.'
            : unavailableInputs.length
              ? `Unavailable inputs: ${unavailableInputs.join(', ')}.`
              : applyDisabledReason ?? rankReason ?? activeStatusText ?? 'Score ready.'}
        </div>
        <div data-derived-score-preview-histogram>
          <DerivedMetricMiniHistogram
            metricKey={scorePreview?.key ?? 'Derived score preview'}
            histogram={scorePreview?.histogram ?? null}
          />
        </div>

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
            className="ui-textarea font-mono h-24 w-full resize-none text-[12px]"
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
          <div
            className="h-14 overflow-auto scrollbar-thin text-[11px] text-muted"
            data-derived-formula-diagnostics
            tabIndex={0}
            title={formulaDiagnosticText ?? undefined}
          >
            {formulaDiagnosticText}
          </div>
        </div>
      </div>
    </div>
  )
}

function valueControlPlaceholder(state: 'pending' | 'error' | 'empty' | 'ready'): string {
  if (state === 'pending') return 'Loading values…'
  if (state === 'error') return 'Enter a value'
  if (state === 'empty') return 'Enter a value'
  return 'Value'
}

function uniqueTermKeys(terms: readonly { key: string }[]): string[] {
  return Array.from(new Set(
    terms.map((term) => term.key.trim()).filter(Boolean),
  )).sort()
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
