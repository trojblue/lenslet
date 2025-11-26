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
  gridItemSize,
  onGridItemSize,
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
  gridItemSize?: number
  onGridItemSize?: (s: number) => void
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

  // Common button/input classes for consistent height and style
  const controlClass = "h-8 rounded-lg px-3 border border-border bg-[#1b1b1b] text-text text-sm hover:bg-[#252525] active:scale-95 transition-all duration-200 outline-none focus-visible:ring-2 focus-visible:ring-accent/50"
  const selectClass = "h-8 rounded-lg px-2.5 border border-border bg-[#1b1b1b] text-text text-sm outline-none focus-visible:ring-2 focus-visible:ring-accent/50 cursor-pointer hover:bg-[#252525] transition-colors"
  const iconBtnClass = "h-8 w-8 flex items-center justify-center rounded-lg border border-border bg-[#1b1b1b] text-text hover:bg-[#252525] active:scale-95 transition-all duration-200 cursor-pointer"

  return (
    <div className="fixed top-0 left-0 right-0 h-12 grid grid-cols-[auto_1fr_auto] items-center px-4 gap-4 bg-panel border-b border-border z-toolbar col-span-full row-start-1 select-none">
      <div className="flex items-center gap-3">
        {viewerActive && (
          <button className={controlClass} onClick={onBack}>
            <span className="mr-1">←</span> Back
          </button>
        )}
        
        {!viewerActive && (
          <div className="flex gap-3 items-center relative">
            {/* View Mode & Size Group */}
            <div className="flex items-center gap-2 p-1 pr-3 rounded-lg bg-black/20 border border-white/5">
              <select 
                className="h-6 bg-transparent text-sm border-none outline-none text-text/90 cursor-pointer ml-1" 
                value={viewMode||'grid'} 
                onChange={e=> onViewMode && onViewMode(e.target.value as ViewMode)} 
                title="View mode"
              >
                <option value="grid">Grid</option>
                <option value="adaptive">Adaptive</option>
              </select>
              
              {onGridItemSize && (
                <div className="flex items-center gap-2 pl-2 border-l border-white/10">
                  <span className="text-xs opacity-50">Size</span>
                  <input
                    type="range"
                    min={80}
                    max={500}
                    step={10}
                    value={gridItemSize || 220}
                    onChange={(e) => onGridItemSize(Number(e.target.value))}
                    className="w-20 h-1 bg-white/10 rounded-full appearance-none cursor-pointer hover:bg-white/20 transition-colors [&::-webkit-slider-thumb]:appearance-none [&::-webkit-slider-thumb]:w-3 [&::-webkit-slider-thumb]:h-3 [&::-webkit-slider-thumb]:rounded-full [&::-webkit-slider-thumb]:bg-text [&::-webkit-slider-thumb]:shadow-sm"
                    title={`Thumbnail size: ${gridItemSize}px`}
                  />
                </div>
              )}
            </div>

            {/* Sort & Filter Group */}
            <div className="flex items-center gap-2">
              <select className={selectClass} value={sortKey||'added'} onChange={e=> onSortKey && onSortKey((e.target.value as any) || 'added')} title="Sort by">
                <option value="added">Date Added</option>
                <option value="name">Filename</option>
              </select>
              
              <button className={iconBtnClass} onClick={()=> onSortDir && onSortDir((sortDir||'desc')==='desc'?'asc':'desc')} title={`Sort ${(sortDir||'desc')==='desc' ? 'Descending' : 'Ascending'}`}>
                {(sortDir||'desc')==='desc' ? '↓' : '↑'}
              </button>

              <div className="w-px h-4 bg-border mx-1"></div>

              <div ref={ratingRef} className="relative">
                <button className={`${controlClass} flex items-center gap-1.5 px-2.5`} onClick={()=> setOpenRating(v=>!v)} title="Filter by rating" aria-haspopup="dialog" aria-expanded={openRating}>
                  <span className="text-[#ffd166]">★</span>
                  <span>Rating</span>
                </button>
                
                {openRating && (
                  <div role="dialog" aria-label="Filter by rating" className="absolute top-[42px] left-0 bg-[#1b1b1b] border border-border rounded-lg p-1.5 shadow-[0_10px_26px_rgba(0,0,0,0.45)] w-[200px] z-50 animate-in fade-in slide-in-from-top-1 duration-150" onKeyDown={(e)=>{ if (e.key==='Escape') setOpenRating(false) }}>
                    {[5,4,3,2,1].map(v => {
                      const active = !!(starFilters||[]).includes(v)
                      const count = starCounts?.[String(v)] ?? 0
                      return (
                        <div key={v} onClick={()=> onToggleStar && onToggleStar(v)} className={`flex items-center justify-between px-2 py-1.5 rounded-md cursor-pointer transition-colors ${active ? 'bg-accent/15' : 'hover:bg-white/5'}`}>
                          <div className={`text-sm ${active ? 'text-[#ffd166]' : 'text-text'}`}>{'★'.repeat(v)}{'☆'.repeat(5-v)}</div>
                          <div className="opacity-60 text-xs font-mono">{count}</div>
                        </div>
                      )
                    })}
                    <div onClick={()=> onToggleStar && onToggleStar(0)} className={`flex items-center justify-between px-2 py-1.5 rounded-md cursor-pointer transition-colors ${!!(starFilters||[]).includes(0) ? 'bg-accent/15' : 'hover:bg-white/5'}`}>
                      <div className="text-sm text-text">Unrated</div>
                      <div className="opacity-60 text-xs font-mono">{starCounts?.['0'] ?? 0}</div>
                    </div>
                    
                    <div className="h-px bg-border my-1.5" />
                    <button className="w-full text-center py-1.5 text-xs opacity-70 hover:opacity-100 hover:bg-white/5 rounded" onClick={onClearStars}>Clear Filter</button>
                  </div>
                )}
              </div>
            </div>

            {/* Active Filters Pills */}
            {(() => {
              const sf = starFilters || []
              if (!sf.length) return null
              const stars = sf.filter(v => v > 0).sort((a,b)=>b-a)
              const label = stars.length ? stars.join(',') : (sf.includes(0) ? 'Unrated' : '')
              return (
                <div className="flex items-center gap-1.5 px-2.5 py-1 bg-accent/10 border border-accent/20 text-text rounded-full h-8 animate-in fade-in zoom-in duration-200" title={`Rating filter: ${label}`}>
                  <span className="text-[#ffd166] text-xs">★</span>
                  <span className="text-sm font-medium opacity-90">{label}</span>
                  <button className="ml-1 w-5 h-5 rounded-full bg-black/20 hover:bg-black/40 flex items-center justify-center transition-colors" onClick={onClearStars}>×</button>
                </div>
              )
            })()}
          </div>
        )}
      </div>

      {/* Center - Viewer Zoom */}
      {viewerActive && (
        <div className="flex items-center gap-3 justify-center bg-black/20 px-4 py-1.5 rounded-full border border-white/5">
          <span className="text-xs opacity-60">Zoom</span>
          <input
            type="range"
            min={5}
            max={800}
            step={5}
            value={Math.round(Math.max(5, Math.min(800, zoomPercent ?? 100)))}
            onChange={e => onZoomPercentChange && onZoomPercentChange(Number(e.target.value))}
            className="w-32 h-1 bg-white/10 rounded-full appearance-none cursor-pointer hover:bg-white/20 transition-colors [&::-webkit-slider-thumb]:appearance-none [&::-webkit-slider-thumb]:w-3 [&::-webkit-slider-thumb]:h-3 [&::-webkit-slider-thumb]:rounded-full [&::-webkit-slider-thumb]:bg-text [&::-webkit-slider-thumb]:shadow-sm"
          />
          <span className="text-xs font-mono opacity-80 w-10 text-right">{Math.round(zoomPercent ?? 100)}%</span>
        </div>
      )}

      {/* Right - Search */}
      <div className="flex items-center gap-2 justify-end toolbar-right">
        <div className="relative group">
          <div className="absolute left-2.5 top-1/2 -translate-y-1/2 text-muted group-focus-within:text-accent transition-colors">
            <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round"><circle cx="11" cy="11" r="8"/><path d="m21 21-4.3-4.3"/></svg>
          </div>
          <input
            aria-label="Search filename, tags, notes"
            placeholder="Search..."
            onChange={e=>onSearch(e.target.value)}
            className="h-8 w-[240px] focus:w-[320px] transition-all duration-300 rounded-lg pl-8 pr-3 border border-border bg-[#1b1b1b] text-text text-sm placeholder:text-muted/70 focus:border-accent/50 focus:ring-1 focus:ring-accent/50 outline-none input"
          />
          <div className="absolute right-2.5 top-1/2 -translate-y-1/2 flex gap-1 pointer-events-none opacity-50 group-focus-within:opacity-0 transition-opacity">
            <kbd className="text-[10px] font-sans bg-white/10 px-1.5 rounded"> / </kbd>
          </div>
        </div>
      </div>
    </div>
  )
}
