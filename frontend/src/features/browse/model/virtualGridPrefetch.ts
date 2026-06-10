import type { BrowseItemPayload } from '../../../lib/types'

type VirtualRowLike = {
  index: number
  start?: number
  end?: number
  size?: number
}

type AdaptiveLayoutLike = {
  mode: 'adaptive'
  rows: Array<{ items: Array<{ item: Pick<BrowseItemPayload, 'path'> }> }>
}

type GridLayoutLike = {
  mode: 'grid'
  columns: number
}

type LayoutLike = AdaptiveLayoutLike | GridLayoutLike

function collectRowPaths(
  rowIndex: number,
  layout: LayoutLike,
  items: readonly Pick<BrowseItemPayload, 'path'>[],
): string[] {
  if (layout.mode === 'adaptive') {
    const rowData = layout.rows[rowIndex]
    return rowData ? rowData.items.map((rowItem) => rowItem.item.path) : []
  }

  const columns = Math.max(1, layout.columns)
  const start = rowIndex * columns
  return items.slice(start, start + columns).map((item) => item.path)
}

export function getAdjacentThumbPrefetchPaths(
  virtualRows: readonly VirtualRowLike[],
  layout: LayoutLike,
  items: readonly Pick<BrowseItemPayload, 'path'>[],
): string[] {
  if (virtualRows.length === 0) return []
  const visibleRows = Array.from(new Set(virtualRows.map((row) => row.index))).sort((a, b) => a - b)
  const minVisible = visibleRows[0]
  const maxVisible = visibleRows[visibleRows.length - 1]

  const maxRowIndex = (() => {
    if (layout.mode === 'adaptive') {
      return Math.max(0, layout.rows.length - 1)
    }
    return Math.max(0, Math.ceil(items.length / Math.max(1, layout.columns)) - 1)
  })()

  const candidateRows = [minVisible - 1, maxVisible + 1].filter((rowIndex) => (
    rowIndex >= 0 && rowIndex <= maxRowIndex
  ))
  if (candidateRows.length === 0) return []

  const paths: string[] = []
  for (const rowIndex of candidateRows) {
    paths.push(...collectRowPaths(rowIndex, layout, items))
  }
  return Array.from(new Set(paths))
}

function rowIntersectsViewport(
  row: VirtualRowLike,
  viewportTop: number,
  viewportBottom: number,
): boolean {
  if (row.start == null) return true
  const rowEnd = row.end ?? (row.start + (row.size ?? 0))
  return rowEnd > viewportTop && row.start < viewportBottom
}

export function getDemandThumbPaths(
  virtualRows: readonly VirtualRowLike[],
  layout: LayoutLike,
  items: readonly Pick<BrowseItemPayload, 'path'>[],
  viewportTop: number,
  viewportHeight: number,
): string[] {
  if (virtualRows.length === 0) return []
  const viewportBottom = viewportTop + Math.max(0, viewportHeight)
  const paths: string[] = []

  for (const row of virtualRows) {
    if (!rowIntersectsViewport(row, viewportTop, viewportBottom)) continue
    paths.push(...collectRowPaths(row.index, layout, items))
  }

  return Array.from(new Set(paths))
}
