import React, { useRef, useState, useEffect, useLayoutEffect, useMemo } from 'react'
import { createPortal } from 'react-dom'
import type { Item } from '../../../lib/types'
import ThumbCard from './ThumbCard'
import { api } from '../../../shared/api/client'
import { flatLayout } from '../model/layouts'
import { useVirtualGrid } from '../hooks/useVirtualGrid'
import { getNextIndexForKeyNav } from '../hooks/useKeyboardNav'

export default function VirtualGrid({ items, selected, restoreToSelectionToken, onSelectionChange, onOpenViewer, onContextMenuItem, highlight }:{ items: Item[]; selected: string[]; restoreToSelectionToken?: number; onSelectionChange:(paths:string[])=>void; onOpenViewer:(p:string)=>void; onContextMenuItem?:(e:React.MouseEvent, path:string)=>void; highlight?: string }){
  const [previewFor, setPreviewFor] = useState<string | null>(null)
  const [previewUrl, setPreviewUrl] = useState<string | null>(null)
  const [hoverTimer, setHoverTimer] = useState<number | null>(null)
  const [delayPassed, setDelayPassed] = useState<boolean>(false)
  const [active, setActive] = useState<string | null>(null)
  const [focused, setFocused] = useState<string | null>(null)
  const previewUrlRef = useRef<string | null>(null)
  const parentRef = useRef<HTMLDivElement | null>(null)
  const anchorRef = useRef<string | null>(null)

  const GAP = 12
  const TARGET_CELL = 220
  const ASPECT = { w: 4, h: 3 }
  const CAPTION_H = 44

  const { columns, cellW, mediaH, rowH, rowVirtualizer, rows } = useVirtualGrid(parentRef as any, items.length, { gap: GAP, targetCell: TARGET_CELL, aspect: ASPECT, captionH: CAPTION_H })

  const pathToIndex = useMemo(() => {
    const map = new Map<string, number>()
    for (let i = 0; i < items.length; i++) map.set(items[i].path, i)
    return map
  }, [items])

  

  const scrollAnimRef = useRef<number | null>(null)
  const scrollRowIntoView = (el: HTMLElement, top: number) => {
    try {
      if (scrollAnimRef.current != null) { try { cancelAnimationFrame(scrollAnimRef.current) } catch {} ; scrollAnimRef.current = null }
      const start = el.scrollTop
      const delta = top - start
      if (Math.abs(delta) < 1) { el.scrollTop = top; return }
      const D = 140
      const t0 = performance.now()
      const easeOutCubic = (t: number) => 1 - Math.pow(1 - t, 3)
      const step = (now: number) => {
        const p = Math.min(1, (now - t0) / D)
        const eased = easeOutCubic(p)
        el.scrollTop = start + delta * eased
        if (p < 1) { scrollAnimRef.current = requestAnimationFrame(step) } else { scrollAnimRef.current = null }
      }
      scrollAnimRef.current = requestAnimationFrame(step)
    } catch { el.scrollTop = top }
  }

  const [isScrolling, setIsScrolling] = useState(false)
  useEffect(() => {
    const el = parentRef.current
    if (!el) return
    let t: any = 0
    const onScroll = () => { setIsScrolling(true); window.clearTimeout(t); t = window.setTimeout(() => setIsScrolling(false), 120) }
    el.addEventListener('scroll', onScroll, { passive: true } as any)
    return () => el.removeEventListener('scroll', onScroll as any)
  }, [])

  useEffect(() => {
    const el = parentRef.current
    if (!el) return
    const onKey = (e: KeyboardEvent) => {
      const result = getNextIndexForKeyNav(items, Math.max(1, columns), focused, e)
      if (result == null) return
      e.preventDefault()
      if (result === 'open') { if (focused) onOpenViewer(focused); return }
      const next = result
      const nextItem = items[next]
      if (!nextItem) return
      setFocused(nextItem.path)
      setActive(nextItem.path)
      onSelectionChange([nextItem.path])
      try { anchorRef.current = nextItem.path } catch {}
      const rowIdx = Math.floor(next / Math.max(1, columns))
      const scrollTop = el.scrollTop
      const viewBottom = scrollTop + el.clientHeight
      const rowTop = rowIdx * rowH
      const rowBottom = rowTop + rowH
      if (rowTop < scrollTop || rowBottom > viewBottom) {
        try { scrollRowIntoView(el, rowTop) }
        catch { try { rowVirtualizer.scrollToIndex(rowIdx, { align: 'start' as const }) } catch {} }
      }
      try { (document.getElementById(`cell-${encodeURIComponent(nextItem.path)}`) as HTMLElement | null)?.focus() } catch {}
    }
    el.addEventListener('keydown', onKey)
    return () => { el.removeEventListener('keydown', onKey) }
  }, [items, focused, columns, onOpenViewer, rowH])

  // measure handled in hook

  useLayoutEffect(() => {
    const el = parentRef.current
    if (!el) return
    if (!restoreToSelectionToken) return
    if (!selected || selected.length === 0) return
    const first = selected[0]
    const idx = pathToIndex.get(first)
    if (idx == null || idx < 0) return
    const col = Math.max(1, columns)
    const rowIdx = Math.floor(idx / col)
    const targetTop = rowIdx * rowH
    try { el.scrollTop = targetTop } catch {}
  }, [restoreToSelectionToken])

  const selectedSet = new Set(selected)
  const hasPreview = !!(previewFor && previewUrl && delayPassed)
  useEffect(() => { parentRef.current?.focus() }, [])

  const activeDescendantId = focused ? `cell-${encodeURIComponent(focused)}` : undefined

  return (
    <div role="grid" aria-label="Gallery" className={`grid${isScrolling ? ' is-scrolling' : ''}${hasPreview ? ' has-preview' : ''}`} ref={parentRef} tabIndex={0} aria-activedescendant={activeDescendantId} onMouseDown={() => parentRef.current?.focus()} style={{ ['--gap' as any]: `${GAP}px` }}>
      <div key={columns} className="grid-rows" style={{ height: rowVirtualizer.getTotalSize() }}>
        {rows.map(row => {
          const start = row.index * columns
          const slice = items.slice(start, start + columns)
          const isTopmostVisibleRow = row.index === rows[0]?.index
          try { if (!isScrolling) { for (const it of slice) { try { api.prefetchThumb(it.path) } catch {} } } } catch {}
          const nextPageStart = (row.index + 1) * columns
          const nextPageItems = items.slice(nextPageStart, nextPageStart + columns)
          if (!isScrolling && rows.length <= 20) { for (const it of nextPageItems) { try { api.prefetchThumb(it.path) } catch {} } }
          return (
            <div key={row.key} className="grid-row" role="row" style={{ transform: `translate3d(0, ${row.start}px, 0)`, gridTemplateColumns: `repeat(${columns}, minmax(0, 1fr))`, containIntrinsicSize: `${rowH}px 100%` as any }}>
              {slice.map(it => (
                <div id={`cell-${encodeURIComponent(it.path)}`} key={it.path} className={`grid-cell ${(active===it.path || selectedSet.has(it.path)) ? 'is-selected' : ''}`} role="gridcell" aria-selected={selectedSet.has(it.path) || active===it.path} tabIndex={focused===it.path?0:-1} onFocus={()=> setFocused(it.path)} draggable onDragStart={(e)=>{
                  try {
                    const paths = selectedSet.has(it.path) && selected.length>0 ? selected : [it.path]
                    e.dataTransfer?.setData('application/x-lenscat-paths', JSON.stringify(paths))
                    if (e.dataTransfer) e.dataTransfer.effectAllowed = 'copyMove'
                    try { document.body.classList.add('drag-active') } catch {}
                    const host = e.currentTarget as HTMLElement
                    const img = host.querySelector('.cell-content img') as HTMLImageElement | null
                    const ghost = document.createElement('div')
                    ghost.className = 'drag-ghost'
                    const ghostImg = document.createElement('img')
                    ghostImg.draggable = false
                    ghostImg.alt = 'drag'
                    if (img && img.src) ghostImg.src = img.src
                    ghost.appendChild(ghostImg)
                    document.body.appendChild(ghost)
                    const w = ghost.getBoundingClientRect().width || 150
                    e.dataTransfer!.setDragImage(ghost, Math.round(w/2), 0)
                    const cleanup = () => { try { ghost.remove() } catch {} ; try { document.body.classList.remove('drag-active') } catch {} ; window.removeEventListener('dragend', cleanup) }
                    window.addEventListener('dragend', cleanup)
                  } catch {}
                }} onDragEnd={()=>{}} onContextMenu={(e)=>{ e.preventDefault(); e.stopPropagation(); if (onContextMenuItem) onContextMenuItem(e, it.path) }}>
                  <div className="cell-media" onMouseEnter={()=>{ try { api.prefetchFile(it.path) } catch {} }} onDoubleClick={()=> onOpenViewer(it.path)} onMouseLeave={()=>{
                    if (hoverTimer) { window.clearTimeout(hoverTimer); setHoverTimer(null) }
                    setPreviewFor(null)
                    if (previewUrlRef.current) { try { URL.revokeObjectURL(previewUrlRef.current) } catch {} ; previewUrlRef.current = null }
                    setPreviewUrl(null)
                    setDelayPassed(false)
                  }}>
                    <div className="cell-content">
                      <ThumbCard path={it.path} name={it.name} selected={(active===it.path) || selectedSet.has(it.path)} displayW={cellW} displayH={mediaH} ioRoot={parentRef.current} isScrolling={isScrolling} priority={isTopmostVisibleRow} onClick={(ev: React.MouseEvent)=>{
                        setActive(it.path)
                        setFocused(it.path)
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
                            if (isToggle) { const next = new Set(selected); for (const p of range) next.add(p); onSelectionChange(Array.from(next)) }
                            else { onSelectionChange(range) }
                          } else { onSelectionChange([it.path]) }
                        } else if (isToggle) {
                          const next = new Set(selected)
                          if (next.has(it.path)) next.delete(it.path); else next.add(it.path)
                          onSelectionChange(Array.from(next))
                          try { anchorRef.current = it.path } catch {}
                        } else {
                          onSelectionChange([it.path])
                          try { anchorRef.current = it.path } catch {}
                        }
                        try { if (!isScrolling) { api.prefetchFile(it.path); api.prefetchThumb(it.path) } } catch {}
                        try { (document.getElementById(`cell-${encodeURIComponent(it.path)}`) as HTMLElement | null)?.focus() } catch {}
                      }} />
                    </div>
                    <div className="cell-zoom-hit" onMouseEnter={async ()=>{
                      if (isScrolling) return
                      if (hoverTimer) window.clearTimeout(hoverTimer)
                      setPreviewFor(it.path)
                      setDelayPassed(false)
                      const t = window.setTimeout(async () => {
                        try {
                          const blob = await api.getFile(it.path)
                          const u = URL.createObjectURL(blob)
                          if (previewUrlRef.current) { try { URL.revokeObjectURL(previewUrlRef.current) } catch {} }
                          previewUrlRef.current = u
                          setPreviewUrl(u)
                          setDelayPassed(true)
                        } catch {}
                      }, 350)
                      setHoverTimer(t as any)
                    }} onMouseLeave={()=>{
                      if (hoverTimer) window.clearTimeout(hoverTimer)
                      setHoverTimer(null)
                      setDelayPassed(false)
                      setPreviewFor(null)
                      if (previewUrlRef.current) { try { URL.revokeObjectURL(previewUrlRef.current) } catch {} ; previewUrlRef.current = null }
                      setPreviewUrl(null)
                    }}>
                      <div className="cell-zoom">🔍</div>
                    </div>
                  </div>
                  <div className="cell-caption">
                    <div className="filename" title={it.name}>{(() => {
                      const q = (highlight||'').trim()
                      if (!q) return it.name
                      const hay = it.name
                      const idx = hay.toLowerCase().indexOf(q.toLowerCase())
                      if (idx === -1) return it.name
                      const before = hay.slice(0, idx)
                      const match = hay.slice(idx, idx + q.length)
                      const after = hay.slice(idx + q.length)
                      return (<>{before}<mark>{match}</mark>{after}</>)
                    })()}</div>
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


