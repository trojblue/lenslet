import { describe, expect, it } from 'vitest'
import { FetchError } from '../../../lib/fetcher'
import type { DerivedMetricSpec, SavedView, ViewState } from '../../../lib/types'
import {
  buildSmartFolderNoWriteExport,
  createSavedViewDraft,
  isSmartFolderNoWriteSaveError,
  shouldClearActiveSavedView,
} from '../smartFolders'

function makeViewState(overrides: Partial<ViewState> = {}): ViewState {
  return {
    filters: { and: [] },
    sort: { kind: 'builtin', key: 'added', dir: 'desc' },
    ...overrides,
  }
}

function makeSavedView(overrides: Partial<SavedView> = {}): SavedView {
  return {
    id: 'recent-cats',
    name: 'Recent cats',
    pool: { kind: 'folder', path: '/cats' },
    view: makeViewState(),
    ...overrides,
  }
}

function makeDerivedSpec(overrides: Partial<DerivedMetricSpec> = {}): DerivedMetricSpec {
  return {
    version: 1,
    id: 'rubric_1',
    name: 'Rubric score',
    intercept: 0,
    numericTerms: [{ key: 'q1', weight: 1, missing: 'invalid' }],
    categoricalTerms: [],
    ...overrides,
  }
}

describe('smart folder persistence helpers', () => {
  it('recognizes no-write save failures and builds the fallback export payload', () => {
    const views = [makeSavedView()]
    const fallback = buildSmartFolderNoWriteExport('recent-cats', views)

    expect(isSmartFolderNoWriteSaveError(new FetchError(403, 'forbidden', '/views'))).toBe(true)
    expect(isSmartFolderNoWriteSaveError(new FetchError(500, 'server error', '/views'))).toBe(false)
    expect(fallback.filename).toBe('lenslet-smart-folder-recent-cats.json')
    expect(fallback.type).toBe('application/json')
    expect(JSON.parse(fallback.json)).toEqual({ version: 1, views })
  })

  it('clears the active smart folder when its saved view is missing or stale', () => {
    const savedView = makeSavedView()
    const changedView = makeViewState({
      sort: { kind: 'builtin', key: 'name', dir: 'asc' },
    })

    expect(shouldClearActiveSavedView(null, [savedView], '/cats', savedView.view)).toBe(false)
    expect(shouldClearActiveSavedView('recent-cats', [savedView], '/cats', savedView.view)).toBe(false)
    expect(shouldClearActiveSavedView('missing', [savedView], '/cats', savedView.view)).toBe(true)
    expect(shouldClearActiveSavedView('recent-cats', [savedView], '/dogs', savedView.view)).toBe(true)
    expect(shouldClearActiveSavedView('recent-cats', [savedView], '/cats', changedView)).toBe(true)
  })

  it('roundtrips derived metric view state when saving a smart folder', () => {
    const viewState = makeViewState({
      sort: { kind: 'metric', key: '@derived/rubric_1', dir: 'desc' },
      selectedMetric: '@derived/rubric_1',
      derivedMetric: makeDerivedSpec(),
      filters: {
        and: [{ metricRange: { key: '@derived/rubric_1', min: 0, max: 10 } }],
      },
    })

    const draft = createSavedViewDraft('Recent cats', [], '/cats', viewState)

    expect(draft.payload.view).toEqual(viewState)
    expect(draft.nextViews[0].view).toEqual(viewState)
  })

  it('retains invalid saved derived definitions and marks changed definitions stale', () => {
    const invalidDerived = {
      version: 1,
      id: 'rubric_1',
      name: 'Saved score',
      intercept: null,
      numericTerms: [],
      categoricalTerms: [],
    }
    const savedView = makeSavedView({
      view: makeViewState({
        sort: { kind: 'metric', key: '@derived/rubric_1', dir: 'desc' },
        selectedMetric: '@derived/rubric_1',
        derivedMetric: invalidDerived,
      }),
    })
    const changedSpecView = makeViewState({
      sort: { kind: 'metric', key: '@derived/rubric_1', dir: 'desc' },
      selectedMetric: '@derived/rubric_1',
      derivedMetric: makeDerivedSpec({ intercept: 1 }),
    })

    expect(shouldClearActiveSavedView('recent-cats', [savedView], '/cats', savedView.view)).toBe(false)
    expect(savedView.view.derivedMetric).toEqual(invalidDerived)
    expect(shouldClearActiveSavedView('recent-cats', [savedView], '/cats', changedSpecView)).toBe(true)
  })
})
