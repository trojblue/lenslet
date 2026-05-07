import React, { useMemo, useState } from 'react'
import { mapItemsToRatings, toRatingsCsv, toRatingsJson } from '../../features/ratings/services/exportRatings'
import { FIND_SIMILAR_SELECT_SINGLE_REASON } from '../../features/inspector/model/findSimilarAvailability'
import { api } from '../../api/client'
import type { ContextMenuState, BrowseItemPayload } from '../../lib/types'
import ContextMenu, { type MenuItem } from './ContextMenu'
import { getPathName, isTrashPath } from '../routing/hash'
import { downloadBlob } from '../utils/appShellHelpers'

interface AppContextMenuItemsProps {
  ctx: ContextMenuState
  current: string
  items: BrowseItemPayload[]
  setCtx: (ctx: ContextMenuState | null) => void
  refreshEnabled: boolean
  refreshDisabledReason?: string | null
  onRefetch: () => Promise<unknown>
  onOpenMoveDialog: (paths: string[]) => void
  onRefreshFolder: (path: string) => Promise<void>
  canFindSimilar?: boolean
  findSimilarDisabledReason?: string | null
  onFindSimilar?: (path: string) => void
}

type ExportFormat = 'csv' | 'json'

export const REFRESH_UNAVAILABLE_LABEL = 'Refresh unavailable in current mode'
export const FIND_SIMILAR_UNAVAILABLE_LABEL = 'Find similar unavailable'

type RefreshMenuItemParams = {
  refreshing: boolean
  refreshEnabled: boolean
  refreshDisabledReason?: string | null
  onRefresh: () => void
}

export function buildRefreshMenuItem({
  refreshing,
  refreshEnabled,
  refreshDisabledReason,
  onRefresh,
}: RefreshMenuItemParams): MenuItem {
  const label = refreshEnabled
    ? (refreshing ? 'Refreshing…' : 'Refresh')
    : (refreshDisabledReason || REFRESH_UNAVAILABLE_LABEL)
  return {
    label,
    disabled: !refreshEnabled || refreshing,
    onClick: onRefresh,
  }
}

type FindSimilarMenuItemParams = {
  selectedPaths: string[]
  canFindSimilar: boolean
  findSimilarDisabledReason?: string | null
  onFindSimilar?: (path: string) => void
}

export function buildFindSimilarMenuItem({
  selectedPaths,
  canFindSimilar,
  findSimilarDisabledReason,
  onFindSimilar,
}: FindSimilarMenuItemParams): MenuItem | null {
  if (!onFindSimilar) return null
  const hasSingleSelection = selectedPaths.length === 1
  const path = hasSingleSelection ? selectedPaths[0] : null
  const disabledReason = hasSingleSelection
    ? (findSimilarDisabledReason || FIND_SIMILAR_UNAVAILABLE_LABEL)
    : (findSimilarDisabledReason || FIND_SIMILAR_SELECT_SINGLE_REASON)
  const enabled = hasSingleSelection && canFindSimilar && !!path
  return {
    label: enabled ? 'Find similar' : disabledReason,
    disabled: !enabled,
    onClick: () => {
      if (!enabled || !path) return
      onFindSimilar(path)
    },
  }
}

function getExportMime(format: ExportFormat): string {
  return format === 'csv' ? 'text/csv;charset=utf-8' : 'application/json;charset=utf-8'
}

function buildRatingsExportContent(items: BrowseItemPayload[], format: ExportFormat): string {
  const ratings = mapItemsToRatings(items)
  return format === 'csv' ? toRatingsCsv(ratings) : toRatingsJson(ratings)
}

function timestampLabel(): string {
  return new Date().toISOString().replace(/[:.]/g, '-')
}

async function fetchRecursiveFolderItems(path: string): Promise<BrowseItemPayload[]> {
  const payload = await api.getFolder(path, { recursive: true })
  return payload.items
}

export default function AppContextMenuItems({
  ctx,
  current,
  items,
  setCtx,
  refreshEnabled,
  refreshDisabledReason,
  onRefetch,
  onOpenMoveDialog,
  onRefreshFolder,
  canFindSimilar = false,
  findSimilarDisabledReason = null,
  onFindSimilar,
}: AppContextMenuItemsProps): JSX.Element {
  const inTrash = isTrashPath(current)
  const [refreshing, setRefreshing] = useState(false)
  const [exporting, setExporting] = useState<ExportFormat | null>(null)

  const selectedPaths = ctx.kind === 'grid' ? ctx.payload.paths : []

  const selectedItemsByPath = useMemo(
    () => new Map(items.map((item) => [item.path, item])),
    [items],
  )

  const closeMenu = (): void => {
    setCtx(null)
  }

  const handleRefresh = async (): Promise<void> => {
    const target = ctx.kind === 'tree' ? ctx.payload.path : '/'
    setRefreshing(true)
    try {
      await onRefreshFolder(target)
    } catch (error) {
      console.error('Failed to refresh folder:', error)
    } finally {
      setRefreshing(false)
      closeMenu()
    }
  }

  const handleFolderExport = (format: ExportFormat) => async (): Promise<void> => {
    setExporting(format)
    const folderPath = ctx.kind === 'tree' ? ctx.payload.path : current
    try {
      const folderItems = await fetchRecursiveFolderItems(folderPath)
      const content = buildRatingsExportContent(folderItems, format)
      const mime = getExportMime(format)
      const slug = folderPath === '/' ? 'root' : (folderPath.replace(/^\/+/, '') || 'root').replace(/\//g, '_')
      downloadBlob(new Blob([content], { type: mime }), `metadata_${slug}_${timestampLabel()}.${format}`)
    } catch (error) {
      console.error('Failed to export folder:', error)
      alert('Failed to export folder. See console for details.')
    } finally {
      setExporting(null)
      closeMenu()
    }
  }

  const handleSelectionExport = (format: ExportFormat) => async (): Promise<void> => {
    setExporting(format)
    try {
      const selectedSet = new Set(selectedPaths)
      const selectedItems = items.filter((item) => selectedSet.has(item.path))
      const content = buildRatingsExportContent(selectedItems, format)
      const mime = getExportMime(format)
      downloadBlob(new Blob([content], { type: mime }), `metadata_selection_${timestampLabel()}.${format}`)
    } finally {
      setExporting(null)
      closeMenu()
    }
  }

  const handleDownloadSelection = async (): Promise<void> => {
    if (!selectedPaths.length) return

    closeMenu()
    for (const path of selectedPaths) {
      try {
        const blob = await api.getFile(path)
        const name = selectedItemsByPath.get(path)?.name || getPathName(path) || 'image'
        downloadBlob(blob, name)
      } catch (error) {
        console.error(`Failed to download ${path}:`, error)
      }
    }
  }

  const handleMoveToTrash = async (): Promise<void> => {
    if (inTrash) return

    for (const path of selectedPaths) {
      try {
        await api.moveFile(path, '/_trash_')
      } catch (error) {
        console.error(`Failed to trash ${path}:`, error)
      }
    }
    void onRefetch()
    closeMenu()
  }

  const handlePermanentDelete = async (): Promise<void> => {
    if (!confirm(`Delete ${selectedPaths.length} file(s) permanently? This cannot be undone.`)) {
      return
    }
    try {
      await api.deleteFiles(selectedPaths)
    } catch (error) {
      console.error('Failed to delete files:', error)
    }
    void onRefetch()
    closeMenu()
  }

  const handleRecover = async (): Promise<void> => {
    for (const path of selectedPaths) {
      try {
        const sidecar = await api.getSidecar(path)
        const originalPath = sidecar.original_position
        const targetDir = originalPath
          ? originalPath.split('/').slice(0, -1).join('/') || '/'
          : '/'
        await api.moveFile(path, targetDir)
      } catch (error) {
        console.error(`Failed to recover ${path}:`, error)
      }
    }
    void onRefetch()
    closeMenu()
  }

  const menuItems: MenuItem[] = ctx.kind === 'tree'
    ? [
        buildRefreshMenuItem({
          refreshing,
          refreshEnabled,
          refreshDisabledReason,
          onRefresh: handleRefresh,
        }),
        {
          label: exporting === 'csv' ? 'Exporting CSV…' : 'Export metadata (CSV)',
          disabled: Boolean(exporting) || refreshing,
          onClick: handleFolderExport('csv'),
        },
        {
          label: exporting === 'json' ? 'Exporting JSON…' : 'Export metadata (JSON)',
          disabled: Boolean(exporting) || refreshing,
          onClick: handleFolderExport('json'),
        },
      ]
    : buildItemMenuItems({
        selectedPaths,
        inTrash,
        exporting,
        canFindSimilar,
        findSimilarDisabledReason,
        onFindSimilar: onFindSimilar
          ? (path: string) => {
              onFindSimilar(path)
              closeMenu()
            }
          : undefined,
        onDownloadSelection: handleDownloadSelection,
        onMoveSelection: onOpenMoveDialog,
        onMoveToTrash: handleMoveToTrash,
        onPermanentDelete: handlePermanentDelete,
        onRecover: handleRecover,
        onExportCsv: handleSelectionExport('csv'),
        onExportJson: handleSelectionExport('json'),
      })

  return <ContextMenu x={ctx.x} y={ctx.y} items={menuItems} />
}

interface BuildItemMenuItemsArgs {
  selectedPaths: string[]
  inTrash: boolean
  exporting: ExportFormat | null
  canFindSimilar: boolean
  findSimilarDisabledReason: string | null
  onFindSimilar?: (path: string) => void
  onDownloadSelection: () => Promise<void>
  onMoveSelection: (paths: string[]) => void
  onMoveToTrash: () => Promise<void>
  onPermanentDelete: () => Promise<void>
  onRecover: () => Promise<void>
  onExportCsv: () => Promise<void>
  onExportJson: () => Promise<void>
}

function buildItemMenuItems({
  selectedPaths,
  inTrash,
  exporting,
  canFindSimilar,
  findSimilarDisabledReason,
  onFindSimilar,
  onDownloadSelection,
  onMoveSelection,
  onMoveToTrash,
  onPermanentDelete,
  onRecover,
  onExportCsv,
  onExportJson,
}: BuildItemMenuItemsArgs): MenuItem[] {
  const items: MenuItem[] = []
  const findSimilarItem = buildFindSimilarMenuItem({
    selectedPaths,
    canFindSimilar,
    findSimilarDisabledReason,
    onFindSimilar,
  })

  if (findSimilarItem) {
    items.push(findSimilarItem)
  }

  if (selectedPaths.length) {
    items.push({
      label: selectedPaths.length > 1 ? `Download (${selectedPaths.length})` : 'Download',
      onClick: onDownloadSelection,
    })
  }

  if (selectedPaths.length) {
    items.push({
      label: 'Move to…',
      disabled: inTrash,
      onClick: () => {
        if (inTrash) return
        onMoveSelection(selectedPaths)
      },
    })
  }

  items.push({
    label: 'Move to trash',
    disabled: inTrash,
    onClick: onMoveToTrash,
  })

  if (inTrash) {
    items.push({
      label: 'Permanent delete',
      danger: true,
      onClick: onPermanentDelete,
    })

    items.push({
      label: 'Recover',
      onClick: onRecover,
    })
  }

  if (selectedPaths.length) {
    items.push({
      label: exporting === 'csv' ? 'Exporting CSV…' : 'Export metadata (CSV)',
      disabled: Boolean(exporting),
      onClick: onExportCsv,
    })

    items.push({
      label: exporting === 'json' ? 'Exporting JSON…' : 'Export metadata (JSON)',
      disabled: Boolean(exporting),
      onClick: onExportJson,
    })
  }

  return items
}
