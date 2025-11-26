import React, { useEffect, useRef, useState } from 'react'
import type { ViewMode } from '../../lib/types'

export default function Toolbar({
  onSearch,
  viewerActive,
  onBack,
  zoomPercent,
  onZoomPercentChange,
  sortKey,
  sortDir,
  onSortKey,
  onSortDir,
  starFilters,
  onToggleStar,
  onClearStars,
  starCounts,
  viewMode,
  onViewMode,
}:{
  onSearch: (q: string) => void
  viewerActive?: boolean
  onBack?: () => void
  zoomPercent?: number
  onZoomPercentChange?: (p: number) => void
  sortKey?: 'name' | 'added'
  sortDir?: 'asc' | 'desc'
  onSortKey?: (k: 'name' | 'added') => void
  onSortDir?: (d: 'asc' | 'desc') => void
  starFilters?: number[] | null
  onToggleStar?: (v: number) => void
  onClearStars?: () => void
  starCounts?: { [k: string]: number }
  viewMode?: ViewMode
  onViewMode?: (v: ViewMode) => void
}){
  const [openRating, setOpenRating] = useState(false)
  const ratingRef = useRef<HTMLDivElement | null>(null)
  useEffect(() => {
    const onClick = (e: MouseEvent) => {
      const t = e.target as HTMLElement
      if (!ratingRef.current) return
      if (!ratingRef.current.contains(t)) setOpenRating(false)
    }
    if (openRating) window.addEventListener('click', onClick)
    return () => window.removeEventListener('click', onClick)
  }, [openRating])
  return (
    <div className="fixed top-0 left-0 right-0 h-12 grid grid-cols-[1fr_auto_1fr] items-center px-3 gap-3 bg-panel border-b border-border z-toolbar col-span-full row-start-1">
      <div className="flex items-center gap-2">
        {viewerActive && (
          <button className="px-2.5 py-1.5 bg-[#1b1b1b] text-text border border-border rounded-lg cursor-pointer" onClick={onBack}>← Back</button>
        )}
        {!viewerActive && (
          <div className="flex gap-2 items-center relative">
            <select className="h-7 rounded-lg px-2.5 border border-border bg-[#1b1b1b] text-text" value={viewMode||'grid'} onChange={e=> onViewMode && onViewMode(e.target.value as ViewMode)} title="View mode">
              <option value="grid">Grid</option>
              <option value="adaptive">Adaptive</option>
            </select>
            <div className="w-px h-5 bg-border mx-1"></div>
            <select className="h-7 rounded-lg px-2.5 border border-border bg-[#1b1b1b] text-text" value={sortKey||'added'} onChange={e=> onSortKey && onSortKey((e.target.value as any) || 'added')} title="Sort by">
              <option value="added">Date added</option>
              <option value="name">Filename</option>
            </select>
            <button className="px-2.5 py-1.5 bg-[#1b1b1b] text-text border border-border rounded-lg cursor-pointer" onClick={()=> onSortDir && onSortDir((sortDir||'desc')==='desc'?'asc':'desc')} title="Toggle sort">
              {(sortDir||'desc')==='desc' ? '↓' : '↑'}
            </button>
            <div ref={ratingRef}>
              <button className="h-7 px-2.5 bg-[#1b1b1b] text-text border border-border rounded-lg cursor-pointer flex items-center gap-1.5" onClick={()=> setOpenRating(v=>!v)} title="Filter by rating" aria-haspopup="dialog" aria-expanded={openRating}>
                <span className="text-sm">★</span>
                <span className="text-[13px]">Rating</span>
              </button>
              {openRating && (
                <div role="dialog" aria-label="Filter by rating" className="absolute top-[38px] left-0 bg-[#1b1b1b] border border-border rounded-lg p-1.5 shadow-[0_10px_26px_rgba(0,0,0,0.35)] w-[200px]" onKeyDown={(e)=>{ if (e.key==='Escape') setOpenRating(false) }}>
                  {[5,4,3,2,1].map(v => {
                    const active = !!(starFilters||[]).includes(v)
                    const count = starCounts?.[String(v)] ?? 0
                    return (
                      <div key={v} onClick={()=> onToggleStar && onToggleStar(v)} className={`flex items-center justify-between px-1.5 py-1 rounded-md cursor-pointer ${active ? 'bg-accent/15' : ''}`}>
                        <div className={`text-[13px] ${active ? 'text-[#ffd166]' : 'text-text'}`}>{'★'.repeat(v)}{'☆'.repeat(5-v)}</div>
                        <div className="opacity-80 text-xs">{count}</div>
                      </div>
                    )
                  })}
                  {(() => { const activeNone = !!(starFilters||[]).includes(0); return (
                    <div onClick={()=> onToggleStar && onToggleStar(0)} className={`flex items-center justify-between px-1.5 py-1 rounded-md cursor-pointer ${activeNone ? 'bg-accent/15' : ''}`}>
                      <div className="text-[13px] text-text">None</div>
                      <div className="opacity-80 text-xs">{starCounts?.['0'] ?? 0}</div>
                    </div>
                  )})()}
                  <div className="h-px bg-border my-1.5" />
                  <div className="flex gap-2">
                    <button className="h-[26px] px-2.5 bg-[#1b1b1b] text-text border border-border rounded-lg cursor-pointer" onClick={onClearStars}>All</button>
                  </div>
                </div>
              )}
            </div>
            {(() => {
              const sf = starFilters || []
              if (!sf.length) return null
              const stars = sf.filter(v => v > 0).sort((a,b)=>b-a)
              const label = stars.length ? stars.join(',') : (sf.includes(0) ? 'None' : '')
              return (
                <div className="inline-flex items-center gap-1.5 px-2 py-1 pl-1.5 bg-accent/20 border border-border text-text rounded-[10px] h-[26px]" aria-label={`Rating filter active: ${label}`} title={`Rating filter: ${label}`}>
                  <span className="text-[#ffd166] text-[13px] leading-none">★</span>
                  <span className="text-[13px] opacity-95">{label}</span>
                  <button className="w-[18px] h-[18px] rounded-full border border-border bg-black/25 text-text cursor-pointer inline-flex items-center justify-center leading-none p-0 hover:bg-black/35" aria-label="Clear rating filter" onClick={onClearStars}>×</button>
                </div>
              )
            })()}
          </div>
        )}
      </div>

      {viewerActive && (
        <div className="flex items-center gap-2.5 justify-center">
          <input
            type="range"
            min={5}
            max={800}
            step={1}
            value={Math.round(Math.max(5, Math.min(800, zoomPercent ?? 100)))}
            onChange={e => onZoomPercentChange && onZoomPercentChange(Number(e.target.value))}
            className="zoom-slider"
          />
          <span className="text-xs opacity-80 min-w-[42px] text-right">{Math.round(zoomPercent ?? 100)}%</span>
        </div>
      )}

      <div className="flex items-center gap-2 justify-end">
        <input
          aria-label="Search filename, tags, notes"
          placeholder="Search filename, tags, notes…"
          onChange={e=>onSearch(e.target.value)}
          className="h-8 w-[360px] rounded-lg px-2.5 border border-border bg-[#1b1b1b] text-text"
        />
      </div>
    </div>
  )
}
