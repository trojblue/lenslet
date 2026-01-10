import { useCallback } from 'react'
import type { KeyboardEvent as ReactKeyboardEvent } from 'react'

interface FolderTreeKeyboardNavOptions {
  path: string
  isLeaf: boolean
  isExpanded: boolean
  setExpanded: (updater: (s: Set<string>) => Set<string>) => void
  onOpen: (path: string) => void
}

const TREE_ITEM_SELECTOR = '[role="tree"] [role="treeitem"]'

function getTreeItems(): HTMLElement[] {
  return Array.from(document.querySelectorAll(TREE_ITEM_SELECTOR)) as HTMLElement[]
}

function focusRelativeTreeItem(target: HTMLElement, key: string) {
  const items = getTreeItems()
  const idx = items.findIndex(el => el === target)
  if (idx === -1) return
  let nextIdx = idx
  if (key === 'ArrowDown') nextIdx = Math.min(items.length - 1, idx + 1)
  else if (key === 'ArrowUp') nextIdx = Math.max(0, idx - 1)
  else if (key === 'Home') nextIdx = 0
  else if (key === 'End') nextIdx = items.length - 1
  items[nextIdx]?.focus()
}

export function useFolderTreeKeyboardNav({
  path,
  isLeaf,
  isExpanded,
  setExpanded,
  onOpen,
}: FolderTreeKeyboardNavOptions) {
  return useCallback((e: ReactKeyboardEvent<HTMLElement>) => {
    if (e.key === 'Enter') {
      e.preventDefault()
      onOpen(path)
      return
    }

    if (e.key === 'ArrowRight') {
      if (!isLeaf && !isExpanded) {
        e.preventDefault()
        setExpanded(prev => {
          const next = new Set(prev)
          next.add(path)
          return next
        })
      }
      return
    }

    if (e.key === 'ArrowLeft') {
      if (!isLeaf && isExpanded) {
        e.preventDefault()
        setExpanded(prev => {
          const next = new Set(prev)
          next.delete(path)
          return next
        })
      }
      return
    }

    if (e.key === 'ArrowDown' || e.key === 'ArrowUp' || e.key === 'Home' || e.key === 'End') {
      e.preventDefault()
      focusRelativeTreeItem(e.currentTarget as HTMLElement, e.key)
    }
  }, [path, isLeaf, isExpanded, setExpanded, onOpen])
}
