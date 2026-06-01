import { useEffect, useRef, type Dispatch, type SetStateAction } from 'react'
import { useLatestRef } from '../../shared/hooks/useLatestRef'
import { readHash, resolveHashTargets } from '../routing/hash'
import { resolveScopeFromHashTarget } from '../utils/appShellHelpers'

type UseAppHashRoutingParams = {
  setCurrent: Dispatch<SetStateAction<string>>
  syncHashImageSelection: (path: string | null) => void
  bumpRestoreGridToSelectionToken: () => void
}

export function useAppHashRouting({
  setCurrent,
  syncHashImageSelection,
  bumpRestoreGridToSelectionToken,
}: UseAppHashRoutingParams): void {
  const initialHashSyncRef = useRef(false)
  const syncHashImageSelectionRef = useLatestRef(syncHashImageSelection)
  const bumpRestoreGridToSelectionTokenRef = useLatestRef(bumpRestoreGridToSelectionToken)

  useEffect(() => {
    const applyHash = (raw: string) => {
      const { folderTarget, imageTarget } = resolveHashTargets(raw)
      const isInitialHashSync = !initialHashSyncRef.current
      initialHashSyncRef.current = true
      syncHashImageSelectionRef.current(imageTarget)
      setCurrent((prev) => {
        const nextScope = resolveScopeFromHashTarget(
          prev,
          folderTarget,
          imageTarget,
          isInitialHashSync,
        )
        if (prev === nextScope) return prev
        bumpRestoreGridToSelectionTokenRef.current()
        return nextScope
      })
    }

    applyHash(readHash())
    const onHash = () => applyHash(readHash())
    window.addEventListener('hashchange', onHash)
    return () => window.removeEventListener('hashchange', onHash)
  }, [bumpRestoreGridToSelectionTokenRef, setCurrent, syncHashImageSelectionRef])
}
