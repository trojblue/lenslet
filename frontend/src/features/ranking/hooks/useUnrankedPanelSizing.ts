import {
  useCallback,
  useEffect,
  useRef,
  useState,
  type PointerEvent as ReactPointerEvent,
  type RefObject,
} from 'react'
import {
  RANKING_DEFAULT_UNRANKED_HEIGHT_PX,
  RANKING_MIN_RANKS_HEIGHT_PX,
  RANKING_MIN_UNRANKED_HEIGHT_PX,
  clampUnrankedHeightPx,
} from '../model/layout'

const UNRANKED_HEIGHT_STORAGE_KEY = 'lenslet.ranking.unranked_height_px.v1'
const UNRANKED_THUMB_SIZE_STORAGE_KEY = 'lenslet.ranking.unranked_thumb_size_px.v1'

export const UNRANKED_THUMB_SIZE_MIN_PX = 132
export const UNRANKED_THUMB_SIZE_MAX_PX = 1560
export const UNRANKED_THUMB_SIZE_STEP_PX = 4
export const UNRANKED_THUMB_SIZE_DEFAULT_PX = 208

function readStoredUnrankedHeightPx(): number | null {
  if (typeof window === 'undefined') return null
  let raw: string | null = null
  try {
    raw = window.localStorage.getItem(UNRANKED_HEIGHT_STORAGE_KEY)
  } catch {
    return null
  }
  if (!raw) return null
  const parsed = Number(raw)
  if (!Number.isFinite(parsed) || parsed <= 0) return null
  return Math.trunc(parsed)
}

export function clampUnrankedThumbSizePx(value: number): number {
  if (!Number.isFinite(value)) return UNRANKED_THUMB_SIZE_DEFAULT_PX
  const snapped = Math.round(value / UNRANKED_THUMB_SIZE_STEP_PX) * UNRANKED_THUMB_SIZE_STEP_PX
  return Math.max(UNRANKED_THUMB_SIZE_MIN_PX, Math.min(UNRANKED_THUMB_SIZE_MAX_PX, snapped))
}

function readStoredUnrankedThumbSizePx(): number | null {
  if (typeof window === 'undefined') return null
  let raw: string | null = null
  try {
    raw = window.localStorage.getItem(UNRANKED_THUMB_SIZE_STORAGE_KEY)
  } catch {
    return null
  }
  if (!raw) return null
  return clampUnrankedThumbSizePx(Number(raw))
}

type UseUnrankedPanelSizingParams = {
  activeDragImageId: string | null
  clearDragState: () => void
  currentIndex: number
  workspaceRef: RefObject<HTMLDivElement | null>
}

export function useUnrankedPanelSizing({
  activeDragImageId,
  clearDragState,
  currentIndex,
  workspaceRef,
}: UseUnrankedPanelSizingParams) {
  const [unrankedHeightPx, setUnrankedHeightPx] = useState<number>(() => {
    const stored = readStoredUnrankedHeightPx()
    if (stored != null) return stored
    if (typeof window !== 'undefined' && Number.isFinite(window.innerHeight)) {
      return Math.round(window.innerHeight * 0.5)
    }
    return RANKING_DEFAULT_UNRANKED_HEIGHT_PX
  })
  const [unrankedThumbSizePx, setUnrankedThumbSizePx] = useState<number>(() => {
    return readStoredUnrankedThumbSizePx() ?? UNRANKED_THUMB_SIZE_DEFAULT_PX
  })
  const [isResizingSplit, setIsResizingSplit] = useState(false)
  const splitResizeRef = useRef<{ startY: number; startHeight: number } | null>(null)

  const clampWorkspaceHeight = useCallback(() => {
    const workspace = workspaceRef.current
    if (!workspace) return
    const { height } = workspace.getBoundingClientRect()
    setUnrankedHeightPx((prev) => {
      const requested = prev ?? Math.round(height * 0.5)
      return clampUnrankedHeightPx(requested, height, {
        minTopPx: RANKING_MIN_UNRANKED_HEIGHT_PX,
        minBottomPx: RANKING_MIN_RANKS_HEIGHT_PX,
        splitterPx: 0,
      })
    })
  }, [workspaceRef])

  useEffect(() => {
    if (typeof window === 'undefined') return
    clampWorkspaceHeight()
    window.addEventListener('resize', clampWorkspaceHeight)
    return () => window.removeEventListener('resize', clampWorkspaceHeight)
  }, [clampWorkspaceHeight])

  useEffect(() => {
    clampWorkspaceHeight()
  }, [clampWorkspaceHeight, currentIndex])

  useEffect(() => {
    if (typeof window === 'undefined') return
    if (!Number.isFinite(unrankedHeightPx) || unrankedHeightPx <= 0) return
    try {
      window.localStorage.setItem(
        UNRANKED_HEIGHT_STORAGE_KEY,
        String(Math.trunc(unrankedHeightPx)),
      )
    } catch {
      // Ignore storage errors (e.g. privacy mode).
    }
  }, [unrankedHeightPx])

  useEffect(() => {
    if (typeof window === 'undefined') return
    try {
      window.localStorage.setItem(
        UNRANKED_THUMB_SIZE_STORAGE_KEY,
        String(clampUnrankedThumbSizePx(unrankedThumbSizePx)),
      )
    } catch {
      // Ignore storage errors (e.g. privacy mode).
    }
  }, [unrankedThumbSizePx])

  const onUnrankedResizeStart = useCallback((event: ReactPointerEvent<HTMLButtonElement>) => {
    if ((event.pointerType ?? 'mouse') !== 'mouse') return
    if (event.button !== 0) return
    if (activeDragImageId) return

    const workspace = workspaceRef.current
    if (!workspace) return

    event.preventDefault()
    event.stopPropagation()
    clearDragState()
    splitResizeRef.current = {
      startY: event.clientY,
      startHeight: unrankedHeightPx,
    }
    setIsResizingSplit(true)
  }, [activeDragImageId, clearDragState, unrankedHeightPx, workspaceRef])

  useEffect(() => {
    const handlePointerMove = (event: PointerEvent) => {
      if (!splitResizeRef.current) return
      const workspace = workspaceRef.current
      if (!workspace) return
      const delta = event.clientY - splitResizeRef.current.startY
      const requestedHeight = splitResizeRef.current.startHeight + delta
      const { height } = workspace.getBoundingClientRect()
      setUnrankedHeightPx(
        clampUnrankedHeightPx(requestedHeight, height, {
          minTopPx: RANKING_MIN_UNRANKED_HEIGHT_PX,
          minBottomPx: RANKING_MIN_RANKS_HEIGHT_PX,
          splitterPx: 0,
        }),
      )
    }

    const stopResize = () => {
      if (!splitResizeRef.current) return
      splitResizeRef.current = null
      setIsResizingSplit(false)
    }

    window.addEventListener('pointermove', handlePointerMove)
    window.addEventListener('pointerup', stopResize)
    window.addEventListener('pointercancel', stopResize)
    return () => {
      window.removeEventListener('pointermove', handlePointerMove)
      window.removeEventListener('pointerup', stopResize)
      window.removeEventListener('pointercancel', stopResize)
    }
  }, [workspaceRef])

  return {
    isResizingSplit,
    onUnrankedResizeStart,
    setUnrankedThumbSizePx,
    unrankedHeightPx,
    unrankedThumbSizePx,
  }
}
