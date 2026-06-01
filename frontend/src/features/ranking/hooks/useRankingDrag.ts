import { useCallback, useMemo, useRef, useState, type MutableRefObject } from 'react'
import {
  PointerSensor,
  useSensor,
  useSensors,
  type DragEndEvent,
  type DragOverEvent,
  type DragStartEvent,
  type Modifier,
} from '@dnd-kit/core'
import type { RankingBoardState } from '../model/board'
import {
  findContainerForImage,
  itemsForContainer,
  parseContainerId,
  rankIndexForContainerId,
  type RankingContainerId,
} from '../model/containers'
import type { InstanceSession } from '../model/session'
import type { RankingInstance } from '../types'
import type { MoveRankOptions } from './useRankingSession'

function pointerClientPosition(event: Event | null): { x: number; y: number } | null {
  if (!event) return null
  if (typeof MouseEvent !== 'undefined' && event instanceof MouseEvent) {
    return {
      x: event.clientX,
      y: event.clientY,
    }
  }
  if (typeof TouchEvent !== 'undefined' && event instanceof TouchEvent) {
    const touch = event.touches[0] ?? event.changedTouches[0]
    if (!touch) return null
    return {
      x: touch.clientX,
      y: touch.clientY,
    }
  }
  return null
}

type UseRankingDragParams = {
  currentInstance: RankingInstance | null
  currentSession: InstanceSession | null
  moveCurrentImageToRank: (
    imageId: string,
    rankIndex: number | null,
    options?: MoveRankOptions,
  ) => void
  selectCurrentImage: (imageId: string) => void
  sessionsRef: MutableRefObject<Record<string, InstanceSession>>
}

export function useRankingDrag({
  currentInstance,
  currentSession,
  moveCurrentImageToRank,
  selectCurrentImage,
  sessionsRef,
}: UseRankingDragParams) {
  const [activeDragImageId, setActiveDragImageId] = useState<string | null>(null)
  const [dragOverContainerId, setDragOverContainerId] = useState<RankingContainerId | null>(null)
  const dragPointerOffsetRef = useRef<{ x: number; y: number } | null>(null)

  const clearDragState = useCallback(() => {
    setDragOverContainerId(null)
    setActiveDragImageId(null)
    dragPointerOffsetRef.current = null
  }, [])

  const sensors = useSensors(
    useSensor(PointerSensor, {
      activationConstraint: { distance: 4 },
    }),
  )

  const dragOverlayModifiers = useMemo<Modifier[]>(
    () => [
      ({ transform }) => {
        const pointerOffset = dragPointerOffsetRef.current
        if (!pointerOffset) return transform
        return {
          ...transform,
          x: transform.x - pointerOffset.x,
          y: transform.y - pointerOffset.y,
        }
      },
    ],
    [],
  )

  const resolveContainerId = useCallback(
    (board: RankingBoardState, rawId: string | null): RankingContainerId | null => {
      if (!rawId) return null
      const parsedContainer = parseContainerId(rawId, board.rankColumns.length)
      if (parsedContainer) return parsedContainer
      return findContainerForImage(board, rawId)
    },
    [],
  )

  const handleDragStart = useCallback(
    (event: DragStartEvent) => {
      if (!currentSession) return
      const activeId = String(event.active.id)
      if (!findContainerForImage(currentSession.board, activeId)) return
      const pointerPosition = pointerClientPosition(event.activatorEvent)
      const initialRect = event.active.rect.current.initial
      if (pointerPosition && initialRect) {
        dragPointerOffsetRef.current = {
          x: Math.max(0, pointerPosition.x - initialRect.left),
          y: Math.max(0, pointerPosition.y - initialRect.top),
        }
      } else {
        dragPointerOffsetRef.current = null
      }
      setActiveDragImageId(activeId)
      selectCurrentImage(activeId)
    },
    [currentSession, selectCurrentImage],
  )

  const handleDragOver = useCallback(
    (event: DragOverEvent) => {
      if (!currentInstance) return
      const current = sessionsRef.current[currentInstance.instance_id]
      if (!current) return
      const overId = event.over ? String(event.over.id) : null
      setDragOverContainerId(resolveContainerId(current.board, overId))
    },
    [currentInstance, resolveContainerId, sessionsRef],
  )

  const handleDragEnd = useCallback(
    (event: DragEndEvent) => {
      if (!currentInstance) {
        clearDragState()
        return
      }
      const current = sessionsRef.current[currentInstance.instance_id]
      clearDragState()
      if (!current || !event.over) return

      const activeId = String(event.active.id)
      const overId = String(event.over.id)
      const board = current.board
      const activeContainerId = resolveContainerId(board, activeId)
      const overContainerId = resolveContainerId(board, overId)
      if (!activeContainerId || !overContainerId) return

      const activeItems = itemsForContainer(board, activeContainerId)
      const activeIndex = activeItems.indexOf(activeId)
      if (activeIndex < 0) return

      const overItems = itemsForContainer(board, overContainerId)
      if (
        activeContainerId === overContainerId &&
        overId === overContainerId &&
        activeIndex === activeItems.length - 1
      ) {
        return
      }
      let targetInsertIndex: number
      if (overId === overContainerId) {
        targetInsertIndex = overItems.length
      } else {
        const overIndex = overItems.indexOf(overId)
        if (overIndex < 0) return
        if (activeContainerId === overContainerId) {
          if (activeIndex === overIndex) return
          targetInsertIndex = overIndex
        } else {
          const activeTop = event.active.rect.current.translated?.top
          const isBelowOverItem = activeTop != null &&
            activeTop > event.over.rect.top + event.over.rect.height
          targetInsertIndex = overIndex + (isBelowOverItem ? 1 : 0)
        }
      }

      moveCurrentImageToRank(activeId, rankIndexForContainerId(overContainerId), {
        targetInsertIndex,
      })
    },
    [clearDragState, currentInstance, moveCurrentImageToRank, resolveContainerId, sessionsRef],
  )

  return {
    activeDragImageId,
    clearDragState,
    dragOverlayModifiers,
    dragOverContainerId,
    handleDragEnd,
    handleDragOver,
    handleDragStart,
    sensors,
  }
}
