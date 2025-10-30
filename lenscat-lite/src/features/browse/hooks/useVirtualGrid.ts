import { useEffect, useLayoutEffect, useMemo, useState } from 'react'
import { useVirtualizer } from '@tanstack/react-virtual'
import { flatLayout } from '../model/layouts'

export function useVirtualGrid(containerRef: React.RefObject<HTMLElement | null>, itemCount: number, opts: { gap:number; targetCell:number; aspect:{w:number,h:number}; captionH:number }) {
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

  const { columns, cellW, mediaH, rowH } = flatLayout({ containerW: width, gap: opts.gap, targetCell: opts.targetCell, aspect: opts.aspect, captionH: opts.captionH })
  const rowCount = Math.ceil(itemCount / Math.max(1, columns))
  const rowVirtualizer = useVirtualizer({ count: rowCount, getScrollElement: () => containerRef.current as any, estimateSize: () => rowH, overscan: 8 })
  const rows = rowVirtualizer.getVirtualItems()
  useEffect(() => { rowVirtualizer.measure() }, [columns, rowH])
  return { width, columns, cellW, mediaH, rowH, rowVirtualizer, rows }
}


