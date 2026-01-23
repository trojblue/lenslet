import React, { useCallback, useEffect, useRef, useState } from 'react'
import type { FolderIndex } from '../../lib/types'
import { useFolder } from '../../shared/api/folders'
import { api } from '../../shared/api/client'
import { middleTruncate } from '../../lib/util'
import { joinPath, sanitizePath } from '../../app/routing/hash'
import { useFolderTreeDragDrop } from './hooks/useFolderTreeDragDrop'
import { useFolderTreeKeyboardNav } from './hooks/useFolderTreeKeyboardNav'

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
  className?: string
  showResizeHandle?: boolean
}

export default function FolderTree({
  current,
  roots,
  data,
  onOpen,
  onResize,
  onContextMenu,
  className,
  showResizeHandle = true,
}: FolderTreeProps) {
  const [expanded, setExpanded] = useState<Set<string>>(new Set(['/']))
  const countCacheRef = useRef<Map<string, number>>(new Map())
  const inflightRef = useRef<Map<string, Promise<number>>>(new Map())

  const getSubtreeCount = useCallback(async (path: string, initial?: FolderIndex): Promise<number> => {
    const target = sanitizePath(path || '/')
    const cache = countCacheRef.current
    const inflight = inflightRef.current
    const cached = cache.get(target)
    if (cached !== undefined) return cached

    const pending = inflight.get(target)
    if (pending) return pending

    const promise = (async () => {
      let count = 0
      const seen = new Set<string>()
      const stack: Array<{ path: string; index?: FolderIndex }> = [{ path: target, index: initial }]

      while (stack.length) {
        const entry = stack.pop()!
        const { path: currentPath, index } = entry
        if (seen.has(currentPath)) continue
        seen.add(currentPath)

        let folder = index
        if (!folder) {
          try {
            folder = await api.getFolder(currentPath)
          } catch (err) {
            console.warn(`Failed to count folder ${currentPath}:`, err)
            continue
          }
        }

        count += folder.items.length
        for (const d of folder.dirs) {
          if (d.kind === 'branch') {
            stack.push({ path: joinPath(currentPath, d.name) })
          }
        }
      }

      cache.set(target, count)
      inflight.delete(target)
      return count
    })()

    inflight.set(target, promise)
    return promise
  }, [])

  useEffect(() => {
    const parts = current.split('/').filter(Boolean)
    const acc = ['/']
    let p = ''
    for (const part of parts) { p = p ? `${p}/${part}` : `/${part}`; acc.push(p) }
    setExpanded(prev => { const next = new Set(prev); for (const a of acc) next.add(a); return next })
  }, [current])

  const containerClass = className ?? 'h-full overflow-auto bg-panel scrollbar-thin'

  return (
    <div className={containerClass}>
      <div className="p-1" role="tree" aria-label="Folders">
        {roots.map(r => (
          <TreeNode key={r.path} path={r.path} label={r.label} depth={0} current={current} expanded={expanded} setExpanded={setExpanded} onOpen={onOpen} onContextMenu={onContextMenu} initial={data} getSubtreeCount={getSubtreeCount} />
        ))}
      </div>
      {showResizeHandle && (
        <div className="toolbar-offset absolute bottom-0 w-1.5 cursor-col-resize z-10 left-[calc(var(--left)-3px)] hover:bg-accent/20" onMouseDown={onResize} />
      )}
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
  getSubtreeCount: (path: string, initial?: FolderIndex) => Promise<number>
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
  getSubtreeCount,
}: TreeNodeProps) {
  const isExpanded = expanded.has(path)
  const { data } = useFolder(path)
  const idx = initial && path === initial.path ? initial : data
  const isActive = current === path
  const isLeaf = (idx?.dirs?.length ?? 0) === 0
  const [subtreeCount, setSubtreeCount] = useState<number | null>(idx ? idx.items.length : null)

  const onKeyDown = useFolderTreeKeyboardNav({
    path,
    isLeaf,
    isExpanded,
    setExpanded,
    onOpen,
  })

  const { onDragOver, onDragEnter, onDragLeave, onDrop } = useFolderTreeDragDrop({ path, isLeaf })

  const toggle = (e: React.MouseEvent) => {
    e.stopPropagation()
    setExpanded(prev => { const next = new Set(prev); if (next.has(path)) next.delete(path); else next.add(path); return next })
  }

  useEffect(() => {
    let cancelled = false
    if (!idx) {
      setSubtreeCount(null)
      return
    }
    setSubtreeCount(idx.items.length)
    getSubtreeCount(path, idx)
      .then((count) => {
        if (!cancelled) setSubtreeCount(count)
      })
      .catch((err) => {
        if (!cancelled) console.warn(`Failed to compute subtree count for ${path}:`, err)
      })
    return () => {
      cancelled = true
    }
  }, [idx, path, getSubtreeCount])

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
        onKeyDown={onKeyDown}
        onDragOver={onDragOver}
        onDragEnter={onDragEnter}
        onDragLeave={onDragLeave}
        onDrop={onDrop}
      >
        <span className="w-4 text-center opacity-60 hover:opacity-100 text-[10px]" onClick={toggle}>{isExpanded? '▼' : '▶'}</span>
        <span className="flex-1 overflow-hidden truncate text-sm" title={label}>{middleTruncate(label, 28)}</span>
        {subtreeCount !== null && (
          <span className="text-[10px] opacity-50 bg-white/5 border border-white/5 rounded px-1.5 min-w-[24px] text-center">
            {subtreeCount}
          </span>
        )}
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
          getSubtreeCount={getSubtreeCount}
        />
      ))}
    </div>
  )
}
