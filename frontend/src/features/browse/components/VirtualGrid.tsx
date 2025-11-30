import React, { useRef, useState, useEffect, useLayoutEffect, useMemo } from 'react'
import { createPortal } from 'react-dom'
import type { Item, ViewMode } from '../../../lib/types'
import ThumbCard from './ThumbCard'
import { api } from '../../../shared/api/client'
import { useVirtualGrid } from '../hooks/useVirtualGrid'
import { getNextIndexForKeyNav } from '../hooks/useKeyboardNav'
import type { AdaptiveRow } from '../model/adaptive'

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

  const adaptivePositions = useMemo(() => {
    if (layout.mode !== 'adaptive') return null
    const map = new Map<string, { row: number, center: number, order: number }>()
    layout.rows.forEach((row: AdaptiveRow, rowIdx: number) => {
      let x = 0
      row.items.forEach((it, order) => {
        const center = x + it.displayW / 2
        map.set(it.item.path, { row: rowIdx, center, order })
        x += it.displayW + GAP
      })
    })
    return map
  }, [layout])

  const adaptiveRowMeta = useMemo(() => {
    if (layout.mode !== 'adaptive') return null
    let offset = 0
    return layout.rows.map(r => {
      const start = offset
      offset += r.height
      return { start, height: r.height }
    })
  }, [layout])

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

  const findClosestInRow = (rowIdx: number, targetCenter: number): string | null => {
    if (layout.mode !== 'adaptive') return null
    const row = layout.rows[rowIdx]
    if (!row) return null
    let x = 0
    let best: { path: string; dist: number } | null = null
    row.items.forEach(it => {
      const center = x + it.displayW / 2
      const dist = Math.abs(center - targetCenter)
      if (!best || dist < best.dist) {
        best = { path: it.item.path, dist }
      }
      x += it.displayW + GAP
    })
    return best?.path ?? null
  }

  const getNextPath = (current: string | null, e: KeyboardEvent): string | 'open' | null => {
    if (!items.length) return null
    // Default to first item when nothing is focused
    const currentPath = current ?? items[0].path

    if (layout.mode !== 'adaptive') {
      const nextIdx = getNextIndexForKeyNav(items, effectiveColumns, currentPath, e)
      if (nextIdx === 'open' || nextIdx == null) return nextIdx
      return items[nextIdx]?.path ?? null
    }

    const info = adaptivePositions?.get(currentPath)
    if (!info) return currentPath

    const idx = pathToIndex.get(currentPath) ?? 0
    const key = e.key

    if (key === 'Enter') return 'open'

    // Horizontal moves stay in reading order using the flat list
    if (key === 'ArrowRight' || key === 'd') return items[Math.min(items.length - 1, idx + 1)]?.path ?? currentPath
    if (key === 'ArrowLeft' || key === 'a') return items[Math.max(0, idx - 1)]?.path ?? currentPath

    const delta = key === 'ArrowDown' || key === 's' ? 1 : key === 'ArrowUp' || key === 'w' ? -1 : 0
    if (delta === 0) return null

    const targetRow = info.row + delta
    if (targetRow < 0 || targetRow >= (layout.rows?.length ?? 0)) return currentPath

    const targetCenter = info.center
    const candidate = findClosestInRow(targetRow, targetCenter)
    return candidate ?? currentPath
  }

  useEffect(() => {
    const el = parentRef.current
    if (!el) return
    const onKey = (e: KeyboardEvent) => {
      const nextPath = getNextPath(focused, e)
      if (nextPath == null) return
      e.preventDefault()
      if (nextPath === 'open') { if (focused) onOpenViewer(focused); return }
      const nextItem = items.find(i => i.path === nextPath)
      if (!nextItem) return
      setFocused(nextItem.path)
      setActive(nextItem.path)
      onSelectionChange([nextItem.path])
      try { anchorRef.current = nextItem.path } catch {}
      
      // Find row for next item
      const nextRowIdx = layout.mode === 'grid'
        ? Math.floor((pathToIndex.get(nextItem.path) ?? 0) / Math.max(1, layout.columns))
        : (adaptivePositions?.get(nextItem.path)?.row ?? 0)

      const scrollTop = el.scrollTop
      const viewBottom = scrollTop + el.clientHeight
      const rowTop = layout.mode === 'adaptive' 
        ? (adaptiveRowMeta?.[nextRowIdx]?.start ?? 0)
        : nextRowIdx * layout.rowH
      const rowBottom = layout.mode === 'adaptive'
        ? rowTop + (adaptiveRowMeta?.[nextRowIdx]?.height ?? 0)
        : rowTop + layout.rowH

      if (rowTop < scrollTop || rowBottom > viewBottom) {
        scrollRowIntoView(el, rowTop)
      }
      try { (document.getElementById(`cell-${encodeURIComponent(nextItem.path)}`) as HTMLElement | null)?.focus() } catch {}
    }
    el.addEventListener('keydown', onKey)
    return () => { el.removeEventListener('keydown', onKey) }
  }, [items, focused, effectiveColumns, onOpenViewer, layout, adaptivePositions, adaptiveRowMeta, pathToIndex])

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
    const targetTop = layout.mode === 'adaptive' ? (adaptiveRowMeta?.[rowIdx]?.start ?? 0) : (rowIdx * layout.rowH)
    
    try { el.scrollTop = targetTop } catch {}
  }, [restoreToSelectionToken, layout, adaptiveRowMeta])

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
                    ? "relative rounded-lg overflow-hidden bg-[var(--thumb-bg,#121212)] group shrink-0" 
                    : "relative aspect-[4/3] rounded-lg overflow-hidden bg-[var(--thumb-bg,#121212)] group"

                return (
                <div 
                  id={`cell-${encodeURIComponent(it.path)}`} 
                  key={it.path} 
                  className={`relative min-w-0 ${isVisuallySelected ? 'outline outline-2 outline-accent outline-offset-2 rounded-[10px]' : ''}`}
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
                      className="absolute right-0 bottom-0 w-7 h-7 cursor-zoom-in"
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
                      <div
                        className="absolute right-0 bottom-0 h-[18px] w-[18px] flex items-center justify-center text-text select-none opacity-0 group-hover:opacity-50 hover:opacity-100 transition-all duration-[140ms]"
                        style={{
                          clipPath: 'path("M0 9C0 4.02944 4.02944 0 9 0H18V18H0V9Z")',
                          background: 'linear-gradient(135deg, rgba(18,18,18,0.9) 0%, rgba(34,34,34,0.9) 60%, rgba(22,22,22,0.9) 100%)',
                          borderTop: '1px solid rgba(255,255,255,0.08)',
                          borderLeft: '1px solid rgba(255,255,255,0.08)',
                          boxShadow: '0 1px 2px rgba(0,0,0,0.45)',
                          backdropFilter: 'blur(1px)'
                        }}
                      >
                        <svg
                          width="11"
                          height="11"
                          viewBox="0 0 24 24"
                          fill="none"
                          stroke="currentColor"
                          strokeWidth="1.7"
                          strokeLinecap="round"
                          strokeLinejoin="round"
                          className="text-[#d9dce2]"
                          aria-hidden="true"
                          style={{ transform: 'translate(0px,0px)' }}
                        >
                          <circle cx="11" cy="11" r="5.4" />
                          <path d="M15.5 15.5 L19 19" />
                        </svg>
                      </div>
                    </div>
                  </div>
                  <div className="flex flex-col items-center text-center gap-0 mt-1 px-0.5 text-white/90">
                    <div className="text-sm leading-[18px] thumb-filename line-clamp-2 break-words hyphens-auto text-center" title={it.name}>{(() => {
                      const q = (highlight||'').trim()
                      if (!q) return it.name
                      const hay = it.name
                      const idx = hay.toLowerCase().indexOf(q.toLowerCase())
                      if (idx === -1) return it.name
                      const before = hay.slice(0, idx)
                      const match = hay.slice(idx, idx + q.length)
                      const after = hay.slice(idx + q.length)
                      return (<>{before}<mark className="bg-accent/20 text-inherit rounded px-0.5">{match}</mark>{after}</>)
                    })()}</div>
                    <div className="text-[11px] leading-[15px] opacity-70">{it.w} × {it.h}</div>
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
