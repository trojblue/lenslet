import React, { useRef, useState, useEffect, useLayoutEffect, useMemo } from 'react'
import { createPortal } from 'react-dom'
import type { Item, ViewMode } from '../../../lib/types'
import ThumbCard from './ThumbCard'
import { api } from '../../../shared/api/client'
import { useVirtualGrid } from '../hooks/useVirtualGrid'
import { getNextIndexForKeyNav } from '../hooks/useKeyboardNav'

interface VirtualGridProps {
  items: Item[]
  selected: string[]
  restoreToSelectionToken?: number
  onSelectionChange: (paths: string[]) => void
  onOpenViewer: (path: string) => void
  onContextMenuItem?: (e: React.MouseEvent, path: string) => void
  highlight?: string
  suppressSelectionHighlight?: boolean
  viewMode?: ViewMode
  targetCellSize?: number
}

export default function VirtualGrid({
  items,
  selected,
  restoreToSelectionToken,
  onSelectionChange,
  onOpenViewer,
  onContextMenuItem,
  highlight,
  suppressSelectionHighlight = false,
  viewMode = 'grid',
  targetCellSize = 220,
}: VirtualGridProps) {
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
  const TARGET_CELL = targetCellSize
  const ASPECT = { w: 4, h: 3 }
  const CAPTION_H = 44

  const { width, layout, rowVirtualizer, virtualRows } = useVirtualGrid(parentRef as any, items, { gap: GAP, targetCell: TARGET_CELL, aspect: ASPECT, captionH: CAPTION_H, viewMode })

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

  const effectiveColumns = layout.mode === 'grid' ? layout.columns : Math.max(1, Math.floor(width / (TARGET_CELL + GAP)))

  useEffect(() => {
    const el = parentRef.current
    if (!el) return
    const onKey = (e: KeyboardEvent) => {
      const result = getNextIndexForKeyNav(items, Math.max(1, effectiveColumns), focused, e)
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
      
      // Find row for next item
      let rowIdx = 0
      if (layout.mode === 'grid') {
        rowIdx = Math.floor(next / Math.max(1, layout.columns))
      } else {
        let low = 0, high = layout.rows.length - 1
        while (low <= high) {
            const mid = (low + high) >> 1
            const r = layout.rows[mid]
            if (next >= r.items[0].originalIndex && next <= r.items[r.items.length-1].originalIndex) {
                rowIdx = mid
                break
            }
            if (next < r.items[0].originalIndex) high = mid - 1
            else low = mid + 1
        }
      }

      const scrollTop = el.scrollTop
      const viewBottom = scrollTop + el.clientHeight
      
      const rowTop = layout.mode === 'adaptive' ? (layout.rows[rowIdx]?.start ?? 0) : (rowIdx * layout.rowH)
      const rowHeight = layout.mode === 'adaptive' ? (layout.rows[rowIdx]?.height ?? 0) : layout.rowH
      const rowBottom = rowTop + rowHeight

      if (rowTop < scrollTop || rowBottom > viewBottom) {
        try { scrollRowIntoView(el, rowTop) }
        catch { try { rowVirtualizer.scrollToIndex(rowIdx, { align: 'start' as const }) } catch {} }
      }
      try { (document.getElementById(`cell-${encodeURIComponent(nextItem.path)}`) as HTMLElement | null)?.focus() } catch {}
    }
    el.addEventListener('keydown', onKey)
    return () => { el.removeEventListener('keydown', onKey) }
  }, [items, focused, effectiveColumns, onOpenViewer, layout])

  useLayoutEffect(() => {
    const el = parentRef.current
    if (!el) return
    if (!restoreToSelectionToken) return
    if (!selected || selected.length === 0) return
    const first = selected[0]
    const idx = pathToIndex.get(first)
    if (idx == null || idx < 0) return
    
    let rowIdx = 0
    if (layout.mode === 'grid') {
        rowIdx = Math.floor(idx / Math.max(1, layout.columns))
    } else {
        let low = 0, high = layout.rows.length - 1
        while (low <= high) {
            const mid = (low + high) >> 1
            const r = layout.rows[mid]
            if (idx >= r.items[0].originalIndex && idx <= r.items[r.items.length-1].originalIndex) {
                rowIdx = mid
                break
            }
            if (idx < r.items[0].originalIndex) high = mid - 1
            else low = mid + 1
        }
    }
    const targetTop = layout.mode === 'adaptive' ? (layout.rows[rowIdx]?.start ?? 0) : (rowIdx * layout.rowH)
    
    try { el.scrollTop = targetTop } catch {}
  }, [restoreToSelectionToken, layout])

  const selectedSet = new Set(selected)
  const hasPreview = !!(previewFor && previewUrl && delayPassed)
  useEffect(() => { parentRef.current?.focus() }, [])
  useEffect(() => { if (suppressSelectionHighlight) { try { parentRef.current?.blur() } catch {} ; try { setFocused(null) } catch {} } }, [suppressSelectionHighlight])

  const activeDescendantId = focused ? `cell-${encodeURIComponent(focused)}` : undefined

  return (
    <div 
      role="grid" 
      aria-label="Gallery" 
      className={`relative h-full overflow-auto p-3 outline-none scrollbar-thin ${hasPreview ? 'cursor-zoom-in' : ''}`}
      ref={parentRef} 
      tabIndex={0} 
      aria-activedescendant={activeDescendantId} 
      onMouseDown={() => parentRef.current?.focus()} 
      style={{ ['--gap' as any]: `${GAP}px` }}
    >
      <div key={`${viewMode}-${effectiveColumns}`} className="relative w-full" style={{ height: rowVirtualizer.getTotalSize() }}>
        {virtualRows.map(row => {
          let rowItems: { item: Item, displayW: number, displayH: number }[] = []
          let rowStyle: React.CSSProperties = {}
          let rowClass = ""

          if (layout.mode === 'adaptive') {
             const rowData = layout.rows[row.index]
             if (!rowData) return null
             rowItems = rowData.items
             rowStyle = {
                 height: rowData.height,
                 transform: `translate3d(0, ${row.start}px, 0)`,
                 display: 'flex',
                 gap: GAP,
                 paddingBottom: GAP,
             }
             rowClass = "absolute top-0 left-0 right-0 w-full will-change-transform"
          } else {
             const start = row.index * layout.columns
             const slice = items.slice(start, start + layout.columns)
             rowItems = slice.map(it => ({ item: it, displayW: layout.cellW, displayH: layout.mediaH }))
             rowStyle = {
                 transform: `translate3d(0, ${row.start}px, 0)`,
                 gridTemplateColumns: `repeat(${layout.columns}, minmax(0, 1fr))`,
                 gap: GAP,
                 paddingBottom: GAP,
             }
             rowClass = "absolute top-0 left-0 right-0 w-full grid will-change-transform"
          }
          
          // Prefetch logic
          const isTopmostVisibleRow = row.index === virtualRows[0]?.index
          try { if (!isScrolling) { for (const { item: it } of rowItems) { try { api.prefetchThumb(it.path) } catch {} } } } catch {}
          
          return (
            <div 
              key={row.key} 
              className={rowClass}
              role="row" 
              style={rowStyle}
            >
              {rowItems.map(({ item: it, displayW, displayH }) => {
                const isVisuallySelected = !suppressSelectionHighlight && ((active===it.path) || selectedSet.has(it.path))
                const wrapperStyle = layout.mode === 'adaptive' ? { width: displayW } : {}
                const imageContainerStyle = layout.mode === 'adaptive' ? { height: displayH } : {}
                
                const itemContainerClass = layout.mode === 'adaptive' 
                    ? "relative rounded-lg overflow-hidden bg-[var(--thumb-bg)] group shrink-0" 
                    : "relative aspect-[4/3] rounded-lg overflow-hidden bg-[var(--thumb-bg)] group"

                return (
                <div 
                  id={`cell-${encodeURIComponent(it.path)}`} 
                  key={it.path} 
                  className={`relative group ${isVisuallySelected ? 'z-10' : 'z-0'}`}
                  role="gridcell" 
                  aria-selected={isVisuallySelected} 
                  tabIndex={focused===it.path?0:-1} 
                  onFocus={()=> setFocused(it.path)} 
                  draggable 
                  style={wrapperStyle}
                  onDragStart={(e)=>{
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
                    const cleanup = () => {
                      try { ghost.remove() } catch {}
                      try { document.body.classList.remove('drag-active') } catch {}
                      window.removeEventListener('dragend', cleanup)
                      window.removeEventListener('pointerup', cleanup)
                      document.removeEventListener('visibilitychange', cleanup)
                    }
                    window.addEventListener('dragend', cleanup)
                    window.addEventListener('pointerup', cleanup)
                    document.addEventListener('visibilitychange', cleanup)
                  } catch {}
                }} onDragEnd={()=>{}} onContextMenu={(e)=>{ e.preventDefault(); e.stopPropagation(); if (onContextMenuItem) onContextMenuItem(e, it.path) }}>
                  <div 
                    className={itemContainerClass}
                    style={imageContainerStyle}
                    onMouseEnter={()=>{ try { api.prefetchFile(it.path) } catch {} }} 
                    onDoubleClick={()=> onOpenViewer(it.path)} 
                    onMouseLeave={()=>{
                    if (hoverTimer) { window.clearTimeout(hoverTimer); setHoverTimer(null) }
                    setPreviewFor(null)
                    if (previewUrlRef.current) { try { URL.revokeObjectURL(previewUrlRef.current) } catch {} ; previewUrlRef.current = null }
                    setPreviewUrl(null)
                    setDelayPassed(false)
                  }}>
                    <div className="cell-content absolute inset-0">
                      <ThumbCard path={it.path} name={it.name} selected={isVisuallySelected} displayW={displayW} displayH={displayH} ioRoot={parentRef.current} isScrolling={isScrolling} priority={isTopmostVisibleRow} onClick={(ev: React.MouseEvent)=>{
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
                    <div 
                      className="absolute right-1 bottom-1 w-6 h-6 bg-black/60 rounded-full flex items-center justify-center text-xs select-none opacity-0 group-hover:opacity-100 transition-opacity duration-[120ms] cursor-zoom-in hover:bg-black/80"
                      onMouseEnter={async ()=>{
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
                      🔍
                    </div>
                  </div>
                  <div className="flex flex-col items-center gap-0.5 mt-1.5 px-0.5 text-text">
                    <div className="text-[11px] leading-[14px] opacity-50 font-mono">{it.w} × {it.h}</div>
                  </div>
                </div>
              )})}
            </div>
          )
        })}
        {previewFor && previewUrl && delayPassed && createPortal(
          <div className="fixed inset-0 top-12 z-[999] flex items-center justify-center pointer-events-none bg-black/20 opacity-100">
            <img src={previewUrl} alt="preview" className="max-w-[80vw] max-h-[80vh] object-contain opacity-[0.98]" />
          </div>,
          document.body
        )}
      </div>
    </div>
  )
}
