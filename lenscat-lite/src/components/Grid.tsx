import React, { useMemo, useRef, useState, useEffect } from 'react'
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

  useEffect(() => {
    const el = parentRef.current
    if (!el) return
    const onKey = (e: KeyboardEvent) => {
      if (!items.length) return
      const idx = active ? items.findIndex(i => i.path === active) : 0
      const col = columns
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
      }
    }
    el.addEventListener('keydown', onKey)
    return () => { el.removeEventListener('keydown', onKey) }
  }, [items, active, columns])

  return (
    <div className="grid" ref={parentRef} tabIndex={0}>
      <div style={{ height: rowVirtualizer.getTotalSize(), width: '100%', position: 'relative' }}>
        {rows.map(row => {
          const start = row.index * columns
          const slice = items.slice(start, start + columns)
          return (
            <div key={row.key} style={{ position: 'absolute', top: 0, left: 0, transform: `translateY(${row.start}px)`, display: 'grid', gridTemplateColumns: `repeat(${columns}, 1fr)`, gap }}>
              {slice.map(it => (
                <div key={it.path} style={{ position:'relative' }}
                     onDoubleClick={()=> onOpenViewer(it.path)}
                     onMouseLeave={()=>{ if (hoverTimer) { window.clearTimeout(hoverTimer); setHoverTimer(null) }; setPreviewFor(null); setPreviewUrl(null) }}>
                  <Thumb path={it.path} name={it.name} selected={active===it.path} onClick={()=>{ setActive(it.path); onOpen(it.path) }} />
                  <div style={{ position:'absolute', right:6, bottom:6, width:18, height:18, background:'rgba(0,0,0,0.6)', borderRadius:4, display:'flex', alignItems:'center', justifyContent:'center', fontSize:10, userSelect:'none' }}
                       onMouseEnter={()=>{
                         if (hoverTimer) window.clearTimeout(hoverTimer)
                         const t = window.setTimeout(async ()=>{
                           setPreviewFor(it.path)
                           try {
                             const blob = await api.getFile(it.path)
                             setPreviewUrl(URL.createObjectURL(blob))
                           } catch {}
                         }, 500)
                         setHoverTimer(t)
                       }}
                       onMouseLeave={()=>{ if (hoverTimer) window.clearTimeout(hoverTimer); setHoverTimer(null); setPreviewFor(null); setPreviewUrl(null) }}
                  >
                    🔍
                  </div>
                </div>
              ))}
            </div>
          )
        })}
        {previewFor && previewUrl && (
          <div style={{ position:'fixed', top:'48px', left:'var(--left)', right:'var(--right)', bottom:0, zIndex:9, display:'flex', alignItems:'center', justifyContent:'center', pointerEvents:'none' }}>
            <img src={previewUrl} alt="preview" style={{ maxWidth:'96%', maxHeight:'96%', objectFit:'contain', transition:'opacity 160ms ease', opacity:0.98 }} />
          </div>
        )}
      </div>
    </div>
  )
}
