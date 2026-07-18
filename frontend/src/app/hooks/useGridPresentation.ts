import { useEffect, useLayoutEffect, useRef, useState } from 'react'
import type { BrowseItemPayload } from '../../lib/types'
import type { GridStatus } from '../model/loadingState'

export const GRID_PRESENTATION_GRACE_MS = 800

export type GridPresentationPhase = 'steady' | 'grace' | 'loading'

export type GridPresentation = {
  items: BrowseItemPayload[]
  phase: GridPresentationPhase
  retained: boolean
}

export function resolveGridPresentation({
  targetItems,
  previousItems,
  pending,
  graceExpired,
}: {
  targetItems: BrowseItemPayload[]
  previousItems: BrowseItemPayload[]
  pending: boolean
  graceExpired: boolean
}): GridPresentation {
  if (!pending) return { items: targetItems, phase: 'steady', retained: false }
  if (!previousItems.length || graceExpired) {
    return { items: targetItems, phase: 'loading', retained: false }
  }
  return { items: previousItems, phase: 'grace', retained: true }
}

export function useGridPresentation({
  targetKey,
  targetItems,
  targetStatus,
}: {
  targetKey: string
  targetItems: BrowseItemPayload[]
  targetStatus: GridStatus
}): GridPresentation {
  const previousItemsRef = useRef<BrowseItemPayload[]>([])
  const [expiredTargetKey, setExpiredTargetKey] = useState<string | null>(null)
  const pending = targetStatus.kind === 'loading' && targetItems.length === 0
  const canRetain = pending && previousItemsRef.current.length > 0

  useLayoutEffect(() => {
    setExpiredTargetKey(null)
  }, [targetKey])

  useEffect(() => {
    if (!canRetain) return
    const timeoutId = window.setTimeout(() => {
      setExpiredTargetKey(targetKey)
    }, GRID_PRESENTATION_GRACE_MS)
    return () => window.clearTimeout(timeoutId)
  }, [canRetain, targetKey])

  useLayoutEffect(() => {
    if (pending) return
    setExpiredTargetKey(null)
    previousItemsRef.current = targetStatus.kind === 'ready' || targetStatus.kind === 'updating'
      ? targetItems
      : []
  }, [pending, targetItems, targetKey, targetStatus.kind])

  return resolveGridPresentation({
    targetItems,
    previousItems: previousItemsRef.current,
    pending,
    graceExpired: expiredTargetKey === targetKey,
  })
}
