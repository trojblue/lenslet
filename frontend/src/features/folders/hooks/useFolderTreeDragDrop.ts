import { useCallback } from 'react'
import type { DragEvent as ReactDragEvent } from 'react'
import { useQueryClient } from '@tanstack/react-query'
import type { FolderIndex } from '../../../lib/types'
import { api } from '../../../shared/api/client'

interface FolderTreeDragDropOptions {
  path: string
  isLeaf: boolean
}

const LENSLET_PATHS_MIME = 'application/x-lenslet-paths'
const DROP_TARGET_SELECTOR = '[role="treeitem"].drop-target'

function hasLensletPaths(e: ReactDragEvent<HTMLElement>): boolean {
  const types = Array.from(e.dataTransfer?.types || [])
  return types.includes(LENSLET_PATHS_MIME)
}

function clearDropTargets(except?: HTMLElement) {
  document.querySelectorAll(DROP_TARGET_SELECTOR).forEach(el => {
    if (el !== except) el.classList.remove('drop-target')
  })
}

function setDropTarget(target: HTMLElement) {
  clearDropTargets(target)
  target.classList.add('drop-target')
}

function normalizePath(path: string): string {
  return path.startsWith('/') ? path : `/${path}`
}

export function useFolderTreeDragDrop({ path, isLeaf }: FolderTreeDragDropOptions) {
  const qc = useQueryClient()

  const onDragOver = useCallback((e: ReactDragEvent<HTMLElement>) => {
    if (!hasLensletPaths(e)) return
    e.preventDefault()
    if (!isLeaf) return
    setDropTarget(e.currentTarget as HTMLElement)
  }, [isLeaf])

  const onDragEnter = useCallback((e: ReactDragEvent<HTMLElement>) => {
    if (!isLeaf || !hasLensletPaths(e)) return
    e.preventDefault()
    setDropTarget(e.currentTarget as HTMLElement)
  }, [isLeaf])

  const onDragLeave = useCallback((e: ReactDragEvent<HTMLElement>) => {
    const target = e.currentTarget as HTMLElement
    const over = document.elementFromPoint(e.clientX, e.clientY)
    if (over && target.contains(over)) return
    target.classList.remove('drop-target')
  }, [])

  const onDrop = useCallback(async (e: ReactDragEvent<HTMLElement>) => {
    const dt = e.dataTransfer
    if (!dt) return
    e.preventDefault()
    ;(e.currentTarget as HTMLElement).classList.remove('drop-target')
    const multi = dt.getData(LENSLET_PATHS_MIME)
    const paths: string[] = multi ? JSON.parse(multi) : []
    const filtered = paths.filter(Boolean)
    if (!filtered.length) return
    let srcDir = filtered[0].split('/').slice(0, -1).join('/') || '/'
    srcDir = normalizePath(srcDir)
    const destPath = normalizePath(path)
    try {
      for (const p of filtered) {
        await api.moveFile(p, destPath)
      }
      qc.invalidateQueries({ queryKey: ['folder', srcDir] })
      qc.invalidateQueries({ queryKey: ['folder', destPath] })
      qc.setQueryData<FolderIndex | undefined>(['folder', srcDir], (old) => {
        if (!old || !Array.isArray(old.items)) return old
        return { ...old, items: old.items.filter((i) => !filtered.includes(i.path)) }
      })
    } catch {}
  }, [path, qc])

  return { onDragOver, onDragEnter, onDragLeave, onDrop }
}
