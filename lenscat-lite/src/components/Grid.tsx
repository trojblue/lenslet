import React, { useRef, useState, useEffect, useLayoutEffect } from 'react'
import { useVirtualizer } from '@tanstack/react-virtual'
import type { Item } from '../lib/types'
import Thumb from './Thumb'
import { api } from '../api/client'

export default function Grid({ items, onOpen, onOpenViewer }:{ items: Item[]; onOpen:(p:string)=>void; onOpenViewer:(p:string)=>void }){
  const [previewFor, setPreviewFor] = useState<string | null>(null)
  const [previewUrl, setPreviewUrl] = useState<string | null>(null)
  const [hoverTimer, setHoverTimer] = useState<number | null>(null)
  const [active, setActive] = useState<string | null>(null)
  const parentRef = useRef<HTMLDivElement | null>(null)

  // Track container width accurately
  const [width, setWidth] = useState(0)
  useLayoutEffect(() => {
    const el = parentRef.current
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

  const GAP = 12
  const TARGET_CELL = 220
  const ASPECT = { w: 4, h: 3 } // width : height
  const CAPTION_H = 44 // px reserved for filename + size

  const columns = Math.max(1, Math.floor((width + GAP) / (TARGET_CELL + GAP)))
  const cellW   = (width - GAP * (columns - 1)) / columns
  const mediaH  = (cellW * ASPECT.h) / ASPECT.w
  const rowH    = mediaH + CAPTION_H + GAP // media + caption + gap

  const rowCount = Math.ceil(items.length / Math.max(1, columns))

  const rowVirtualizer = useVirtualizer({
    count: rowCount,
    getScrollElement: () => parentRef.current,
    estimateSize: () => rowH,
    overscan: 6,
  })

  const rows = rowVirtualizer.getVirtualItems()

  // Snappy smooth scroll helper (~150ms)
  const smoothScrollTo = (el: HTMLElement, top: number, duration = 150) => {
    const start = el.scrollTop
    const delta = top - start
    if (Math.abs(delta) < 2) { el.scrollTop = top; return }
    const startTs = performance.now()
    const step = (now: number) => {
      const t = Math.min(1, (now - startTs) / duration)
      // easeOutCubic
      const eased = 1 - Math.pow(1 - t, 3)
      el.scrollTop = start + delta * eased
      if (t < 1) requestAnimationFrame(step)
    }
    requestAnimationFrame(step)
  }

  useEffect(() => {
    const el = parentRef.current
    if (!el) return
    const onKey = (e: KeyboardEvent) => {
      if (!items.length) return
      const idx = active ? items.findIndex(i => i.path === active) : 0
      const col = Math.max(1, columns)
      let next = idx
      if (e.key === 'ArrowRight' || e.key === 'd') next = Math.min(items.length - 1, idx + 1)
      else if (e.key === 'ArrowLeft' || e.key === 'a') next = Math.max(0, idx - 1)
      else if (e.key === 'ArrowDown' || e.key === 's') next = Math.min(items.length - 1, idx + col)
      else if (e.key === 'ArrowUp' || e.key === 'w') next = Math.max(0, idx - col)
      else if (e.key === 'Enter') { if (active) onOpenViewer(active); return }
      else return
      e.preventDefault()
      const nextItem = items[next]
      if (nextItem) {
        setActive(nextItem.path)
        onOpen(nextItem.path)
        // If the row is outside of the viewport, scroll it to the top
        const rowIdx = Math.floor(next / Math.max(1, columns))
        const scrollTop = el.scrollTop
        const viewBottom = scrollTop + el.clientHeight
        const rowTop = rowIdx * rowH
        const rowBottom = rowTop + rowH
        if (rowTop < scrollTop || rowBottom > viewBottom) {
          try { smoothScrollTo(el, rowTop, 150) }
          catch { try { rowVirtualizer.scrollToIndex(rowIdx, { align: 'start' as const }) } catch {} }
        }
      }
    }
    el.addEventListener('keydown', onKey)
    return () => { el.removeEventListener('keydown', onKey) }
  }, [items, active, columns, onOpen, onOpenViewer])

  // Re-measure when layout parameters change
  useEffect(() => { rowVirtualizer.measure() }, [columns, rowH])

  return (
    <div className="grid" ref={parentRef} tabIndex={0} style={{ ['--gap' as any]: `${GAP}px` }}>
      <div key={columns} className="grid-rows" style={{ height: rowVirtualizer.getTotalSize() }}>
        {rows.map(row => {
          const start = row.index * columns
          const slice = items.slice(start, start + columns)
          return (
            <div
              key={row.key}
              className="grid-row"
              style={{
                transform: `translate3d(0, ${row.start}px, 0)`,
                gridTemplateColumns: `repeat(${columns}, minmax(0, 1fr))`,
              }}
            >
              {slice.map(it => (
                <div
                  key={it.path}
                  className={`grid-cell ${active===it.path ? 'is-selected' : ''}`}
                >
                  <div
                    className="cell-media"
                    onDoubleClick={()=> onOpenViewer(it.path)}
                    onMouseLeave={()=>{ if (hoverTimer) { window.clearTimeout(hoverTimer); setHoverTimer(null) }; setPreviewFor(null); setPreviewUrl(null) }}
                  >
                    <div className="cell-content">
                      <Thumb path={it.path} name={it.name} selected={active===it.path} onClick={()=>{ setActive(it.path); onOpen(it.path) }} />
                    </div>
                    <div
                      className="cell-zoom"
                      onMouseEnter={async ()=>{
                        if (hoverTimer) window.clearTimeout(hoverTimer)
                        setPreviewFor(it.path)
                        try {
                          const blob = await api.getFile(it.path)
                          setPreviewUrl(URL.createObjectURL(blob))
                        } catch {}
                        const t = window.setTimeout(()=>{}, 200)
                        setHoverTimer(t)
                      }}
                      onMouseLeave={()=>{ if (hoverTimer) window.clearTimeout(hoverTimer); setHoverTimer(null); setPreviewFor(null); setPreviewUrl(null) }}
                    >
                      🔍
                    </div>
                  </div>
                  <div className="cell-caption">
                    <div className="filename" title={it.name}>{it.name}</div>
                    <div className="filesize">{it.w} × {it.h}</div>
                  </div>
                </div>
              ))}
            </div>
          )
        })}
        {previewFor && previewUrl && (
          <div className="preview-backdrop">
            <img src={previewUrl} alt="preview" className="preview-img" />
          </div>
        )}
      </div>
    </div>
  )
}
