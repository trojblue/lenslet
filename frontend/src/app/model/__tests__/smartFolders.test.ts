import { describe, expect, it } from 'vitest'
import { FetchError } from '../../../lib/fetcher'
import type { SavedView, ViewState } from '../../../lib/types'
import {
  buildSmartFolderNoWriteExport,
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
})
