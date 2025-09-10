import React, { useEffect, useMemo, useState } from 'react'
import type { FolderIndex } from '../lib/types'
import { useFolder } from '../api/folders'

type Root = { label: string; path: string }

export default function FolderTree({ current, roots, data, onOpen, onResize }:{ current: string; roots: Root[]; data?: FolderIndex; onOpen:(p:string)=>void; onResize?:(e:React.MouseEvent)=>void }){
  const [expanded, setExpanded] = useState<Set<string>>(new Set(['/']))

  useEffect(() => {
    // auto-expand ancestors of the current path
    const parts = current.split('/').filter(Boolean)
    const acc = ['/']
    let p = ''
    for (const part of parts) {
      p = p ? `${p}/${part}` : `/${part}`
      acc.push(p)
    }
    setExpanded(prev => {
      const next = new Set(prev)
      for (const a of acc) next.add(a)
      return next
    })
  }, [current])

  return (
    <div className="sidebar">
      <div className="tree">
        {roots.map(r => (
          <TreeNode key={r.path} path={r.path} label={r.label} depth={0} current={current} expanded={expanded} setExpanded={setExpanded} onOpen={onOpen} initial={data} />
        ))}
      </div>
      <div className="resizer resizer-left" onMouseDown={onResize} />
    </div>
  )
}

function joinPath(a: string, b: string) {
  const aa = a.replace(/\/+$/, '')
  const bb = b.replace(/^\/+/, '')
  const joined = [aa, bb].filter(Boolean).join('/')
  return joined.startsWith('/') ? joined : `/${joined}`
}

function TreeNode({ path, label, depth, current, expanded, setExpanded, onOpen, initial }:{ path:string; label:string; depth:number; current:string; expanded:Set<string>; setExpanded:(u:(s:Set<string>)=>Set<string>)=>void; onOpen:(p:string)=>void; initial?:FolderIndex }){
  const isExpanded = expanded.has(path)
  const { data } = useFolder(path)
  const idx = initial && path === initial.path ? initial : data
  const isActive = current === path
  const isLeaf = (idx?.items?.length ?? 0) > 0
  const count = isLeaf ? idx?.items?.length ?? 0 : 0

  const toggle = (e: React.MouseEvent) => {
    e.stopPropagation()
    setExpanded(prev => {
      const next = new Set(prev)
      if (next.has(path)) next.delete(path); else next.add(path)
      return next
    })
  }

  return (
    <div>
      <div className={`tree-item ${isActive?'active':''}`} style={{ paddingLeft: 8 + depth * 14 }} onClick={()=> onOpen(path)}>
        <span className="tree-toggle" onClick={toggle}>{isExpanded? '▾' : '▸'}</span>
        <span className="tree-label">{label}</span>
        {isLeaf && <span className="tree-count">{count}</span>}
      </div>
      {isExpanded && idx?.dirs?.map(d => (
        <TreeNode key={d.name} path={joinPath(path, d.name)} label={d.name} depth={depth+1} current={current} expanded={expanded} setExpanded={setExpanded} onOpen={onOpen} />
      ))}
    </div>
  )
}
