import React from 'react'
import type { FolderIndex } from '../lib/types'

export default function FolderTree({ current, roots, onOpen }:{ current: string; roots: { label: string; path: string }[]; onOpen:(p:string)=>void }){
  return (
    <div className="sidebar">
      <div className="tree">
        {roots.map(r => (
          <div key={r.path} className={`tree-item ${current===r.path?'active':''}`} onClick={()=>onOpen(r.path)}>
            {r.label}
          </div>
        ))}
      </div>
    </div>
  )
}
