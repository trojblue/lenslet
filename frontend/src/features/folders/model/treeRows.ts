import type { BrowseFolderPayload } from '../../../lib/types'
import { joinPath } from '../../../lib/paths'

export type FolderRoot = { label: string; path: string }
export type FolderTreeRow = {
  kind: 'folder' | 'pending' | 'error'
  path: string
  label: string
  depth: number
  position: number
  siblings: number
  expanded: boolean
  leaf: boolean
  payload?: BrowseFolderPayload
}

export function expandedAncestorPaths(path: string): string[] {
  const ancestors = ['/']
  let current = ''
  for (const part of path.split('/').filter(Boolean)) {
    current = `${current}/${part}`
    ancestors.push(current)
  }
  return ancestors
}

export function flattenFolderRows(
  roots: readonly FolderRoot[],
  expanded: ReadonlySet<string>,
  payloads: Readonly<Record<string, BrowseFolderPayload | undefined>>,
  errors: ReadonlySet<string>,
): FolderTreeRow[] {
  const rows: FolderTreeRow[] = []
  const append = (entries: readonly FolderRoot[], depth: number) => {
    entries.forEach((entry, index) => {
      const payload = payloads[entry.path]
      const leaf = !!payload && payload.folders.length === 0
      const open = expanded.has(entry.path) && !leaf
      rows.push({
        kind: 'folder', path: entry.path, label: entry.label, depth,
        position: index + 1, siblings: entries.length, expanded: open, leaf, payload,
      })
      if (!open) return
      if (!payload) {
        rows.push({
          kind: errors.has(entry.path) ? 'error' : 'pending',
          path: entry.path, label: entry.label, depth: depth + 1,
          position: 1, siblings: 1, expanded: false, leaf: true,
        })
        return
      }
      append(payload.folders.map((folder) => ({
        label: folder.name, path: joinPath(entry.path, folder.name),
      })), depth + 1)
    })
  }
  append(roots, 0)
  return rows
}

export function folderKeyboardTarget(rows: readonly FolderTreeRow[], path: string, key: string): number {
  const index = rows.findIndex((row) => row.kind === 'folder' && row.path === path)
  if (index < 0) return -1
  if (key === 'Home') return rows.findIndex((row) => row.kind === 'folder')
  if (key === 'End') {
    for (let i = rows.length - 1; i >= 0; i--) if (rows[i].kind === 'folder') return i
  }
  const direction = key === 'ArrowUp' ? -1 : key === 'ArrowDown' ? 1 : 0
  if (!direction) return index
  for (let i = index + direction; i >= 0 && i < rows.length; i += direction) {
    if (rows[i].kind === 'folder') return i
  }
  return index
}
