import {
  useCallback,
  useEffect,
  useState,
  type Dispatch,
  type SetStateAction,
} from 'react'
import { api } from '../../api/client'
import { normalizeFilterAst } from '../../features/browse/model/filters'
import type { SavedView, ViewState, ViewsPayload } from '../../lib/types'
import {
  SMART_FOLDER_NO_WRITE_MESSAGE,
  buildSmartFolderNoWriteExport,
  createSavedViewDraft,
  isSmartFolderNoWriteSaveError,
  shouldClearActiveSavedView,
} from '../model/smartFolders'
import { downloadBlob } from '../../lib/download'

type UseSmartFoldersParams = {
  current: string
  viewState: ViewState
  setViewState: Dispatch<SetStateAction<ViewState>>
  openFolder: (path: string) => void
}

type UseSmartFoldersResult = {
  views: SavedView[]
  activeViewId: string | null
  activateView: (view: SavedView) => void
  clearActiveView: () => void
  saveView: () => Promise<void>
}

export function useSmartFolders({
  current,
  viewState,
  setViewState,
  openFolder,
}: UseSmartFoldersParams): UseSmartFoldersResult {
  const [views, setViews] = useState<SavedView[]>([])
  const [activeViewId, setActiveViewId] = useState<string | null>(null)

  useEffect(() => {
    let alive = true
    api.getViews()
      .then((payload: ViewsPayload) => {
        if (!alive) return
        setViews(payload.views || [])
      })
      .catch(() => {
        if (!alive) return
        setViews([])
      })
    return () => {
      alive = false
    }
  }, [])

  const saveView = useCallback(async () => {
    if (typeof window === 'undefined') return
    const name = window.prompt('Save Smart Folder as:', 'New Smart Folder')
    if (!name) return
    const { id, nextViews } = createSavedViewDraft(name, views, current, viewState)
    setViews(nextViews)
    setActiveViewId(id)
    try {
      await api.saveViews({ version: 1, views: nextViews })
    } catch (error) {
      if (isSmartFolderNoWriteSaveError(error)) {
        const exportPayload = buildSmartFolderNoWriteExport(id, nextViews)
        const blob = new Blob([exportPayload.json], { type: exportPayload.type })
        downloadBlob(blob, exportPayload.filename)
        window.alert(SMART_FOLDER_NO_WRITE_MESSAGE)
        return
      }
      console.error('Failed to save Smart Folder:', error)
    }
  }, [current, viewState, views])

  useEffect(() => {
    if (shouldClearActiveSavedView(activeViewId, views, current, viewState)) {
      setActiveViewId(null)
    }
  }, [activeViewId, views, current, viewState])

  const activateView = useCallback((view: SavedView) => {
    setActiveViewId(view.id)
    const safeFilters = normalizeFilterAst(view.view?.filters) ?? { and: [] }
    setViewState({ ...view.view, filters: safeFilters })
    openFolder(view.pool.path)
  }, [openFolder, setViewState])

  const clearActiveView = useCallback(() => {
    setActiveViewId(null)
  }, [])

  return {
    views,
    activeViewId,
    activateView,
    clearActiveView,
    saveView,
  }
}
