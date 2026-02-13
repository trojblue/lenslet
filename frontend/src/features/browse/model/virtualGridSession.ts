import type { Item } from '../../../lib/types'

type GridLayoutLike = {
  mode: 'grid'
  columns: number
  rowH: number
}

type AdaptiveLayoutRowLike = {
  items: Array<{
    item: {
      path: string
    }
    originalIndex: number
  }>
}

type AdaptiveLayoutLike = {
  mode: 'adaptive'
  rows: AdaptiveLayoutRowLike[]
}

export type VirtualGridLayoutLike = GridLayoutLike | AdaptiveLayoutLike
export type VirtualRowLike = {
  index: number
  start?: number
  end?: number
  size?: number
}

export type AdaptiveRowMetric = {
  start: number
  height: number
}

export type VisibleGridCellLike = {
  path: string
  top: number
  left: number
  bottom: number
}

export type VirtualGridRestoreDecision = {
  source: 'selection' | 'top-anchor'
  path: string
  token: number
}

export function findAdaptiveRowIndex(
  rows: AdaptiveLayoutRowLike[],
  itemIndex: number,
): number {
  let low = 0
  let high = rows.length - 1

  while (low <= high) {
    const mid = (low + high) >> 1
    const row = rows[mid]
    const firstIndex = row.items[0]?.originalIndex ?? -1
    const lastIndex = row.items[row.items.length - 1]?.originalIndex ?? -1

    if (itemIndex >= firstIndex && itemIndex <= lastIndex) {
      return mid
    }
    if (itemIndex < firstIndex) {
      high = mid - 1
    } else {
      low = mid + 1
    }
  }

  return 0
}

export function collectVisiblePaths(
  items: Item[],
  layout: VirtualGridLayoutLike,
  virtualRows: readonly VirtualRowLike[],
): Set<string> {
  const next = new Set<string>()
  for (const row of virtualRows) {
    if (layout.mode === 'adaptive') {
      const rowData = layout.rows[row.index]
      if (!rowData) continue
      for (const rowItem of rowData.items) {
        next.add(rowItem.item.path)
      }
      continue
    }
    const start = row.index * layout.columns
    const end = Math.min(items.length, start + layout.columns)
    for (let index = start; index < end; index += 1) {
      const item = items[index]
      if (item) next.add(item.path)
    }
  }
  return next
}

export function getTopAnchorPathForVisibleRows(
  items: Item[],
  layout: VirtualGridLayoutLike,
  virtualRows: readonly VirtualRowLike[],
  scrollTop: number,
): string | null {
  const topRow = resolveTopVisibleRow(virtualRows, scrollTop)
  if (!topRow) return null

  if (layout.mode === 'adaptive') {
    return layout.rows[topRow.index]?.items[0]?.item.path ?? null
  }

  const itemIndex = topRow.index * layout.columns
  return items[itemIndex]?.path ?? null
}

export function getTopAnchorPathForVisibleCells(
  cells: readonly VisibleGridCellLike[],
  viewportTop: number,
  viewportBottom: number,
): string | null {
  let topPath: string | null = null
  let top = Number.POSITIVE_INFINITY
  let left = Number.POSITIVE_INFINITY

  for (const cell of cells) {
    if (!cell.path) continue
    if (cell.bottom <= viewportTop || cell.top >= viewportBottom) continue
    if (cell.top > top) continue
    if (cell.top === top && cell.left >= left) continue
    topPath = cell.path
    top = cell.top
    left = cell.left
  }

  return topPath
}

function resolveTopVisibleRow(
  virtualRows: readonly VirtualRowLike[],
  scrollTop: number,
): VirtualRowLike | null {
  if (virtualRows.length === 0) return null

  const targetTop = Math.max(0, scrollTop)
  for (const row of virtualRows) {
    const rowStart = row.start ?? 0
    const rowEnd = row.end ?? (rowStart + (row.size ?? 0))
    if (rowEnd > targetTop) {
      return row
    }
  }

  return virtualRows[0]
}

type ResolveRestoreDecisionParams = {
  selectionToken: number | undefined
  appliedSelectionToken: number
  selectedPath: string | null
  topAnchorToken: number | undefined
  appliedTopAnchorToken: number
  topAnchorPath: string | null
  hasPath: (path: string) => boolean
}

export function resolveVirtualGridRestoreDecision({
  selectionToken,
  appliedSelectionToken,
  selectedPath,
  topAnchorToken,
  appliedTopAnchorToken,
  topAnchorPath,
  hasPath,
}: ResolveRestoreDecisionParams): VirtualGridRestoreDecision | null {
  const normalizedSelectionToken = selectionToken ?? 0
  if (
    normalizedSelectionToken > 0
    && normalizedSelectionToken !== appliedSelectionToken
    && selectedPath
    && hasPath(selectedPath)
  ) {
    return {
      source: 'selection',
      path: selectedPath,
      token: normalizedSelectionToken,
    }
  }

  const normalizedTopAnchorToken = topAnchorToken ?? 0
  if (
    normalizedTopAnchorToken > 0
    && normalizedTopAnchorToken !== appliedTopAnchorToken
    && topAnchorPath
    && hasPath(topAnchorPath)
  ) {
    return {
      source: 'top-anchor',
      path: topAnchorPath,
      token: normalizedTopAnchorToken,
    }
  }

  return null
}

type GetRestoreScrollTopForPathParams = {
  path: string
  pathToIndex: ReadonlyMap<string, number>
  layout: VirtualGridLayoutLike
  adaptiveRowMeta: ReadonlyArray<AdaptiveRowMetric> | null
}

export function getRestoreScrollTopForPath({
  path,
  pathToIndex,
  layout,
  adaptiveRowMeta,
}: GetRestoreScrollTopForPathParams): number | null {
  const index = pathToIndex.get(path)
  if (index == null || index < 0) return null

  const rowIndex = layout.mode === 'grid'
    ? Math.floor(index / Math.max(1, layout.columns))
    : findAdaptiveRowIndex(layout.rows, index)

  if (layout.mode === 'grid') {
    return rowIndex * layout.rowH
  }

  return adaptiveRowMeta?.[rowIndex]?.start ?? 0
}
