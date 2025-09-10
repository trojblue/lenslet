import React from 'react'

export default function Toolbar({
  onSearch,
  viewerActive,
  onBack,
  zoomPercent,
  onZoomPercentChange,
}:{
  onSearch: (q: string) => void
  viewerActive?: boolean
  onBack?: () => void
  zoomPercent?: number
  onZoomPercentChange?: (p: number) => void
}){
  return (
    <div className="toolbar">
      <div className="toolbar-left">
        {viewerActive && (
          <button className="toolbar-back" onClick={onBack}>← Back</button>
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
