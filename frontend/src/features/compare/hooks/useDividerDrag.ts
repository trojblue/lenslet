import {
  useCallback,
  useEffect,
  useRef,
  type Dispatch,
  type PointerEvent as ReactPointerEvent,
  type SetStateAction,
} from 'react'

const MIN_COMPARE_SPLIT_PCT = 5
const MAX_COMPARE_SPLIT_PCT = 95

type StageRect = Pick<DOMRectReadOnly, 'left' | 'width'>

type DividerDragSessionOptions = {
  pointerId: number
  target: HTMLElement
  listenerTarget: Pick<Window, 'addEventListener' | 'removeEventListener'>
  getStageRect: () => StageRect | null
  setSplitPct: (value: number) => void
}

type DividerDragSession = {
  cleanup: () => void
  isActive: () => boolean
}

type UseDividerDragOptions = {
  getStage: () => HTMLElement | null
  setSplitPct: Dispatch<SetStateAction<number>>
  onUserInteraction?: () => void
}

export function clampCompareSplitPct(value: number): number {
  return Math.min(MAX_COMPARE_SPLIT_PCT, Math.max(MIN_COMPARE_SPLIT_PCT, value))
}

export function splitPctFromClientX(clientX: number, rect: StageRect): number | null {
  if (!Number.isFinite(rect.width) || rect.width <= 0) return null
  return clampCompareSplitPct(((clientX - rect.left) / rect.width) * 100)
}

function trySetPointerCapture(target: HTMLElement, pointerId: number): void {
  try {
    target.setPointerCapture(pointerId)
  } catch {
    // Pointer capture is best-effort across browsers and synthetic test events.
  }
}

function tryReleasePointerCapture(target: HTMLElement, pointerId: number): void {
  try {
    target.releasePointerCapture(pointerId)
  } catch {
    // Capture can already be gone after lostpointercapture or unmount.
  }
}

export function createDividerDragSession({
  pointerId,
  target,
  listenerTarget,
  getStageRect,
  setSplitPct,
}: DividerDragSessionOptions): DividerDragSession {
  let active = true

  const updateFromClientX = (clientX: number) => {
    const rect = getStageRect()
    if (!rect) return
    const nextPct = splitPctFromClientX(clientX, rect)
    if (nextPct === null) return
    setSplitPct(nextPct)
  }

  const cleanup = () => {
    if (!active) return
    active = false
    tryReleasePointerCapture(target, pointerId)
    listenerTarget.removeEventListener('pointermove', onMove as EventListener)
    listenerTarget.removeEventListener('pointerup', onEnd as EventListener)
    listenerTarget.removeEventListener('pointercancel', onEnd as EventListener)
    target.removeEventListener('lostpointercapture', onEnd as EventListener)
  }

  const onMove = (event: PointerEvent) => {
    if (event.pointerId !== pointerId) return
    event.preventDefault()
    updateFromClientX(event.clientX)
  }

  const onEnd = (event: PointerEvent) => {
    if (event.pointerId !== pointerId) return
    cleanup()
  }

  trySetPointerCapture(target, pointerId)
  listenerTarget.addEventListener('pointermove', onMove as EventListener)
  listenerTarget.addEventListener('pointerup', onEnd as EventListener)
  listenerTarget.addEventListener('pointercancel', onEnd as EventListener)
  target.addEventListener('lostpointercapture', onEnd as EventListener)

  return {
    cleanup,
    isActive: () => active,
  }
}

export function useDividerDrag({
  getStage,
  setSplitPct,
  onUserInteraction,
}: UseDividerDragOptions) {
  const sessionRef = useRef<DividerDragSession | null>(null)

  useEffect(() => {
    return () => {
      sessionRef.current?.cleanup()
      sessionRef.current = null
    }
  }, [])

  return useCallback((event: ReactPointerEvent<HTMLDivElement>) => {
    const stage = getStage()
    if (!stage) return
    event.preventDefault()
    event.stopPropagation()
    onUserInteraction?.()
    sessionRef.current?.cleanup()
    sessionRef.current = createDividerDragSession({
      pointerId: event.pointerId,
      target: event.currentTarget,
      listenerTarget: window,
      getStageRect: () => getStage()?.getBoundingClientRect() ?? null,
      setSplitPct,
    })
  }, [getStage, onUserInteraction, setSplitPct])
}
