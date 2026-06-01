import { useCallback, useEffect, useState } from 'react'
import type { Dispatch, SetStateAction } from 'react'
import type { ContextMenuState } from '../../lib/types'

type UseAppActionsParams = {
  selectedPaths: string[]
  setSelectedPaths: Dispatch<SetStateAction<string[]>>
}

type UseAppActionsResult = {
  ctx: ContextMenuState | null
  setCtx: Dispatch<SetStateAction<ContextMenuState | null>>
  openGridActions: (targetPath: string, anchor: { x: number; y: number }) => void
  openFolderActions: (path: string, anchor: { x: number; y: number }) => void
}

function dedupePaths(paths: string[]): string[] {
  return Array.from(new Set(paths.filter(Boolean)))
}

export function useAppActions({
  selectedPaths,
  setSelectedPaths,
}: UseAppActionsParams): UseAppActionsResult {
  const [ctx, setCtx] = useState<ContextMenuState | null>(null)

  const resolveGridActionPaths = useCallback((targetPath: string): string[] => {
    const currentSelection = dedupePaths(selectedPaths)
    if (currentSelection.includes(targetPath)) return currentSelection
    return [targetPath]
  }, [selectedPaths])

  const openGridActions = useCallback((targetPath: string, anchor: { x: number; y: number }) => {
    const paths = resolveGridActionPaths(targetPath)
    setSelectedPaths(paths)
    setCtx({ x: anchor.x, y: anchor.y, kind: 'grid', payload: { paths } })
  }, [resolveGridActionPaths, setSelectedPaths])

  const openFolderActions = useCallback((path: string, anchor: { x: number; y: number }) => {
    setCtx({ x: anchor.x, y: anchor.y, kind: 'tree', payload: { path } })
  }, [])

  useEffect(() => {
    const onGlobalClick = () => setCtx(null)
    const onEsc = (e: KeyboardEvent) => {
      if (e.key === 'Escape') setCtx(null)
    }

    window.addEventListener('click', onGlobalClick)
    window.addEventListener('keydown', onEsc)

    return () => {
      window.removeEventListener('click', onGlobalClick)
      window.removeEventListener('keydown', onEsc)
    }
  }, [])

  return {
    ctx,
    setCtx,
    openGridActions,
    openFolderActions,
  }
}
