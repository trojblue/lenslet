import { useEffect, type MutableRefObject } from 'react'
import { selectNeighborImage } from '../model/board'
import {
  getBoardKeyAction,
  getFullscreenKeyAction,
  shouldIgnoreRankingHotkey,
} from '../model/keyboard'
import type { InstanceSession } from '../model/session'
import type { RankingInstance } from '../types'
import type { MoveRankOptions } from './useRankingSession'

const INTERACTIVE_CONTROL_SELECTOR = 'button, a, [role="button"]'

type UseRankingKeyboardParams = {
  closeFullscreen: () => void
  currentInstance: RankingInstance | null
  currentSession: InstanceSession | null
  focusCard: (imageId: string | null) => void
  fullscreenImageId: string | null
  goNext: () => void
  goPrev: () => void
  moveCurrentImageToRank: (
    imageId: string,
    rankIndex: number | null,
    options?: MoveRankOptions,
  ) => void
  navigateFullscreenImage: (direction: 'prev' | 'next') => void
  openFullscreenForImage: (imageId: string) => void
  selectCurrentImage: (imageId: string) => void
  sessionsRef: MutableRefObject<Record<string, InstanceSession>>
}

export function useRankingKeyboard({
  closeFullscreen,
  currentInstance,
  currentSession,
  focusCard,
  fullscreenImageId,
  goNext,
  goPrev,
  moveCurrentImageToRank,
  navigateFullscreenImage,
  openFullscreenForImage,
  selectCurrentImage,
  sessionsRef,
}: UseRankingKeyboardParams) {
  useEffect(() => {
    if (!currentSession || !currentInstance) return
    const onKeyDown = (event: KeyboardEvent) => {
      const target = event.target instanceof HTMLElement ? event.target : null
      if (
        shouldIgnoreRankingHotkey(event.key, {
          isContentEditable: Boolean(target?.isContentEditable),
          tagName: target?.tagName ?? null,
          insideInteractiveControl: Boolean(target?.closest(INTERACTIVE_CONTROL_SELECTOR)),
        })
      ) {
        return
      }

      if (fullscreenImageId) {
        const fullscreenAction = getFullscreenKeyAction(event.key, currentInstance.max_ranks)
        if (fullscreenAction.type === 'assign-rank') {
          event.preventDefault()
          moveCurrentImageToRank(fullscreenImageId, fullscreenAction.rankIndex)
          selectCurrentImage(fullscreenImageId)
          return
        }
        if (fullscreenAction.type === 'fullscreen-nav') {
          event.preventDefault()
          navigateFullscreenImage(fullscreenAction.direction)
          return
        }
        if (fullscreenAction.type === 'fullscreen-close') {
          event.preventDefault()
          closeFullscreen()
        }
        return
      }

      const boardAction = getBoardKeyAction(event.key, currentInstance.max_ranks)
      if (boardAction.type === 'assign-rank') {
        const selected = currentSession.board.selectedImageId
        if (!selected) return
        event.preventDefault()
        const instanceId = currentInstance.instance_id
        moveCurrentImageToRank(selected, boardAction.rankIndex, { autoAdvance: true })
        window.setTimeout(() => {
          const nextSelected = sessionsRef.current[instanceId]?.board.selectedImageId ?? null
          focusCard(nextSelected)
        }, 0)
        return
      }
      if (boardAction.type === 'select-neighbor') {
        event.preventDefault()
        const nextSelected = selectNeighborImage(currentSession.board, boardAction.direction)
        if (nextSelected) {
          selectCurrentImage(nextSelected)
          focusCard(nextSelected)
        }
        return
      }
      if (boardAction.type === 'instance-nav') {
        event.preventDefault()
        if (boardAction.direction === 'prev') {
          goPrev()
        } else {
          goNext()
        }
        return
      }
      if (boardAction.type === 'fullscreen-open') {
        const selected = currentSession.board.selectedImageId
        if (!selected) return
        event.preventDefault()
        openFullscreenForImage(selected)
      }
    }

    window.addEventListener('keydown', onKeyDown)
    return () => window.removeEventListener('keydown', onKeyDown)
  }, [
    closeFullscreen,
    currentInstance,
    currentSession,
    focusCard,
    fullscreenImageId,
    goNext,
    goPrev,
    moveCurrentImageToRank,
    navigateFullscreenImage,
    openFullscreenForImage,
    selectCurrentImage,
    sessionsRef,
  ])
}
