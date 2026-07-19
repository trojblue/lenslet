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
  derivedFacetFieldsFromDraft,
  derivedMetricEditorResetToken,
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
  useFacetFieldPresentation,
  type FacetFieldQueryStates,
  type FacetFieldState,
  type FacetQueryState,
} from '../model/facetPresentation'

interface DerivedScoreCardProps {
  active?: boolean
  items: BrowseItemPayload[]
  metricKeys: string[]
  categoricalKeys: string[]
  metricDisplayNames?: MetricDisplayNames | null
  facets?: BrowseFacetsPayload | null
  facetsState?: FacetQueryState
  facetFieldStates?: FacetFieldQueryStates
  populationItemsComplete?: boolean
  presentationResetKey?: string
  draftResetKey?: string
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

const draftTermIdentityByObject = new WeakMap<object, string>()
let draftTermIdentitySequence = 0

function draftTermIdentity(term: object, kind: 'numeric' | 'categorical'): string {
  const existing = draftTermIdentityByObject.get(term)
  if (existing) return existing
  draftTermIdentitySequence += 1
  const identity = `${kind}-${draftTermIdentitySequence}`
  draftTermIdentityByObject.set(term, identity)
  return identity
}

function transferDraftTermIdentity(previous: object, next: object): void {
  const identity = draftTermIdentityByObject.get(previous)
  if (identity) draftTermIdentityByObject.set(next, identity)
}

function transferDraftTermIdentities(
  previous: object[],
  next: object[],
  kind: 'numeric' | 'categorical',
): void {
  next.forEach((term, index) => {
    const previousTerm = previous[index]
    if (!previousTerm) return
    draftTermIdentityByObject.set(term, draftTermIdentity(previousTerm, kind))
  })
}

export default function DerivedScoreCard(props: DerivedScoreCardProps): JSX.Element {
  const sourceMetricKeys = props.metricKeys.filter((key) => !isDerivedMetricKey(key))
  const resetToken = derivedMetricEditorResetToken(
    props.derivedMetric,
    props.draftResetKey ?? 'default',
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
  active = true,
  items,
  sourceMetricKeys,
  categoricalKeys,
  metricDisplayNames,
  facets = null,
  facetsState = 'settled',
  facetFieldStates,
  populationItemsComplete = true,
  presentationResetKey = 'default',
  derivedMetric,
  backendAuthoritative = false,
  rankDisabledReason = null,
  onApplyDerivedMetric,
  onRankByDerivedMetric,
  onFacetFieldsChange,
}: DerivedScoreCardEditorProps): JSX.Element {
  const categoricalValuesByKey = useMemo(() => {
    if (!active) return new Map<string, string[]>()
    const values = populationItemsComplete
      ? collectCategoricalValuesByKey(items, categoricalKeys)
      : new Map<string, string[]>()
    categoricalKeys.forEach((key) => {
      const facet = facets?.categoricals[key]
      if (facet) values.set(key, facet.values.map((entry) => entry.value))
    })
    return values
  },
    [active, categoricalKeys, facets, items, populationItemsComplete],
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
  const draftRankState = useMemo(() => active
    ? evaluateDerivedMetricDraft(draft, {
        items,
        metricKeys: sourceMetricKeys,
        categoricalKeys,
        rankDisabledReason,
      })
    : { disabledReason: rankDisabledReason, evaluation: null },
  [active, categoricalKeys, draft, items, rankDisabledReason, sourceMetricKeys])
  const formulaPreview = useMemo(
    () => buildDerivedMetricFormulaPreview(draft, metricDisplayNames),
    [draft, metricDisplayNames],
  )
  const formulaDiagnosticText = useMemo(
    () => formatFormulaDiagnostics(formulaDiagnostics),
    [formulaDiagnostics],
  )
  const draftFacetFields = useMemo(() => derivedFacetFieldsFromDraft(draft), [draft])
  const numericTermKeys = draftFacetFields.metric_keys
  const categoricalTermKeys = draftFacetFields.categorical_keys
  const histogramsByMetric = useMemo(
    () => active
      ? buildNumericTermHistograms({
          facets,
          facetsState,
          facetFieldStates,
          items,
          metricKeys: numericTermKeys,
          populationItemsComplete,
        })
      : new Map<string, DerivedHistogram>(),
    [
      active,
      facetFieldStates,
      facets,
      facetsState,
      items,
      numericTermKeys,
      populationItemsComplete,
    ],
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
    if (!active) return null
    const evaluation = draftRankState.evaluation
    if (!evaluation?.key || evaluation.status !== 'valid') return null
    const valuesByKey = collectMetricValuesByKey(evaluation.items, [evaluation.key])
    return {
      key: evaluation.key,
      histogram: computeHistogramFromValues(getMetricValues(valuesByKey, evaluation.key), 32),
    }
  }, [active, draftRankState.evaluation])
  const categoricalTermStates = useMemo(() => new Map(categoricalTermKeys.map((key) => {
    const values = categoricalValuesByKey.get(key) ?? []
    return [key, resolveCategoricalTermState({
      key,
      values,
      facets,
      facetsState,
      facetFieldStates,
      populationItemsComplete,
    })]
  })), [
    categoricalTermKeys,
    categoricalValuesByKey,
    facetFieldStates,
    facets,
    facetsState,
    populationItemsComplete,
  ])
  const scorePreviewState = resolveScorePreviewState({
    histogram: scorePreview?.histogram ?? null,
    populationItemsComplete,
    requiredStates: [
      ...Array.from(histogramsByMetric.values(), (entry) => entry.state),
      ...categoricalTermKeys.map((key) => categoricalTermStates.get(key) ?? 'pending'),
    ],
  })
  const unavailableInputs = draftRankState.evaluation?.status === 'unavailable'
    ? [
      ...draftRankState.evaluation.missingMetricKeys,
      ...draftRankState.evaluation.missingCategoricalKeys,
    ].sort()
    : []

  const updateNumericTerm = (index: number, patch: Partial<DerivedMetricNumericDraftTerm>) => {
    setFormulaDiagnostics(null)
    const nextTerms = draft.numericTerms.map((term, idx) => {
      if (idx !== index) return term
      const next = { ...term, ...patch }
      transferDraftTermIdentity(term, next)
      return next
    })
    const nextDraft = { ...draft, numericTerms: nextTerms }
    if (patch.key !== undefined) onFacetFieldsChange?.(derivedFacetFieldsFromDraft(nextDraft))
    setDraft(nextDraft)
  }

  const updateCategoricalTerm = (index: number, patch: Partial<DerivedMetricCategoricalDraftTerm>) => {
    setFormulaDiagnostics(null)
    const nextTerms = draft.categoricalTerms.map((term, idx) => {
      if (idx !== index) return term
      const next = { ...term, ...patch }
      transferDraftTermIdentity(term, next)
      return next
    })
    const nextDraft = { ...draft, categoricalTerms: nextTerms }
    if (patch.key !== undefined) onFacetFieldsChange?.(derivedFacetFieldsFromDraft(nextDraft))
    setDraft(nextDraft)
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
    transferDraftTermIdentities(draft.numericTerms, result.draft.numericTerms, 'numeric')
    transferDraftTermIdentities(draft.categoricalTerms, result.draft.categoricalTerms, 'categorical')
    onFacetFieldsChange?.(derivedFacetFieldsFromDraft(result.draft))
    setDraft(result.draft)
    setFormulaCode(nextCode)
    setFormulaDirty(false)
  }

  const handleUseCurrentFormula = () => {
    setFormulaCode(formulaCodeFromDraft)
    setFormulaDirty(false)
    setFormulaDiagnostics(null)
  }

  const addNumericTerm = () => {
    const nextDraft = {
      ...draft,
      numericTerms: [...draft.numericTerms, createNumericDraftTerm(sourceMetricKeys)],
    }
    onFacetFieldsChange?.(derivedFacetFieldsFromDraft(nextDraft))
    setDraft(nextDraft)
  }

  const removeNumericTerm = (index: number) => {
    const nextDraft = {
      ...draft,
      numericTerms: draft.numericTerms.filter((_term, idx) => idx !== index),
    }
    onFacetFieldsChange?.(derivedFacetFieldsFromDraft(nextDraft))
    setDraft(nextDraft)
  }

  const addCategoricalTerm = () => {
    const nextDraft = {
      ...draft,
      categoricalTerms: [
        ...draft.categoricalTerms,
        createCategoricalDraftTerm(categoricalKeys, categoricalValuesByKey),
      ],
    }
    onFacetFieldsChange?.(derivedFacetFieldsFromDraft(nextDraft))
    setDraft(nextDraft)
  }

  const removeCategoricalTerm = (index: number) => {
    const nextDraft = {
      ...draft,
      categoricalTerms: draft.categoricalTerms.filter((_term, idx) => idx !== index),
    }
    onFacetFieldsChange?.(derivedFacetFieldsFromDraft(nextDraft))
    setDraft(nextDraft)
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
              onClick={addNumericTerm}
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
                <DerivedNumericTermRow
                  key={draftTermIdentity(term, 'numeric')}
                  index={index}
                  term={term}
                  candidate={term.key.trim()
                    ? histogramsByMetric.get(term.key.trim()) ?? {
                        histogram: null,
                        state: 'pending',
                      }
                    : { histogram: null, state: 'empty' }}
                  metricOptions={numericMetricOptions}
                  metricDisplayNames={metricDisplayNames}
                  presentationResetKey={presentationResetKey}
                  onChange={(patch) => updateNumericTerm(index, patch)}
                  onRemove={() => removeNumericTerm(index)}
                />
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
              onClick={addCategoricalTerm}
              disabled={!categoricalKeys.length}
              title="Add categorical bonus"
            >
              <Plus size={12} aria-hidden="true" />
              <span>Add</span>
            </button>
          </div>
          {draft.categoricalTerms.length ? (
            <div className="space-y-2">
              {draft.categoricalTerms.map((term, index) => (
                <DerivedCategoricalTermRow
                  key={draftTermIdentity(term, 'categorical')}
                  index={index}
                  term={term}
                  candidate={{
                    values: categoricalValuesByKey.get(term.key) ?? [],
                    state: term.key
                      ? categoricalTermStates.get(term.key) ?? 'pending'
                      : 'empty',
                  }}
                  fieldOptions={categoricalKeyOptions}
                  presentationResetKey={presentationResetKey}
                  onFieldChange={(nextKey) => updateCategoricalTerm(index, {
                    key: nextKey,
                    value: categoricalValuesByKey.get(nextKey)?.[0] ?? '',
                  })}
                  onChange={(patch) => updateCategoricalTerm(index, patch)}
                  onRemove={() => removeCategoricalTerm(index)}
                />
              ))}
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
          <DerivedNumericTermHistogram
            index="score-preview"
            metricKey={scorePreview?.key ?? 'Derived score preview'}
            candidate={{ histogram: scorePreview?.histogram ?? null, state: scorePreviewState }}
            presentationResetKey={presentationResetKey}
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

type DerivedHistogram = {
  histogram: Histogram | null
  state: FacetFieldState
}

function resolveCategoricalTermState({
  key,
  values,
  facets,
  facetsState,
  facetFieldStates,
  populationItemsComplete,
}: {
  key: string
  values: readonly string[]
  facets: BrowseFacetsPayload | null
  facetsState: FacetQueryState
  facetFieldStates?: FacetFieldQueryStates
  populationItemsComplete: boolean
}): FacetFieldState {
  const hasFacet = Object.prototype.hasOwnProperty.call(facets?.categoricals ?? {}, key)
  return resolveFacetFieldState({
    facetDataState: !hasFacet ? 'absent' : values.length > 0 ? 'ready' : 'empty',
    localDataState: hasFacet || !populationItemsComplete
      ? 'absent'
      : values.length > 0
        ? 'ready'
        : 'empty',
    queryState: facetFieldQueryState(
      facetFieldStates,
      'categoricals',
      key,
      facetsState,
    ),
  })
}

export function resolveScorePreviewState({
  histogram,
  populationItemsComplete,
  requiredStates,
}: {
  histogram: Histogram | null
  populationItemsComplete: boolean
  requiredStates: readonly FacetFieldState[]
}): FacetFieldState {
  if (populationItemsComplete) return histogram ? 'ready' : 'empty'
  if (requiredStates.length === 0) return 'empty'
  if (requiredStates.some((state) => state === 'error')) return 'error'
  return 'pending'
}

type DerivedNumericMetricOption = {
  value: string
  label: string
  keywords: string[]
}

type DerivedCategoricalFieldOption = {
  value: string
  label: string
  keywords: string[]
}

function DerivedCategoricalTermRow({
  index,
  term,
  candidate,
  fieldOptions,
  presentationResetKey,
  onFieldChange,
  onChange,
  onRemove,
}: {
  index: number
  term: DerivedMetricCategoricalDraftTerm
  candidate: { values: string[]; state: FacetFieldState }
  fieldOptions: DerivedCategoricalFieldOption[]
  presentationResetKey: string
  onFieldChange: (key: string) => void
  onChange: (patch: Partial<DerivedMetricCategoricalDraftTerm>) => void
  onRemove: () => void
}): JSX.Element {
  const requestedKey = term.key.trim() || 'Unselected field'
  const { presentation, retained } = useFacetFieldPresentation({
    key: requestedKey,
    state: candidate.state,
    value: { term, values: candidate.values },
  }, presentationResetKey)
  const presentedTerm = presentation.value.term
  const presentedValues = presentation.value.values
  return (
    <div
      className="rounded-md border border-border/60 bg-surface-inset p-2"
      data-derived-categorical-term-slot={index}
      data-facet-requested-field={requestedKey}
      data-facet-presented-field={presentation.key}
      aria-busy={retained || undefined}
      aria-disabled={retained || undefined}
      ref={(element) => element?.toggleAttribute('inert', retained)}
    >
      <div className="flex flex-wrap items-end gap-2">
        <div className="flex min-w-[12rem] flex-[1_1_14rem] flex-col gap-1">
          <span className="ui-label mb-0 text-[10px]">Field</span>
          <div data-derived-categorical-key={index}>
            <Dropdown
              value={presentedTerm.key}
              onChange={onFieldChange}
              options={fieldOptions}
              aria-label={`Categorical field ${index + 1}`}
              title={presentedTerm.key || 'Field'}
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
          <div
            data-derived-categorical-value={index}
            data-facet-state={presentation.state}
            data-facet-requested-field={requestedKey}
            data-facet-presented-field={presentation.key}
          >
            <Dropdown
              value={presentedTerm.value}
              onChange={(nextValue) => onChange({ value: nextValue })}
              options={presentedValues.map((value) => ({
                value,
                label: value,
                keywords: [value],
              }))}
              aria-label={`Categorical value ${index + 1}`}
              title={presentation.state === 'pending'
                ? 'Loading known values…'
                : presentedTerm.value || 'Value'}
              placeholder={valueControlPlaceholder(presentation.state)}
              triggerClassName="w-full min-w-0"
              panelClassName="min-w-[12rem]"
              width="trigger"
              editable
              emptyMessage={presentation.state === 'error'
                ? 'Known values could not be loaded; enter a custom value.'
                : 'No known values; enter a custom value.'}
            />
          </div>
        </label>
        <label className="flex w-24 flex-col gap-1">
          <span className="ui-label mb-0 text-[10px]">Bonus</span>
          <input
            className="ui-input ui-number w-full"
            value={presentedTerm.weight}
            aria-label={`Categorical weight ${index + 1}`}
            data-derived-categorical-weight={index}
            type="text"
            inputMode="decimal"
            autoComplete="off"
            spellCheck={false}
            onChange={(event) => onChange({ weight: event.currentTarget.value })}
          />
        </label>
        <button
          type="button"
          className="btn btn-xs btn-ghost h-8 w-8 px-0"
          aria-label={`Remove categorical bonus ${index + 1}`}
          title="Remove categorical bonus"
          onClick={onRemove}
        >
          <Trash2 size={12} aria-hidden="true" />
        </button>
      </div>
    </div>
  )
}

function DerivedNumericTermRow({
  index,
  term,
  candidate,
  metricOptions,
  metricDisplayNames,
  presentationResetKey,
  onChange,
  onRemove,
}: {
  index: number
  term: DerivedMetricNumericDraftTerm
  candidate: DerivedHistogram
  metricOptions: DerivedNumericMetricOption[]
  metricDisplayNames?: MetricDisplayNames | null
  presentationResetKey: string
  onChange: (patch: Partial<DerivedMetricNumericDraftTerm>) => void
  onRemove: () => void
}): JSX.Element {
  const requestedKey = term.key.trim() || 'Unselected metric'
  const { presentation, retained } = useFacetFieldPresentation({
    key: requestedKey,
    state: candidate.state,
    value: { term, histogram: candidate.histogram },
  }, presentationResetKey)
  const presentedTerm = presentation.value.term
  return (
    <div
      className="rounded-md border border-border/60 bg-surface-inset p-2"
      data-derived-numeric-term-slot={index}
      data-facet-requested-field={requestedKey}
      data-facet-presented-field={presentation.key}
      aria-busy={retained || undefined}
      aria-disabled={retained || undefined}
      ref={(element) => element?.toggleAttribute('inert', retained)}
    >
      <div className="flex flex-wrap items-end gap-2">
        <div className="flex min-w-[14rem] flex-[1_1_16rem] flex-col gap-1">
          <span className="ui-label mb-0 text-[10px]">Metric</span>
          <div data-derived-numeric-key={index}>
            <Dropdown
              value={presentedTerm.key}
              onChange={(nextKey) => onChange({ key: nextKey })}
              options={metricOptions}
              aria-label={`Numeric metric ${index + 1}`}
              title={presentedTerm.key
                ? getMetricDisplayName(presentedTerm.key, metricDisplayNames)
                : 'Metric'}
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
            value={presentedTerm.weight}
            aria-label={`Numeric weight ${index + 1}`}
            data-derived-numeric-weight={index}
            type="text"
            inputMode="decimal"
            autoComplete="off"
            spellCheck={false}
            onChange={(event) => onChange({ weight: event.currentTarget.value })}
          />
        </label>
        <div className="flex min-w-[10rem] flex-[0_0_10.5rem] flex-col gap-1">
          <span className="ui-label mb-0 text-[10px]">Missing</span>
          <div data-derived-numeric-missing={index}>
            <Dropdown
              value={presentedTerm.missing}
              onChange={(nextValue) => onChange({
                missing: nextValue === 'zero' ? 'zero' : 'invalid',
              })}
              options={MISSING_VALUE_OPTIONS}
              aria-label={`Numeric missing ${index + 1}`}
              title={presentedTerm.missing === 'zero' ? 'Missing = 0' : 'Require value'}
              triggerClassName="w-full justify-between"
              width="trigger"
            />
          </div>
        </div>
        <div className="ml-auto flex items-center gap-1 self-end">
          <button
            type="button"
            className={`btn btn-xs h-8 px-2 ${presentedTerm.zNormalize ? 'btn-active' : 'btn-ghost'}`}
            aria-label={`Z-normalize numeric term ${index + 1}`}
            aria-pressed={presentedTerm.zNormalize}
            title="Z-normalize this metric"
            data-derived-numeric-znormalize={index}
            onClick={() => onChange({ zNormalize: !presentedTerm.zNormalize })}
          >
            <Sigma size={12} aria-hidden="true" />
            <span>Z</span>
          </button>
          <button
            type="button"
            className="btn btn-xs btn-ghost h-8 w-8 px-0"
            aria-label={`Remove numeric term ${index + 1}`}
            title="Remove numeric term"
            onClick={onRemove}
          >
            <Trash2 size={12} aria-hidden="true" />
          </button>
        </div>
      </div>
      <div
        className="mt-2"
        data-derived-numeric-histogram-slot={index}
        data-facet-requested-field={requestedKey}
        data-facet-presented-field={presentation.key}
        aria-busy={retained || undefined}
      >
        <DerivedMetricMiniHistogram
          metricKey={presentation.key}
          histogram={presentation.value.histogram}
          state={presentation.state}
        />
      </div>
    </div>
  )
}

function DerivedNumericTermHistogram({
  index,
  metricKey,
  candidate,
  presentationResetKey,
}: {
  index: number | 'score-preview'
  metricKey: string
  candidate: DerivedHistogram
  presentationResetKey: string
}): JSX.Element {
  const { presentation, retained } = useFacetFieldPresentation({
    key: metricKey,
    state: candidate.state,
    value: candidate.histogram,
  }, presentationResetKey)
  return (
    <div
      className={index === 'score-preview' ? '' : 'mt-2'}
      data-derived-numeric-histogram-slot={index}
      data-facet-requested-field={metricKey}
      data-facet-presented-field={presentation.key}
      aria-busy={retained || undefined}
    >
      <DerivedMetricMiniHistogram
        metricKey={presentation.key}
        histogram={presentation.value}
        state={presentation.state}
      />
    </div>
  )
}

function buildNumericTermHistograms({
  facets,
  facetsState,
  facetFieldStates,
  items,
  metricKeys,
  populationItemsComplete,
}: {
  facets: BrowseFacetsPayload | null
  facetsState: FacetQueryState
  facetFieldStates?: FacetFieldQueryStates
  items: BrowseItemPayload[]
  metricKeys: readonly string[]
  populationItemsComplete: boolean
}): Map<string, DerivedHistogram> {
  const histograms = new Map<string, DerivedHistogram>()
  if (!metricKeys.length) return histograms

  const localValues = populationItemsComplete
    ? collectMetricValuesByKey(items, metricKeys)
    : new Map<string, number[]>()
  for (const key of metricKeys) {
    const hasFacet = Object.prototype.hasOwnProperty.call(facets?.metrics ?? {}, key)
    const facetHistogram = metricHistogramFromFacet(facets?.metrics[key]?.histogram)
    const localHistogram = populationItemsComplete
      ? computeHistogramFromValues(getMetricValues(localValues, key), 32)
      : null
    const state = resolveFacetFieldState({
      facetDataState: !hasFacet ? 'absent' : facetHistogram ? 'ready' : 'empty',
      localDataState: !populationItemsComplete ? 'absent' : localHistogram ? 'ready' : 'empty',
      queryState: facetFieldQueryState(facetFieldStates, 'metrics', key, facetsState),
    })
    histograms.set(key, {
      histogram: hasFacet ? facetHistogram : localHistogram,
      state,
    })
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
