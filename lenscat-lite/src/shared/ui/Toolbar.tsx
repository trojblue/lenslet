import React, { useEffect, useRef, useState } from 'react'

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
    <div className="toolbar">
      <div className="toolbar-left">
        {viewerActive && (
          <button className="toolbar-back" onClick={onBack}>← Back</button>
        )}
        {!viewerActive && (
          <div style={{ display:'flex', gap:8, alignItems:'center', position:'relative' }}>
            <select className="input" style={{ height:28 }} value={sortKey||'added'} onChange={e=> onSortKey && onSortKey((e.target.value as any) || 'added')}>
              <option value="added">Date added</option>
              <option value="name">Filename</option>
            </select>
            <button className="toolbar-back" onClick={()=> onSortDir && onSortDir((sortDir||'desc')==='desc'?'asc':'desc')} title="Toggle sort">
              {(sortDir||'desc')==='desc' ? '↓' : '↑'}
            </button>
            <div ref={ratingRef}>
              <button className="toolbar-back" onClick={()=> setOpenRating(v=>!v)} title="Filter by rating" style={{ height:28, padding:'0 10px', display:'flex', alignItems:'center', gap:6 }}>
                <span style={{ fontSize:14 }}>★</span>
                <span style={{ fontSize:13 }}>Rating</span>
              </button>
              {openRating && (
                <div style={{ position:'absolute', top:38, left:0, background:'#1b1b1b', border:'1px solid var(--border)', borderRadius:8, padding:6, boxShadow:'0 10px 26px rgba(0,0,0,0.35)', width:200 }}>
                  {[5,4,3,2,1].map(v => {
                    const active = !!(starFilters||[]).includes(v)
                    const count = starCounts?.[String(v)] ?? 0
                    return (
                      <div key={v} onClick={()=> onToggleStar && onToggleStar(v)} style={{ display:'flex', alignItems:'center', justifyContent:'space-between', padding:'4px 6px', borderRadius:6, cursor:'pointer', background: active? 'rgba(58,143,255,0.15)':'transparent' }}>
                        <div style={{ color: active? '#ffd166' : 'var(--text)', fontSize:13 }}>{'★'.repeat(v)}{'☆'.repeat(5-v)}</div>
                        <div style={{ opacity:0.8, fontSize:12 }}>{count}</div>
                      </div>
                    )
                  })}
                  {(() => { const activeNone = !!(starFilters||[]).includes(0); return (
                    <div onClick={()=> onToggleStar && onToggleStar(0)} style={{ display:'flex', alignItems:'center', justifyContent:'space-between', padding:'4px 6px', borderRadius:6, cursor:'pointer', background: activeNone? 'rgba(58,143,255,0.15)':'transparent' }}>
                      <div style={{ fontSize:13, color: activeNone? 'var(--text)' : 'var(--text)' }}>None</div>
                      <div style={{ opacity:0.8, fontSize:12 }}>{starCounts?.['0'] ?? 0}</div>
                    </div>
                  )})()}
                  <div style={{ height:1, background:'var(--border)', margin:'6px 0' }} />
                  <div style={{ display:'flex', gap:8 }}>
                    <button className="toolbar-back" onClick={onClearStars} style={{ height:26, padding:'0 10px' }}>All</button>
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
                <div className="filter-pill" aria-label={`Rating filter active: ${label}`} title={`Rating filter: ${label}`}>
                  <span className="filter-pill-star">★</span>
                  <span className="filter-pill-text">{label}</span>
                  <button className="filter-pill-close" aria-label="Clear rating filter" onClick={onClearStars}>×</button>
                </div>
              )
            })()}
          </div>
        )}
      </div>

      {viewerActive && (
        <div className="toolbar-center">
          <input
            type="range"
            min={5}
            max={800}
            step={1}
            value={Math.round(Math.max(5, Math.min(800, zoomPercent ?? 100)))}
            onChange={e => onZoomPercentChange && onZoomPercentChange(Number(e.target.value))}
            className="zoom-slider"
          />
          <span className="zoom-label">{Math.round(zoomPercent ?? 100)}%</span>
        </div>
      )}

      <div className="toolbar-right">
        <input
          aria-label="Search filename, tags, notes"
          placeholder="Search filename, tags, notes…"
          onChange={e=>onSearch(e.target.value)}
          className="input"
          style={{width: 360}}
        />
      </div>
    </div>
  )
}


