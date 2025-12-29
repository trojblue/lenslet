import React, { useEffect, useState, useCallback } from 'react'
import type { FolderIndex } from '../../lib/types'
import { useFolder } from '../../shared/api/folders'
import { api } from '../../shared/api/client'
import { useQueryClient } from '@tanstack/react-query'
import { middleTruncate } from '../../lib/util'
import { joinPath } from '../../app/routing/hash'

interface Root {
  label: string
  path: string
}

interface FolderTreeProps {
  current: string
  roots: Root[]
  data?: FolderIndex
  onOpen: (path: string) => void
  onResize?: (e: React.MouseEvent) => void
  onContextMenu?: (e: React.MouseEvent, path: string) => void
}

export default function FolderTree({
  current,
  roots,
  data,
  onOpen,
  onResize,
  onContextMenu,
}: FolderTreeProps) {
  const [expanded, setExpanded] = useState<Set<string>>(new Set(['/']))

  useEffect(() => {
    const parts = current.split('/').filter(Boolean)
    const acc = ['/']
    let p = ''
    for (const part of parts) { p = p ? `${p}/${part}` : `/${part}`; acc.push(p) }
    setExpanded(prev => { const next = new Set(prev); for (const a of acc) next.add(a); return next })
  }, [current])

  return (
    <div className="col-start-1 row-start-2 overflow-auto border-r border-border bg-panel scrollbar-thin">
      <div className="p-1" role="tree" aria-label="Folders">
        {roots.map(r => (
          <TreeNode key={r.path} path={r.path} label={r.label} depth={0} current={current} expanded={expanded} setExpanded={setExpanded} onOpen={onOpen} onContextMenu={onContextMenu} initial={data} />
        ))}
      </div>
      <div className="absolute top-12 bottom-0 w-1.5 cursor-col-resize z-10 left-[calc(var(--left)-3px)] hover:bg-accent/20" onMouseDown={onResize} />
    </div>
  )
}

interface TreeNodeProps {
  path: string
  label: string
  depth: number
  current: string
  expanded: Set<string>
  setExpanded: (updater: (s: Set<string>) => Set<string>) => void
  onOpen: (path: string) => void
  onContextMenu?: (e: React.MouseEvent, path: string) => void
  initial?: FolderIndex
}

function TreeNode({
  path,
  label,
  depth,
  current,
  expanded,
  setExpanded,
  onOpen,
  onContextMenu,
  initial,
}: TreeNodeProps) {
  const isExpanded = expanded.has(path)
  const { data } = useFolder(path)
  const idx = initial && path === initial.path ? initial : data
  const isActive = current === path
  const isLeaf = (idx?.dirs?.length ?? 0) === 0
  const count = isLeaf ? idx?.items?.length ?? 0 : 0
  const qc = useQueryClient()

  const toggle = (e: React.MouseEvent) => {
    e.stopPropagation()
    setExpanded(prev => { const next = new Set(prev); if (next.has(path)) next.delete(path); else next.add(path); return next })
  }

  return (
    <div>
      <div
        className={`flex items-center gap-1.5 py-0.5 px-2 rounded-md cursor-pointer min-h-[28px] outline-none transition-colors duration-75 ${isActive ? 'bg-accent/20 text-accent font-medium' : 'hover:bg-white/5 text-text'}`}
        role="treeitem"
        aria-level={depth+1}
        aria-expanded={isLeaf ? undefined : isExpanded}
        aria-selected={isActive}
        tabIndex={isActive ? 0 : -1}
        style={{ paddingLeft: 8 + depth * 14 }}
        onClick={()=> onOpen(path)}
        onContextMenu={(e)=> { e.preventDefault(); e.stopPropagation(); onContextMenu && onContextMenu(e, path) }}
        onKeyDown={(e)=>{
          if (e.key === 'Enter') { e.preventDefault(); onOpen(path) }
          else if (e.key === 'ArrowRight') { if (!isLeaf && !isExpanded) { e.preventDefault(); setExpanded(prev => { const next = new Set(prev); next.add(path); return next }) } }
          else if (e.key === 'ArrowLeft') { if (!isLeaf && isExpanded) { e.preventDefault(); setExpanded(prev => { const next = new Set(prev); next.delete(path); return next }) } }
          else if (e.key === 'ArrowDown' || e.key === 'ArrowUp' || e.key === 'Home' || e.key === 'End') {
            e.preventDefault()
            const items = Array.from(document.querySelectorAll('[role="tree"] [role="treeitem"]')) as HTMLElement[]
            const idx = items.findIndex(el => el === e.currentTarget)
            if (idx === -1) return
            let nextIdx = idx
            if (e.key === 'ArrowDown') nextIdx = Math.min(items.length - 1, idx + 1)
            else if (e.key === 'ArrowUp') nextIdx = Math.max(0, idx - 1)
            else if (e.key === 'Home') nextIdx = 0
            else if (e.key === 'End') nextIdx = items.length - 1
            items[nextIdx]?.focus()
          }
        }}
        onDragOver={(e)=>{
          const types = Array.from(e.dataTransfer?.types || [])
          if (types.includes('application/x-lenslet-paths')) {
            e.preventDefault()
            if (isLeaf) {
              document.querySelectorAll('[role="treeitem"].drop-target').forEach(el => { if (el !== e.currentTarget) el.classList.remove('drop-target') })
              ;(e.currentTarget as HTMLElement).classList.add('drop-target')
            }
          }
        }}
        onDragEnter={(e)=>{
          const types = Array.from(e.dataTransfer?.types || [])
          if ((types.includes('application/x-lenslet-paths')) && isLeaf) {
            e.preventDefault()
            document.querySelectorAll('[role="treeitem"].drop-target').forEach(el => { if (el !== e.currentTarget) el.classList.remove('drop-target') })
            ;(e.currentTarget as HTMLElement).classList.add('drop-target')
          }
        }}
        onDragLeave={(e)=>{
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
          const multi = dt.getData('application/x-lenslet-paths')
          const paths: string[] = multi ? JSON.parse(multi) : []
          const filtered = paths.filter(Boolean)
          if (!filtered.length) return
          let srcDir = filtered[0].split('/').slice(0,-1).join('/') || '/'
          if (!srcDir.startsWith('/')) srcDir = `/${srcDir}`
          let destPath = path
          if (!destPath.startsWith('/')) destPath = `/${destPath}`
          try {
            for (const p of filtered) { await api.moveFile(p, destPath) }
            qc.invalidateQueries({ queryKey: ['folder', srcDir] })
            qc.invalidateQueries({ queryKey: ['folder', destPath] })
            qc.setQueryData<FolderIndex | undefined>(['folder', srcDir], (old) => {
              if (!old || !Array.isArray(old.items)) return old
              return { ...old, items: old.items.filter((i) => !filtered.includes(i.path)) }
            })
          } catch {}
        }}
      >
        <span className="w-4 text-center opacity-60 hover:opacity-100 text-[10px]" onClick={toggle}>{isExpanded? '▼' : '▶'}</span>
        <span className="flex-1 overflow-hidden truncate text-sm" title={label}>{middleTruncate(label, 28)}</span>
        {isLeaf && <span className="text-[10px] opacity-50 bg-white/5 border border-white/5 rounded px-1.5 min-w-[24px] text-center">{count}</span>}
      </div>
      {isExpanded && idx?.dirs?.map(d => (
        <TreeNode
          key={d.name}
          path={joinPath(path, d.name)}
          label={d.name}
          depth={depth+1}
          current={current}
          expanded={expanded}
          setExpanded={setExpanded}
          onOpen={onOpen}
          onContextMenu={onContextMenu}
        />
      ))}
    </div>
  )
}
