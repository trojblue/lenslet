import React, { useRef, useState, useEffect, useLayoutEffect, useMemo } from 'react'
import { createPortal } from 'react-dom'
import { useVirtualizer } from '@tanstack/react-virtual'
import type { Item } from '../lib/types'
import Thumb from './Thumb'
import { api } from '../api/client'

export default function Grid({ items, selected, onSelectionChange, onOpenViewer, onContextMenuItem }:{ items: Item[]; selected: string[]; onSelectionChange:(paths:string[])=>void; onOpenViewer:(p:string)=>void; onContextMenuItem?:(e:React.MouseEvent, path:string)=>void }){
  const [previewFor, setPreviewFor] = useState<string | null>(null)
  const [previewUrl, setPreviewUrl] = useState<string | null>(null)
  const [hoverTimer, setHoverTimer] = useState<number | null>(null)
  const [delayPassed, setDelayPassed] = useState<boolean>(false)
  const [active, setActive] = useState<string | null>(null)
  const previewUrlRef = useRef<string | null>(null)
  const parentRef = useRef<HTMLDivElement | null>(null)
  const anchorRef = useRef<string | null>(null)

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

  // Fast lookup from path -> index for range selections
  const pathToIndex = useMemo(() => {
    const map = new Map<string, number>()
    for (let i = 0; i < items.length; i++) map.set(items[i].path, i)
    return map
  }, [items])

  const rowVirtualizer = useVirtualizer({
    count: rowCount,
    getScrollElement: () => parentRef.current,
    estimateSize: () => rowH,
    overscan: 8,
  })

  const rows = rowVirtualizer.getVirtualItems()

  // Native compositor-driven smooth scrolling helper
  const scrollRowIntoView = (el: HTMLElement, top: number) => {
    try { el.scrollTo({ top, behavior: 'smooth' }) }
    catch { el.scrollTop = top }
  }

  const [isScrolling, setIsScrolling] = useState(false)
  useEffect(() => {
    const el = parentRef.current
    if (!el) return
    let t: any = 0
    const onScroll = () => {
      setIsScrolling(true)
      window.clearTimeout(t)
      t = window.setTimeout(() => setIsScrolling(false), 120)
    }
    el.addEventListener('scroll', onScroll, { passive: true } as any)
    return () => el.removeEventListener('scroll', onScroll as any)
  }, [])

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
        onSelectionChange([nextItem.path])
        try { anchorRef.current = nextItem.path } catch {}
        // If the row is outside of the viewport, scroll it to the top
        const rowIdx = Math.floor(next / Math.max(1, columns))
        const scrollTop = el.scrollTop
        const viewBottom = scrollTop + el.clientHeight
        const rowTop = rowIdx * rowH
        const rowBottom = rowTop + rowH
        if (rowTop < scrollTop || rowBottom > viewBottom) {
          try { scrollRowIntoView(el, rowTop) }
          catch { try { rowVirtualizer.scrollToIndex(rowIdx, { align: 'start' as const }) } catch {} }
        }
      }
    }
    el.addEventListener('keydown', onKey)
    return () => { el.removeEventListener('keydown', onKey) }
  }, [items, active, columns, onOpenViewer])

  // Re-measure when layout parameters change
  useEffect(() => { rowVirtualizer.measure() }, [columns, rowH])

  const selectedSet = new Set(selected)

  const hasPreview = !!(previewFor && previewUrl && delayPassed)
  return (
    <div className={`grid${isScrolling ? ' is-scrolling' : ''}${hasPreview ? ' has-preview' : ''}`} ref={parentRef} tabIndex={0} style={{ ['--gap' as any]: `${GAP}px` }}>
      <div key={columns} className="grid-rows" style={{ height: rowVirtualizer.getTotalSize() }}>
        {rows.map(row => {
          const start = row.index * columns
          const slice = items.slice(start, start + columns)
          // Prefetch thumbnails for the next page worth of items when we render this row
          const nextPageStart = (row.index + 1) * columns
          const nextPageItems = items.slice(nextPageStart, nextPageStart + columns)
          for (const it of nextPageItems) { try { api.prefetchThumb(it.path) } catch {} }
          return (
            <div
              key={row.key}
              className="grid-row"
              style={{
                transform: `translate3d(0, ${row.start}px, 0)`,
                gridTemplateColumns: `repeat(${columns}, minmax(0, 1fr))`,
                containIntrinsicSize: `${rowH}px 100%` as any,
              }}
            >
              {slice.map(it => (
                <div
                  key={it.path}
                  className={`grid-cell ${(active===it.path || selectedSet.has(it.path)) ? 'is-selected' : ''}`}
                  draggable
                  onDragStart={(e)=>{
                    try {
                      const paths = selectedSet.has(it.path) && selected.length>0 ? selected : [it.path]
                      e.dataTransfer?.setData('application/x-lenscat-paths', JSON.stringify(paths))
                      if (e.dataTransfer) e.dataTransfer.effectAllowed = 'copyMove'
                      // mark drag-active to adjust tree hover visuals
                      try { document.body.classList.add('drag-active') } catch {}
                      // Create a lightweight drag image (semi-transparent thumb) positioned below cursor
                      const host = e.currentTarget as HTMLElement
                      const img = host.querySelector('.cell-content img') as HTMLImageElement | null
                      const ghost = document.createElement('div')
                      ghost.className = 'drag-ghost'
                      const ghostImg = document.createElement('img')
                      ghostImg.draggable = false
                      ghostImg.alt = 'drag'
                      // Prefer actual loaded thumb; otherwise let it remain empty
                      if (img && img.src) ghostImg.src = img.src
                      ghost.appendChild(ghostImg)
                      document.body.appendChild(ghost)
                      // Anchor cursor at top-center so the image sits below the pointer
                      const w = ghost.getBoundingClientRect().width || 150
                      e.dataTransfer!.setDragImage(ghost, Math.round(w/2), 0)
                      // cleanup on dragend
                      const cleanup = () => { try { ghost.remove() } catch {} ; try { document.body.classList.remove('drag-active') } catch {} ; window.removeEventListener('dragend', cleanup) }
                      window.addEventListener('dragend', cleanup)
                    } catch {}
                  }}
                  onDragEnd={()=>{ /* cleanup happens via window listener above */ }}
                  onContextMenu={(e)=>{ e.preventDefault(); e.stopPropagation(); if (onContextMenuItem) onContextMenuItem(e, it.path) }}
                >
                  <div
                    className="cell-media"
                    onMouseEnter={()=>{ try { api.prefetchFile(it.path) } catch {} }}
                    onDoubleClick={()=> onOpenViewer(it.path)}
                    onMouseLeave={()=>{
                      if (hoverTimer) { window.clearTimeout(hoverTimer); setHoverTimer(null) }
                      setPreviewFor(null)
                      if (previewUrlRef.current) { try { URL.revokeObjectURL(previewUrlRef.current) } catch {} ; previewUrlRef.current = null }
                      setPreviewUrl(null)
                      setDelayPassed(false)
                    }}
                  >
                    <div className="cell-content">
                      <Thumb
                        path={it.path}
                        name={it.name}
                        selected={(active===it.path) || selectedSet.has(it.path)}
                        displayW={cellW}
                        displayH={mediaH}
                        onClick={(ev: React.MouseEvent)=>{
                          setActive(it.path)
                          const isShift = !!ev.shiftKey
                          const isToggle = !!(ev.ctrlKey || ev.metaKey)

                          if (isShift) {
                            const anchorPath = anchorRef.current ?? active ?? (selected[0] ?? it.path)
                            const aIdx = pathToIndex.get(anchorPath) ?? items.findIndex(i => i.path === anchorPath)
                            const bIdx = pathToIndex.get(it.path) ?? items.findIndex(i => i.path === it.path)
                            if (aIdx !== -1 && bIdx !== -1) {
                              const start = Math.min(aIdx, bIdx)
                              const end = Math.max(aIdx, bIdx)
                              const range = items.slice(start, end + 1).map(x => x.path)
                              if (isToggle) {
                                const next = new Set(selected)
                                for (const p of range) next.add(p)
                                onSelectionChange(Array.from(next))
                              } else {
                                onSelectionChange(range)
                              }
                            } else {
                              onSelectionChange([it.path])
                            }
                            // Preserve existing anchor on shift to allow repeated range selections
                          } else if (isToggle) {
                            const next = new Set(selected)
                            if (next.has(it.path)) next.delete(it.path); else next.add(it.path)
                            onSelectionChange(Array.from(next))
                            try { anchorRef.current = it.path } catch {}
                          } else {
                            onSelectionChange([it.path])
                            try { anchorRef.current = it.path } catch {}
                          }

                          try { api.prefetchFile(it.path); api.prefetchThumb(it.path) } catch {}
                        }}
                      />
                    </div>
                    <div
                      className="cell-zoom-hit"
                      onMouseEnter={async ()=>{
                        if (isScrolling) return
                        if (hoverTimer) window.clearTimeout(hoverTimer)
                        setPreviewFor(it.path)
                        setDelayPassed(false)
                        try {
                          const blob = await api.getFile(it.path)
                          const u = URL.createObjectURL(blob)
                          if (previewUrlRef.current) { try { URL.revokeObjectURL(previewUrlRef.current) } catch {} }
                          previewUrlRef.current = u
                          setPreviewUrl(u)
                        } catch {}
                        const t = window.setTimeout(()=>{ setDelayPassed(true) }, 350)
                        setHoverTimer(t as any)
                      }}
                      onMouseLeave={()=>{
                        if (hoverTimer) window.clearTimeout(hoverTimer)
                        setHoverTimer(null)
                        setDelayPassed(false)
                        setPreviewFor(null)
                        if (previewUrlRef.current) { try { URL.revokeObjectURL(previewUrlRef.current) } catch {} ; previewUrlRef.current = null }
                        setPreviewUrl(null)
                      }}
                    >
                      <div className="cell-zoom">🔍</div>
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
        {previewFor && previewUrl && delayPassed && createPortal(
          <div className="preview-backdrop is-active">
            <img src={previewUrl} alt="preview" className="preview-img" />
          </div>,
          document.body
        )}
      </div>
    </div>
  )
}
