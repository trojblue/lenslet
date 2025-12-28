import React, { useEffect, useRef, useState } from 'react'
import type { SortDir, SortKey, ViewMode } from '../../lib/types'

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
  leftOpen,
  rightOpen,
  onToggleLeft,
  onToggleRight,
  onPrevImage,
  onNextImage,
  canPrevImage,
  canNextImage,
}:{
  onSearch: (q: string) => void
  viewerActive?: boolean
  onBack?: () => void
  zoomPercent?: number
  onZoomPercentChange?: (p: number) => void
  sortKey?: SortKey
  sortDir?: SortDir
  onSortKey?: (k: SortKey) => void
  onSortDir?: (d: SortDir) => void
  starFilters?: number[] | null
  onToggleStar?: (v: number) => void
  onClearStars?: () => void
  starCounts?: { [k: string]: number }
  viewMode?: ViewMode
  onViewMode?: (v: ViewMode) => void
  gridItemSize?: number
  onGridItemSize?: (s: number) => void
  leftOpen?: boolean
  rightOpen?: boolean
  onToggleLeft?: () => void
  onToggleRight?: () => void
  onPrevImage?: () => void
  onNextImage?: () => void
  canPrevImage?: boolean
  canNextImage?: boolean
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
    <div className="fixed top-0 left-0 right-0 h-12 grid grid-cols-[auto_1fr_auto] items-center px-3 gap-3 bg-panel border-b border-border z-toolbar col-span-full row-start-1">
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
            <select className="h-7 rounded-lg px-2.5 border border-border bg-[#1b1b1b] text-text" value={sortKey||'added'} onChange={e=> onSortKey && onSortKey((e.target.value as SortKey) || 'added')} title="Sort by">
              <option value="added">Date added</option>
              <option value="name">Filename</option>
              <option value="random">Random</option>
            </select>
            <button className="px-2.5 py-1.5 bg-[#1b1b1b] text-text border border-border rounded-lg cursor-pointer" onClick={()=> onSortDir && onSortDir((sortDir||'desc')==='desc'?'asc':'desc')} title={sortKey === 'random' ? 'Shuffle' : 'Toggle sort'}>
              {sortKey === 'random' ? '⟳' : ((sortDir||'desc')==='desc' ? '↓' : '↑')}
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

      <div className="flex items-center gap-3 justify-center">
        {viewerActive ? (
          <>
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
          </>
        ) : (
          onGridItemSize && (
            <div className="flex items-center gap-2">
              <span className="text-xs text-muted">Size</span>
              <input
                type="range"
                min={80}
                max={500}
                step={10}
                value={gridItemSize ?? 220}
                onChange={(e)=> onGridItemSize(Number(e.target.value))}
                className="w-32 h-1.5 bg-white/10 rounded-full appearance-none cursor-pointer hover:bg-white/20 transition-colors [&::-webkit-slider-thumb]:appearance-none [&::-webkit-slider-thumb]:w-3 [&::-webkit-slider-thumb]:h-3 [&::-webkit-slider-thumb]:rounded-full [&::-webkit-slider-thumb]:bg-text [&::-moz-range-thumb]:w-3 [&::-moz-range-thumb]:h-3 [&::-moz-range-thumb]:rounded-full [&::-moz-range-thumb]:bg-text"
                aria-label="Thumbnail size"
              />
            </div>
          )
        )}
      </div>

      <div className="flex items-center gap-2 justify-end toolbar-right">
        {viewerActive && (
          <div className="flex items-center gap-2 mr-1">
            <button
              className={`h-7 w-7 rounded-md border border-[#3a3a3a] bg-[#252525] text-[#cfd1d4] flex items-center justify-center transition-colors hover:bg-[#2f2f2f] hover:border-[#4a4a4a] ${canPrevImage ? 'opacity-90 cursor-pointer' : 'opacity-45 cursor-not-allowed'}`}
              title="Previous image (A / ←)"
              onClick={() => canPrevImage && onPrevImage && onPrevImage()}
              aria-label="Previous image"
              aria-disabled={!canPrevImage}
            >
              <svg width="12" height="12" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.7" strokeLinecap="round" strokeLinejoin="round">
                <path d="M15 18l-6-6 6-6" />
              </svg>
            </button>
            <button
              className={`h-7 w-7 rounded-md border border-[#3a3a3a] bg-[#252525] text-[#cfd1d4] flex items-center justify-center transition-colors hover:bg-[#2f2f2f] hover:border-[#4a4a4a] ${canNextImage ? 'opacity-90 cursor-pointer' : 'opacity-45 cursor-not-allowed'}`}
              title="Next image (D / →)"
              onClick={() => canNextImage && onNextImage && onNextImage()}
              aria-label="Next image"
              aria-disabled={!canNextImage}
            >
              <svg width="12" height="12" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.7" strokeLinecap="round" strokeLinejoin="round">
                <path d="M9 6l6 6-6 6" />
              </svg>
            </button>
          </div>
        )}

        <div className="flex items-center gap-1 ml-1">
          <button
            className={`h-8 w-8 rounded-lg border border-border bg-[#1b1b1b] text-text flex items-center justify-center hover:bg-[#252525] ${leftOpen ? 'opacity-100' : 'opacity-60'}`}
            title={leftOpen ? 'Hide left panel (Ctrl+B)' : 'Show left panel (Ctrl+B)'}
            onClick={onToggleLeft}
            aria-pressed={leftOpen}
            aria-label="Toggle left panel"
          >
            <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round"><rect x="3" y="5" width="6" height="14" rx="1.5"/><rect x="11" y="5" width="10" height="14" rx="1.5"/></svg>
          </button>
          <button
            className={`h-8 w-8 rounded-lg border border-border bg-[#1b1b1b] text-text flex items-center justify-center hover:bg-[#252525] ${rightOpen ? 'opacity-100' : 'opacity-60'}`}
            title={rightOpen ? 'Hide right panel (Ctrl+Alt+B)' : 'Show right panel (Ctrl+Alt+B)'}
            onClick={onToggleRight}
            aria-pressed={rightOpen}
            aria-label="Toggle right panel"
          >
            <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
              <rect x="15" y="5" width="6" height="14" rx="1.5" />
              <rect x="3" y="5" width="10" height="14" rx="1.5" />
            </svg>
          </button>
        </div>

        <input
          aria-label="Search filename, tags, notes"
          placeholder="Search..."
          onChange={e=>onSearch(e.target.value)}
          className="input h-8 w-[220px] focus:w-[280px] transition-all duration-200 rounded-lg px-2.5 border border-border bg-[#1b1b1b] text-text"
        />
      </div>
    </div>
  )
}
