import { useEffect, useLayoutEffect, useMemo, useState } from 'react'
import { useVirtualizer } from '@tanstack/react-virtual'
import { flatLayout } from '../model/layouts'
import { computeAdaptiveRows } from '../model/adaptive'
import type { Item, ViewMode } from '../../../lib/types'

type GridOptions = {
  gap: number
  targetCell: number
  aspect: { w: number; h: number }
  captionH: number
  viewMode: ViewMode
}

type AdaptiveLayout = { mode: 'adaptive'; rows: ReturnType<typeof computeAdaptiveRows> }
type GridLayout = {
  mode: 'grid'
  columns: number
  cellW: number
  mediaH: number
  rowH: number
  rowCount: number
}

type Layout = AdaptiveLayout | GridLayout

function buildAdaptiveLayout(width: number, items: Item[], opts: GridOptions): AdaptiveLayout {
  const rows = computeAdaptiveRows({
    items,
    containerWidth: width,
    targetHeight: opts.targetCell,
    gap: opts.gap,
    captionH: opts.captionH,
  })
  return { mode: 'adaptive', rows }
}

function buildGridLayout(width: number, items: Item[], opts: GridOptions): GridLayout {
  const { columns, cellW, mediaH, rowH } = flatLayout({
    containerW: width,
    gap: opts.gap,
    targetCell: opts.targetCell,
    aspect: opts.aspect,
    captionH: opts.captionH,
  })
  const rowCount = Math.ceil(items.length / Math.max(1, columns))
  return { mode: 'grid', columns, cellW, mediaH, rowH, rowCount }
}

export function useVirtualGrid(
  containerRef: React.RefObject<HTMLElement | null>,
  items: Item[],
  opts: GridOptions
) {
  const [width, setWidth] = useState(0)
  useLayoutEffect(() => {
    const el = containerRef.current as HTMLElement | null
    if (!el) return
    const measure = () => {
      const cs = getComputedStyle(el)
      const inner = el.clientWidth - parseFloat(cs.paddingLeft) - parseFloat(cs.paddingRight)
      setWidth(inner)
    }
    const ro = new ResizeObserver(measure)
    ro.observe(el)
    measure()
    return () => ro.disconnect()
  }, [])

  const layout: Layout = useMemo(() => {
    return opts.viewMode === 'adaptive'
      ? buildAdaptiveLayout(width, items, opts)
      : buildGridLayout(width, items, opts)
  }, [width, items, opts.viewMode, opts.gap, opts.targetCell, opts.aspect.w, opts.aspect.h, opts.captionH])

  const rowVirtualizer = useVirtualizer({
    count: layout.mode === 'adaptive' ? layout.rows.length : layout.rowCount,
    getScrollElement: () => containerRef.current as any,
    estimateSize: (i) => layout.mode === 'adaptive' ? layout.rows[i].height : layout.rowH,
    overscan: 8,
  })

  const virtualRows = rowVirtualizer.getVirtualItems()
  
  useEffect(() => { rowVirtualizer.measure() }, [layout, rowVirtualizer])
  
  return { width, layout, rowVirtualizer, virtualRows }
}
