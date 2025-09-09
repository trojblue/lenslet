import React, { useMemo, useRef } from 'react'
import { useVirtualizer } from '@tanstack/react-virtual'
import type { Item } from '../lib/types'
import Thumb from './Thumb'

export default function Grid({ items, onOpen }:{ items: Item[]; onOpen:(p:string)=>void }){
  const parentRef = useRef<HTMLDivElement | null>(null)
  const columnWidth = 220 // includes padding/gap; adjust with CSS
  const gap = 12
  const columns = Math.max(1, Math.floor((parentRef.current?.clientWidth ?? 800) / (columnWidth + gap)))
  const rowCount = Math.ceil(items.length / columns)

  const rowVirtualizer = useVirtualizer({
    count: rowCount,
    getScrollElement: () => parentRef.current,
    estimateSize: () => columnWidth + gap,
    overscan: 4
  })

  const rows = rowVirtualizer.getVirtualItems()

  return (
    <div className="grid" ref={parentRef}>
      <div style={{ height: rowVirtualizer.getTotalSize(), width: '100%', position: 'relative' }}>
        {rows.map(row => {
          const start = row.index * columns
          const slice = items.slice(start, start + columns)
          return (
            <div key={row.key} style={{ position: 'absolute', top: 0, left: 0, transform: `translateY(${row.start}px)`, display: 'grid', gridTemplateColumns: `repeat(${columns}, 1fr)`, gap }}>
              {slice.map(it => (
                <Thumb key={it.path} path={it.path} name={it.name} onClick={()=>onOpen(it.path)} />
              ))}
            </div>
          )
        })}
      </div>
    </div>
  )
}
