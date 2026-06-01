import {
  useCallback,
  useEffect,
  useRef,
  useState,
  type PointerEvent as ReactPointerEvent,
  type WheelEvent as ReactWheelEvent,
} from 'react'

type FullscreenTransform = {
  zoom: number
  offsetX: number
  offsetY: number
}

type PanState = {
  active: boolean
  pointerId: number | null
  startX: number
  startY: number
  originX: number
  originY: number
}

const MIN_FULLSCREEN_ZOOM = 1
const MAX_FULLSCREEN_ZOOM = 4
const FULLSCREEN_ZOOM_STEP = 0.18

function defaultFullscreenTransform(): FullscreenTransform {
  return {
    zoom: MIN_FULLSCREEN_ZOOM,
    offsetX: 0,
    offsetY: 0,
  }
}

function defaultPanState(): PanState {
  return {
    active: false,
    pointerId: null,
    startX: 0,
    startY: 0,
    originX: 0,
    originY: 0,
  }
}

function clampZoom(zoom: number): number {
  if (zoom < MIN_FULLSCREEN_ZOOM) return MIN_FULLSCREEN_ZOOM
  if (zoom > MAX_FULLSCREEN_ZOOM) return MAX_FULLSCREEN_ZOOM
  return zoom
}

type UseRankingFullscreenParams = {
  currentImageOrder: string[]
  currentInstanceId: string | null
  focusCard: (imageId: string | null) => void
  selectCurrentImage: (imageId: string) => void
}

export function useRankingFullscreen({
  currentImageOrder,
  currentInstanceId,
  focusCard,
  selectCurrentImage,
}: UseRankingFullscreenParams) {
  const [fullscreenImageId, setFullscreenImageId] = useState<string | null>(null)
  const [fullscreenTransform, setFullscreenTransform] = useState<FullscreenTransform>(
    defaultFullscreenTransform,
  )
  const panStateRef = useRef<PanState>(defaultPanState())

  const resetFullscreenTransform = useCallback(() => {
    panStateRef.current = defaultPanState()
    setFullscreenTransform(defaultFullscreenTransform())
  }, [])

  useEffect(() => {
    setFullscreenImageId(null)
    resetFullscreenTransform()
  }, [currentInstanceId, resetFullscreenTransform])

  const openFullscreenForImage = useCallback(
    (imageId: string) => {
      selectCurrentImage(imageId)
      setFullscreenImageId(imageId)
      resetFullscreenTransform()
    },
    [resetFullscreenTransform, selectCurrentImage],
  )

  const closeFullscreen = useCallback(() => {
    setFullscreenImageId((openImageId) => {
      focusCard(openImageId)
      return null
    })
    resetFullscreenTransform()
  }, [focusCard, resetFullscreenTransform])

  const navigateFullscreenImage = useCallback(
    (direction: 'prev' | 'next') => {
      if (!fullscreenImageId || currentImageOrder.length === 0) return
      const currentPos = currentImageOrder.indexOf(fullscreenImageId)
      if (currentPos < 0) return
      const targetPos = direction === 'prev' ? currentPos - 1 : currentPos + 1
      const targetImageId = currentImageOrder[targetPos]
      if (!targetImageId) return
      setFullscreenImageId(targetImageId)
      selectCurrentImage(targetImageId)
      resetFullscreenTransform()
    },
    [currentImageOrder, fullscreenImageId, resetFullscreenTransform, selectCurrentImage],
  )

  const handleFullscreenWheel = useCallback((event: ReactWheelEvent<HTMLDivElement>) => {
    event.preventDefault()
    const delta = event.deltaY < 0 ? FULLSCREEN_ZOOM_STEP : -FULLSCREEN_ZOOM_STEP
    setFullscreenTransform((prev) => {
      const zoom = clampZoom(prev.zoom + delta)
      if (zoom === MIN_FULLSCREEN_ZOOM) {
        return defaultFullscreenTransform()
      }
      return {
        ...prev,
        zoom,
      }
    })
  }, [])

  const handleFullscreenPointerDown = useCallback(
    (event: ReactPointerEvent<HTMLDivElement>) => {
      if (event.button !== 0 || fullscreenTransform.zoom <= MIN_FULLSCREEN_ZOOM) return
      event.preventDefault()
      event.currentTarget.setPointerCapture(event.pointerId)
      panStateRef.current = {
        active: true,
        pointerId: event.pointerId,
        startX: event.clientX,
        startY: event.clientY,
        originX: fullscreenTransform.offsetX,
        originY: fullscreenTransform.offsetY,
      }
    },
    [fullscreenTransform.offsetX, fullscreenTransform.offsetY, fullscreenTransform.zoom],
  )

  const handleFullscreenPointerMove = useCallback((event: ReactPointerEvent<HTMLDivElement>) => {
    const panState = panStateRef.current
    if (!panState.active || panState.pointerId !== event.pointerId) return
    const nextOffsetX = panState.originX + (event.clientX - panState.startX)
    const nextOffsetY = panState.originY + (event.clientY - panState.startY)
    setFullscreenTransform((prev) => ({
      ...prev,
      offsetX: nextOffsetX,
      offsetY: nextOffsetY,
    }))
  }, [])

  const handleFullscreenPointerEnd = useCallback((event: ReactPointerEvent<HTMLDivElement>) => {
    if (event.currentTarget.hasPointerCapture(event.pointerId)) {
      event.currentTarget.releasePointerCapture(event.pointerId)
    }
    panStateRef.current.active = false
    panStateRef.current.pointerId = null
  }, [])

  return {
    closeFullscreen,
    fullscreenImageId,
    fullscreenTransform,
    handleFullscreenPointerDown,
    handleFullscreenPointerEnd,
    handleFullscreenPointerMove,
    handleFullscreenWheel,
    isFullscreenZoomed: fullscreenTransform.zoom > MIN_FULLSCREEN_ZOOM,
    navigateFullscreenImage,
    openFullscreenForImage,
    resetFullscreenTransform,
  }
}
