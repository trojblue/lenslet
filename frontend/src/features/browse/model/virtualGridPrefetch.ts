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

export function getVisibleThumbPrefetchPaths(
  virtualRows: readonly VirtualRowLike[],
  layout: LayoutLike,
  items: readonly Pick<Item, 'path'>[],
): string[] {
  const paths: string[] = []
  for (const row of virtualRows) {
    if (layout.mode === 'adaptive') {
      const rowData = layout.rows[row.index]
      if (!rowData) continue
      for (const rowItem of rowData.items) {
        paths.push(rowItem.item.path)
      }
      continue
    }
    const start = row.index * layout.columns
    const slice = items.slice(start, start + layout.columns)
    for (const item of slice) {
      paths.push(item.path)
    }
  }
  return Array.from(new Set(paths))
}
