import type { Item } from '../../../lib/types'

type VirtualRowLike = {
  index: number
}

type AdaptiveLayoutLike = {
  mode: 'adaptive'
  rows: Array<{ items: Array<{ item: Pick<Item, 'path'> }> }>
}

type GridLayoutLike = {
  mode: 'grid'
  columns: number
}

type LayoutLike = AdaptiveLayoutLike | GridLayoutLike

export function getAdjacentThumbPrefetchPaths(
  virtualRows: readonly VirtualRowLike[],
  layout: LayoutLike,
  items: readonly Pick<Item, 'path'>[],
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
    if (layout.mode === 'adaptive') {
      const rowData = layout.rows[rowIndex]
      if (!rowData) continue
      for (const rowItem of rowData.items) {
        paths.push(rowItem.item.path)
      }
      continue
    }
    const start = rowIndex * layout.columns
    const slice = items.slice(start, start + layout.columns)
    for (const item of slice) {
      paths.push(item.path)
    }
  }
  return Array.from(new Set(paths))
}
