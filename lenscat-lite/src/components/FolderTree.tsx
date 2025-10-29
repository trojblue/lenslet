import React, { useEffect, useMemo, useState } from 'react'
import type { FolderIndex } from '../lib/types'
import { useFolder } from '../api/folders'
import { api } from '../api/client'
import { useQueryClient } from '@tanstack/react-query'
import { middleTruncate } from '../lib/util'

type Root = { label: string; path: string }

export default function FolderTree({ current, roots, data, onOpen, onResize, onContextMenu }:{ current: string; roots: Root[]; data?: FolderIndex; onOpen:(p:string)=>void; onResize?:(e:React.MouseEvent)=>void; onContextMenu?:(e:React.MouseEvent, path:string)=>void }){
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
          <TreeNode key={r.path} path={r.path} label={r.label} depth={0} current={current} expanded={expanded} setExpanded={setExpanded} onOpen={onOpen} onContextMenu={onContextMenu} initial={data} />
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

function TreeNode({ path, label, depth, current, expanded, setExpanded, onOpen, onContextMenu, initial }:{ path:string; label:string; depth:number; current:string; expanded:Set<string>; setExpanded:(u:(s:Set<string>)=>Set<string>)=>void; onOpen:(p:string)=>void; onContextMenu?:(e:React.MouseEvent, path:string)=>void; initial?:FolderIndex }){
  const isExpanded = expanded.has(path)
  const { data } = useFolder(path)
  const idx = initial && path === initial.path ? initial : data
  const isActive = current === path
  const isLeaf = (idx?.dirs?.length ?? 0) === 0
  const count = isLeaf ? idx?.items?.length ?? 0 : 0
  const qc = useQueryClient()

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
      <div
        className={`tree-item ${isActive?'active':''}`}
        style={{ paddingLeft: 8 + depth * 14, outline: 'none' }}
        onClick={()=> onOpen(path)}
        onContextMenu={(e)=> { e.preventDefault(); e.stopPropagation(); onContextMenu && onContextMenu(e, path) }}
        onDragOver={(e)=>{
          const types = Array.from(e.dataTransfer?.types || [])
          if (types.includes('application/x-lenscat-paths')) {
            e.preventDefault()
            // keep target highlighted while cursor is anywhere over the row
            if (isLeaf) {
              // ensure only one drop-target at a time
              document.querySelectorAll('.tree-item.drop-target').forEach(el => { if (el !== e.currentTarget) el.classList.remove('drop-target') })
              ;(e.currentTarget as HTMLElement).classList.add('drop-target')
            }
          }
        }}
        onDragEnter={(e)=>{
          const types = Array.from(e.dataTransfer?.types || [])
          if ((types.includes('application/x-lenscat-paths')) && isLeaf) {
            e.preventDefault()
            // ensure only one drop-target at a time
            document.querySelectorAll('.tree-item.drop-target').forEach(el => { if (el !== e.currentTarget) el.classList.remove('drop-target') })
            ;(e.currentTarget as HTMLElement).classList.add('drop-target')
          }
        }}
        onDragLeave={(e)=>{
          // Only remove highlight if cursor truly left the element (not moving between children)
          const target = e.currentTarget as HTMLElement
          const over = document.elementFromPoint(e.clientX, e.clientY)
          if (over && target.contains(over)) return
          target.classList.remove('drop-target')
        }}
        onDrop={async (e)=>{
          const dt = e.dataTransfer
          if (!dt) return
          e.preventDefault()
          ;(e.currentTarget as HTMLElement).classList.remove('drop-target')
          const multi = dt.getData('application/x-lenscat-paths')
          const paths: string[] = multi ? JSON.parse(multi) : []
          const filtered = paths.filter(Boolean)
          if (!filtered.length) return
          let srcDir = filtered[0].split('/').slice(0,-1).join('/') || '/'
          if (!srcDir.startsWith('/')) srcDir = `/${srcDir}`
          let destPath = path
          if (!destPath.startsWith('/')) destPath = `/${destPath}`
          try {
            for (const p of filtered) { await api.moveFile(p, destPath) }
            // Invalidate/refetch both folders
            qc.invalidateQueries({ queryKey: ['folder', srcDir] })
            qc.invalidateQueries({ queryKey: ['folder', destPath] })
            // Optimistically update source folder cache to immediately remove item and adjust count
            qc.setQueryData<any>(['folder', srcDir], (old) => {
              if (!old || !Array.isArray(old.items)) return old
              const next = { ...old, items: old.items.filter((i: any) => !filtered.includes(i.path)) }
              return next
            })
          } catch {}
        }}
      >
        <span className="tree-toggle" onClick={toggle}>{isExpanded? '▾' : '▸'}</span>
        <span className="tree-label" title={label}>{middleTruncate(label, 28)}</span>
        {isLeaf && <span className="tree-count">{count}</span>}
      </div>
      {isExpanded && idx?.dirs?.map(d => (
        <TreeNode key={d.name} path={joinPath(path, d.name)} label={d.name} depth={depth+1} current={current} expanded={expanded} setExpanded={setExpanded} onOpen={onOpen} />
      ))}
    </div>
  )
}
