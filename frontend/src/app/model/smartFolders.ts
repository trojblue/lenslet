import type { SavedView, ViewState, ViewsPayload } from '../../lib/types'
import { FetchError } from '../../lib/fetcher'
import { normalizeViewState } from '../../features/metrics/model/derivedMetric'
import { makeUniqueViewId } from '../utils/appShellHelpers'

export const SMART_FOLDER_NO_WRITE_MESSAGE = 'No-write mode: exported Smart Folder JSON instead of saving.'

export type SavedViewDraft = {
  id: string
  payload: SavedView
  nextViews: SavedView[]
}

export type SmartFolderExport = {
  filename: string
  json: string
  type: 'application/json'
}

export function createSavedViewDraft(
  name: string,
  views: SavedView[],
  current: string,
  viewState: ViewState,
): SavedViewDraft {
  const id = makeUniqueViewId(name, views)
  const payload: SavedView = {
    id,
    name,
    pool: { kind: 'folder', path: current },
    view: normalizeViewState(JSON.parse(JSON.stringify(viewState))),
  }
  return {
    id,
    payload,
    nextViews: [...views.filter((view) => view.id !== id), payload],
  }
}

export function shouldClearActiveSavedView(
  activeViewId: string | null,
  views: SavedView[],
  current: string,
  viewState: ViewState,
): boolean {
  if (!activeViewId) return false
  const view = views.find((candidate) => candidate.id === activeViewId)
  if (!view) return true
  return view.pool.path !== current
    || JSON.stringify(normalizeViewState(view.view)) !== JSON.stringify(normalizeViewState(viewState))
}

export function isSmartFolderNoWriteSaveError(error: unknown): boolean {
  return error instanceof FetchError && error.status === 403
}

export function buildSmartFolderNoWriteExport(id: string, views: SavedView[]): SmartFolderExport {
  return {
    filename: `lenslet-smart-folder-${id}.json`,
    json: JSON.stringify({ version: 1, views } satisfies ViewsPayload, null, 2),
    type: 'application/json',
  }
}
