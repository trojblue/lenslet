import React from 'react'

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
}){
  return (
    <div className="toolbar">
      <div className="toolbar-left">
        {viewerActive && (
          <button className="toolbar-back" onClick={onBack}>← Back</button>
        )}
        {!viewerActive && (
          <div style={{ display:'flex', gap:8, alignItems:'center' }}>
            <select className="input" style={{ height:28 }} value={sortKey||'added'} onChange={e=> onSortKey && onSortKey((e.target.value as any) || 'added')}>
              <option value="added">Date added</option>
              <option value="name">Filename</option>
            </select>
            <button className="toolbar-back" onClick={()=> onSortDir && onSortDir((sortDir||'desc')==='desc'?'asc':'desc')} title="Toggle sort">
              {(sortDir||'desc')==='desc' ? '↓' : '↑'}
            </button>
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
          placeholder="Search filename, tags, notes…"
          onChange={e=>onSearch(e.target.value)}
          className="input"
          style={{width: 360}}
        />
      </div>
    </div>
  )
}
