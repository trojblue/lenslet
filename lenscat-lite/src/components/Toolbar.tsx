import React from 'react'
export default function Toolbar({ onSearch }: { onSearch: (q: string) => void }) {
  return (
    <div className="toolbar">
      <input placeholder="Search filename, tags, notes…" onChange={e=>onSearch(e.target.value)} className="input" style={{width: 360}} />
    </div>
  )
}
