import React from 'react'
import type { FolderIndex } from '../lib/types'

export default function FolderTree({ current, roots, data, onOpen, onResize }:{ current: string; roots: { label: string; path: string }[]; data?: FolderIndex; onOpen:(p:string)=>void; onResize?:(e:React.MouseEvent)=>void }){
  const join = (a: string, b: string) => {
    const aa = a.replace(/\/+$/, '')
    const bb = b.replace(/^\/+/, '')
    const joined = [aa, bb].filter(Boolean).join('/')
    return joined.startsWith('/') ? joined : `/${joined}`
  }
  return (
    <div className="sidebar">
      <div className="tree">
        {roots.map(r => (
          <div key={r.path} className={`tree-item ${current===r.path?'active':''}`} onClick={()=>onOpen(r.path)}>
            {r.label}
          </div>
        ))}
        {data?.dirs.map(dir => (
          <div key={dir.name} className={`tree-item ${current===join(current, dir.name)?'active':''}`} onClick={()=>onOpen(join(current, dir.name))}>
            📁 {dir.name}
          </div>
        ))}
      </div>
      <div className="resizer resizer-left" onMouseDown={onResize} />
    </div>
  )
}
