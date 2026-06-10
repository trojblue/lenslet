import React, { useMemo, useState } from 'react'
import { mapItemsToRatings, toRatingsCsv, toRatingsJson } from '../../features/ratings/services/exportRatings'
import { FIND_SIMILAR_SELECT_SINGLE_REASON } from '../../features/inspector/model/findSimilarAvailability'
import { api } from '../../api/client'
import type { ContextMenuState, BrowseItemPayload } from '../../lib/types'
import ContextMenu, { type MenuItem } from './ContextMenu'
import { getPathName } from '../routing/hash'
import { downloadBlob } from '../../lib/download'

interface AppContextMenuItemsProps {
  ctx: ContextMenuState
  current: string
  items: BrowseItemPayload[]
  setCtx: (ctx: ContextMenuState | null) => void
  refreshEnabled: boolean
  refreshDisabledReason?: string | null
  onRefreshFolder: (path: string) => Promise<void>
  canFindSimilar?: boolean
  findSimilarDisabledReason?: string | null
  onFindSimilar?: (path: string) => void
  onActionStart?: () => void
  onActionError?: (action: string, error: unknown) => void
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

type SelectionExportHandlerParams = {
  format: ExportFormat
  selectedPaths: string[]
  items: BrowseItemPayload[]
  setExporting: (format: ExportFormat | null) => void
  closeMenu: () => void
  download: typeof downloadBlob
  timestamp: () => string
  onActionStart?: () => void
  onActionError?: (action: string, error: unknown) => void
}

export function buildSelectionExportHandler({
  format,
  selectedPaths,
  items,
  setExporting,
  closeMenu,
  download,
  timestamp,
  onActionStart,
  onActionError,
}: SelectionExportHandlerParams): () => void {
  return () => {
    setExporting(format)
    onActionStart?.()
    try {
      const selectedSet = new Set(selectedPaths)
      const selectedItems = items.filter((item) => selectedSet.has(item.path))
      const content = buildRatingsExportContent(selectedItems, format)
      const mime = getExportMime(format)
      download(new Blob([content], { type: mime }), `metadata_selection_${timestamp()}.${format}`)
    } catch (error) {
      onActionError?.('Export selection metadata failed', error)
    } finally {
      setExporting(null)
      closeMenu()
    }
  }
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
  onRefreshFolder,
  canFindSimilar = false,
  findSimilarDisabledReason = null,
  onFindSimilar,
  onActionStart,
  onActionError,
}: AppContextMenuItemsProps): JSX.Element {
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
    onActionStart?.()
    try {
      await onRefreshFolder(target)
    } catch (error) {
      onActionError?.('Refresh folder failed', error)
    } finally {
      setRefreshing(false)
      closeMenu()
    }
  }

  const handleFolderExport = (format: ExportFormat) => async (): Promise<void> => {
    setExporting(format)
    onActionStart?.()
    const folderPath = ctx.kind === 'tree' ? ctx.payload.path : current
    try {
      const folderItems = await fetchRecursiveFolderItems(folderPath)
      const content = buildRatingsExportContent(folderItems, format)
      const mime = getExportMime(format)
      const slug = folderPath === '/' ? 'root' : (folderPath.replace(/^\/+/, '') || 'root').replace(/\//g, '_')
      downloadBlob(new Blob([content], { type: mime }), `metadata_${slug}_${timestampLabel()}.${format}`)
    } catch (error) {
      onActionError?.('Export folder metadata failed', error)
    } finally {
      setExporting(null)
      closeMenu()
    }
  }

  const handleSelectionExport = (format: ExportFormat): (() => void) => buildSelectionExportHandler({
    format,
    selectedPaths,
    items,
    setExporting,
    closeMenu,
    download: downloadBlob,
    timestamp: timestampLabel,
    onActionStart,
    onActionError,
  })

  const handleDownloadSelection = async (): Promise<void> => {
    if (!selectedPaths.length) return

    closeMenu()
    onActionStart?.()
    const failures: unknown[] = []
    for (const path of selectedPaths) {
      try {
        const blob = await api.getFile(path)
        const name = selectedItemsByPath.get(path)?.name || getPathName(path) || 'image'
        downloadBlob(blob, name)
      } catch (error) {
        failures.push(error)
      }
    }
    if (failures.length) {
      const action = failures.length === selectedPaths.length
        ? 'Download failed'
        : `${failures.length} download${failures.length === 1 ? '' : 's'} failed`
      onActionError?.(action, failures[0])
    }
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
        onExportCsv: handleSelectionExport('csv'),
        onExportJson: handleSelectionExport('json'),
      })

  return <ContextMenu x={ctx.x} y={ctx.y} items={menuItems} />
}

interface BuildItemMenuItemsArgs {
  selectedPaths: string[]
  exporting: ExportFormat | null
  canFindSimilar: boolean
  findSimilarDisabledReason: string | null
  onFindSimilar?: (path: string) => void
  onDownloadSelection: () => Promise<void>
  onExportCsv: () => void
  onExportJson: () => void
}

function buildItemMenuItems({
  selectedPaths,
  exporting,
  canFindSimilar,
  findSimilarDisabledReason,
  onFindSimilar,
  onDownloadSelection,
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
