import {
  useCallback,
  useEffect,
  useMemo,
  useRef,
  useState,
  type DragEvent,
  type PointerEvent as ReactPointerEvent,
  type WheelEvent as ReactWheelEvent,
} from 'react'
import { BASE } from '../../api/base'
import { rankingApi } from './api'
import './ranking.css'
import {
  finalRanksFromBoard,
  isBoardComplete,
  moveImageToRank,
  moveImageToRankWithAutoAdvance,
  orderedImageIds,
  selectNeighborImage,
  type RankingBoardState,
} from './model/board'
import {
  RANKING_MIN_RANKS_HEIGHT_PX,
  RANKING_SPLITTER_HEIGHT_PX,
  clampUnrankedHeightPx,
} from './model/layout'
import {
  getBoardKeyAction,
  getFullscreenKeyAction,
  shouldIgnoreRankingHotkey,
} from './model/keyboard'
import { RANKING_DOT_COLORS, buildDotColorByImageId } from './model/palette'
import {
  buildInitialSessions,
  canNavigateNext,
  canNavigatePrev,
  clampInstanceIndex,
  computeDurationMs,
  isValidIsoTimestamp,
  type InstanceSession,
} from './model/session'
import type {
  RankingDatasetResponse,
  RankingInstance,
  RankingSaveRequest,
} from './types'

type ImageView = {
  url: string
  sourcePath: string
}

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
const INTERACTIVE_CONTROL_SELECTOR = 'button, a, [role="button"]'
const DEFAULT_DOT_COLOR = RANKING_DOT_COLORS[0]

function nowIso(): string {
  return new Date().toISOString()
}

function cardLabel(sourcePath: string): string {
  const name = sourcePath.split('/').filter(Boolean).pop()
  return name || sourcePath
}

function saveStateLabel(session: InstanceSession): string {
  if (session.saveStatus === 'saving') return 'Saving...'
  if (session.saveStatus === 'saved') return 'Saved'
  if (session.saveStatus === 'error') {
    return `Save failed: ${session.saveError ?? 'unknown error'}`
  }
  return 'Idle'
}

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

export default function RankingApp() {
  const [dataset, setDataset] = useState<RankingDatasetResponse | null>(null)
  const [sessions, setSessions] = useState<Record<string, InstanceSession>>({})
  const [currentIndex, setCurrentIndex] = useState(0)
  const [loading, setLoading] = useState(true)
  const [loadError, setLoadError] = useState<string | null>(null)
  const [draggingImageId, setDraggingImageId] = useState<string | null>(null)
  const [dragOverRank, setDragOverRank] = useState<number | null>(null)
  const [unrankedHeightPx, setUnrankedHeightPx] = useState<number | null>(null)
  const [splitterEnabled, setSplitterEnabled] = useState(false)
  const [isResizingSplit, setIsResizingSplit] = useState(false)
  const [fullscreenImageId, setFullscreenImageId] = useState<string | null>(null)
  const [fullscreenTransform, setFullscreenTransform] = useState<FullscreenTransform>(
    defaultFullscreenTransform,
  )

  const sessionsRef = useRef<Record<string, InstanceSession>>(sessions)
  const saveRequestRef = useRef<Record<string, number>>({})
  const cardRefs = useRef<Record<string, HTMLElement | null>>({})
  const workspaceRef = useRef<HTMLDivElement | null>(null)
  const splitterPointerIdRef = useRef<number | null>(null)
  const panStateRef = useRef<PanState>(defaultPanState())
  useEffect(() => {
    sessionsRef.current = sessions
  }, [sessions])

  useEffect(() => {
    if (typeof window === 'undefined' || typeof window.matchMedia !== 'function') {
      setSplitterEnabled(true)
      return
    }

    const coarseQuery = window.matchMedia('(pointer: coarse)')
    const narrowQuery = window.matchMedia('(max-width: 980px)')

    const apply = () => {
      setSplitterEnabled(!(coarseQuery.matches || narrowQuery.matches))
    }
    apply()

    const attachChangeListener = (query: MediaQueryList): (() => void) => {
      if (typeof query.addEventListener === 'function') {
        query.addEventListener('change', apply)
        return () => query.removeEventListener('change', apply)
      }
      query.addListener(apply)
      return () => query.removeListener(apply)
    }

    const cleanupCoarse = attachChangeListener(coarseQuery)
    const cleanupNarrow = attachChangeListener(narrowQuery)
    return () => {
      cleanupCoarse()
      cleanupNarrow()
    }
  }, [])

  useEffect(() => {
    if (splitterEnabled) return
    splitterPointerIdRef.current = null
    setIsResizingSplit(false)
    setUnrankedHeightPx(null)
  }, [splitterEnabled])

  const updateSession = useCallback(
    (instanceId: string, updater: (session: InstanceSession) => InstanceSession) => {
      setSessions((prev) => {
        const session = prev[instanceId]
        if (!session) return prev
        return {
          ...prev,
          [instanceId]: updater(session),
        }
      })
    },
    [],
  )

  useEffect(() => {
    let active = true
    setLoading(true)
    setLoadError(null)
    Promise.all([
      rankingApi.getDataset(),
      rankingApi.getProgress(),
      rankingApi.exportLatest(false),
    ])
      .then(([datasetPayload, progressPayload, exportPayload]) => {
        if (!active) return
        setDataset(datasetPayload)
        setSessions(buildInitialSessions(datasetPayload, exportPayload.results))
        setCurrentIndex(
          clampInstanceIndex(progressPayload.resume_instance_index, datasetPayload.instances.length),
        )
        setLoading(false)
      })
      .catch((error) => {
        if (!active) return
        setLoadError(error instanceof Error ? error.message : 'failed to load ranking session')
        setLoading(false)
      })
    return () => {
      active = false
    }
  }, [])

  const instances = dataset?.instances ?? []
  const currentInstance = instances[currentIndex] ?? null
  const currentSession = currentInstance ? sessions[currentInstance.instance_id] ?? null : null
  const canGoPrev = canNavigatePrev(currentIndex)
  const canGoNext = canNavigateNext(currentIndex, instances.length, currentSession)

  const imageById = useMemo(() => {
    const map = new Map<string, ImageView>()
    if (!currentInstance) return map
    for (const image of currentInstance.images) {
      map.set(image.image_id, { url: image.url, sourcePath: image.source_path })
    }
    return map
  }, [currentInstance])
  const currentImageOrder = useMemo(
    () => currentInstance?.images.map((image) => image.image_id) ?? [],
    [currentInstance],
  )
  const fullscreenImage = fullscreenImageId ? imageById.get(fullscreenImageId) ?? null : null
  const dotColorByImageId = useMemo(
    () => buildDotColorByImageId(currentImageOrder),
    [currentImageOrder],
  )

  useEffect(() => {
    if (typeof Image === 'undefined' || !dataset) return
    const nextInstance = dataset.instances[currentIndex + 1]
    if (!nextInstance) return
    for (const image of nextInstance.images) {
      const preload = new Image()
      preload.src = image.url
    }
  }, [dataset, currentIndex])

  useEffect(() => {
    setFullscreenImageId(null)
    setFullscreenTransform(defaultFullscreenTransform())
    panStateRef.current = defaultPanState()
  }, [currentInstance?.instance_id])

  const ensureStartedAt = useCallback(
    (instanceId: string): string => {
      const existing = sessionsRef.current[instanceId]?.startedAt
      if (isValidIsoTimestamp(existing)) {
        return existing
      }
      const startedAt = nowIso()
      updateSession(instanceId, (session) => {
        if (isValidIsoTimestamp(session.startedAt)) return session
        return {
          ...session,
          startedAt,
        }
      })
      return startedAt
    },
    [updateSession],
  )

  const persistSnapshot = useCallback(
    (instance: RankingInstance, board: RankingBoardState, startedAtInput: string | null = null) => {
      const instanceId = instance.instance_id
      const startedAt = isValidIsoTimestamp(startedAtInput)
        ? startedAtInput
        : ensureStartedAt(instanceId)
      const payload: RankingSaveRequest = {
        instance_id: instanceId,
        final_ranks: finalRanksFromBoard(board),
        started_at: startedAt,
        duration_ms: computeDurationMs(startedAt),
        completed: isBoardComplete(board),
      }

      const requestId = (saveRequestRef.current[instanceId] ?? 0) + 1
      saveRequestRef.current[instanceId] = requestId
      updateSession(instanceId, (session) => ({
        ...session,
        saveStatus: 'saving',
        saveError: null,
      }))

      void rankingApi.save(payload)
        .then(() => {
          if (saveRequestRef.current[instanceId] !== requestId) return
          updateSession(instanceId, (session) => ({
            ...session,
            saveStatus: 'saved',
            saveError: null,
          }))
        })
        .catch((error) => {
          if (saveRequestRef.current[instanceId] !== requestId) return
          const message = error instanceof Error ? error.message : 'failed to save ranking'
          updateSession(instanceId, (session) => ({
            ...session,
            saveStatus: 'error',
            saveError: message,
          }))
        })
    },
    [ensureStartedAt, updateSession],
  )

  const moveCurrentImageToRank = useCallback(
    (
      imageId: string,
      rankIndex: number | null,
      options?: { autoAdvance: boolean },
    ) => {
      if (!currentInstance) return
      const current = sessionsRef.current[currentInstance.instance_id]
      if (!current) return
      const boardSnapshot = options?.autoAdvance
        ? moveImageToRankWithAutoAdvance(
          current.board,
          imageId,
          rankIndex,
          currentImageOrder,
        )
        : moveImageToRank(current.board, imageId, rankIndex)
      if (boardSnapshot === current.board) return
      updateSession(currentInstance.instance_id, (session) => ({
        ...session,
        board: boardSnapshot,
      }))
      persistSnapshot(currentInstance, boardSnapshot, current.startedAt)
    },
    [currentImageOrder, currentInstance, persistSnapshot, updateSession],
  )

  const selectCurrentImage = useCallback(
    (imageId: string) => {
      if (!currentInstance) return
      updateSession(currentInstance.instance_id, (session) => ({
        ...session,
        board: {
          ...session.board,
          selectedImageId: imageId,
        },
      }))
    },
    [currentInstance, updateSession],
  )

  const registerCardRef = useCallback((imageId: string, element: HTMLElement | null) => {
    cardRefs.current[imageId] = element
  }, [])

  const resetFullscreenTransform = useCallback(() => {
    panStateRef.current = defaultPanState()
    setFullscreenTransform(defaultFullscreenTransform())
  }, [])

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
      if (openImageId && typeof window !== 'undefined') {
        window.requestAnimationFrame(() => {
          cardRefs.current[openImageId]?.focus()
        })
      }
      return null
    })
    resetFullscreenTransform()
  }, [resetFullscreenTransform])

  const clearDragState = useCallback(() => {
    setDragOverRank(null)
    setDraggingImageId(null)
  }, [])

  const onSplitterPointerDown = useCallback((event: ReactPointerEvent<HTMLDivElement>) => {
    if (!splitterEnabled) return
    if ((event.pointerType ?? 'mouse') !== 'mouse') return
    if (event.button !== 0) return
    if (draggingImageId) return

    const workspace = workspaceRef.current
    if (!workspace) return

    event.preventDefault()
    event.stopPropagation()
    clearDragState()

    const pointerId = event.pointerId
    splitterPointerIdRef.current = pointerId
    setIsResizingSplit(true)

    const handle = event.currentTarget
    try {
      handle.setPointerCapture(pointerId)
    } catch {
      // Ignore unsupported capture attempts.
    }

    const rect = workspace.getBoundingClientRect()
    const applyPointerTop = (clientY: number) => {
      setUnrankedHeightPx(clampUnrankedHeightPx(clientY - rect.top, rect.height))
    }
    applyPointerTop(event.clientY)

    const onPointerMove = (nextEvent: PointerEvent) => {
      if (splitterPointerIdRef.current !== nextEvent.pointerId) return
      applyPointerTop(nextEvent.clientY)
    }

    const onPointerUp = (nextEvent: PointerEvent) => {
      if (splitterPointerIdRef.current !== nextEvent.pointerId) return
      splitterPointerIdRef.current = null
      setIsResizingSplit(false)
      window.removeEventListener('pointermove', onPointerMove)
      window.removeEventListener('pointerup', onPointerUp)
      window.removeEventListener('pointercancel', onPointerUp)
      try {
        handle.releasePointerCapture(pointerId)
      } catch {
        // Ignore unsupported release attempts.
      }
    }

    window.addEventListener('pointermove', onPointerMove)
    window.addEventListener('pointerup', onPointerUp)
    window.addEventListener('pointercancel', onPointerUp)
  }, [clearDragState, draggingImageId, splitterEnabled])

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

  const navigateTo = useCallback(
    (nextIndex: number) => {
      if (!currentInstance || !dataset) return
      const clamped = clampInstanceIndex(nextIndex, dataset.instances.length)
      if (clamped === currentIndex) return
      const current = sessionsRef.current[currentInstance.instance_id]
      if (current) {
        persistSnapshot(currentInstance, current.board, current.startedAt)
      }
      setCurrentIndex(clamped)
    },
    [currentIndex, currentInstance, dataset, persistSnapshot],
  )

  const goPrev = useCallback(() => {
    if (!canGoPrev) return
    navigateTo(currentIndex - 1)
  }, [canGoPrev, currentIndex, navigateTo])

  const goNext = useCallback(() => {
    if (!canGoNext) return
    navigateTo(currentIndex + 1)
  }, [canGoNext, currentIndex, navigateTo])

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
        moveCurrentImageToRank(selected, boardAction.rankIndex, { autoAdvance: true })
        return
      }
      if (boardAction.type === 'select-neighbor') {
        event.preventDefault()
        const nextSelected = selectNeighborImage(currentSession.board, boardAction.direction)
        if (nextSelected) {
          selectCurrentImage(nextSelected)
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
    fullscreenImageId,
    goNext,
    goPrev,
    moveCurrentImageToRank,
    navigateFullscreenImage,
    openFullscreenForImage,
    selectCurrentImage,
  ])

  const startDrag = useCallback((event: DragEvent<HTMLElement>, imageId: string) => {
    if (isResizingSplit) {
      event.preventDefault()
      return
    }
    event.dataTransfer.setData('text/plain', imageId)
    event.dataTransfer.effectAllowed = 'move'
    setDraggingImageId(imageId)
  }, [isResizingSplit])

  const dropOnRank = useCallback(
    (event: DragEvent<HTMLElement>, rankIndex: number | null) => {
      if (isResizingSplit) {
        event.preventDefault()
        clearDragState()
        return
      }
      event.preventDefault()
      const imageId = event.dataTransfer.getData('text/plain') || draggingImageId
      clearDragState()
      if (!imageId) return
      moveCurrentImageToRank(imageId, rankIndex)
    },
    [clearDragState, draggingImageId, isResizingSplit, moveCurrentImageToRank],
  )

  if (loading) {
    return <div className="ranking-loading">Loading ranking session...</div>
  }

  if (loadError || !currentInstance || !currentSession || !dataset) {
    return (
      <div className="ranking-error">
        <p>Failed to load ranking mode.</p>
        <pre>{loadError ?? 'missing ranking dataset payload'}</pre>
      </div>
    )
  }

  const ordered = orderedImageIds(currentSession.board)
  const exportHref = `${BASE}/rank/export?completed_only=true`
  const fullscreenPosition = fullscreenImageId
    ? currentImageOrder.indexOf(fullscreenImageId) + 1
    : 0
  const workspaceStyle = splitterEnabled && unrankedHeightPx != null
    ? {
      gridTemplateRows: `${unrankedHeightPx}px ${RANKING_SPLITTER_HEIGHT_PX}px minmax(${RANKING_MIN_RANKS_HEIGHT_PX}px, 1fr)`,
    }
    : undefined
  const workspaceClassName = [
    'ranking-workspace',
    splitterEnabled ? 'is-splitter-enabled' : 'is-splitter-disabled',
    isResizingSplit && 'is-resizing',
  ]
    .filter(Boolean)
    .join(' ')
  const splitterClassName = ['ranking-splitter', !splitterEnabled && 'is-disabled']
    .filter(Boolean)
    .join(' ')

  const renderCard = (imageId: string) => {
    const image = imageById.get(imageId)
    if (!image) return null
    const isSelected = currentSession.board.selectedImageId === imageId
    const label = cardLabel(image.sourcePath)
    const dotColor = dotColorByImageId[imageId] ?? DEFAULT_DOT_COLOR
    return (
      <article
        key={imageId}
        className={`ranking-card ${isSelected ? 'is-selected' : ''}`}
        draggable={!isResizingSplit}
        tabIndex={0}
        ref={(element) => registerCardRef(imageId, element)}
        onDragStart={(event) => startDrag(event, imageId)}
        onDragEnd={clearDragState}
        onClick={() => selectCurrentImage(imageId)}
      >
        <button
          type="button"
          className="ranking-card-fullscreen"
          onClick={(event) => {
            event.preventDefault()
            event.stopPropagation()
            openFullscreenForImage(imageId)
          }}
          aria-label={`Open ${label} fullscreen`}
        >
          Fullscreen
        </button>
        <img src={image.url} alt={image.sourcePath} loading="lazy" draggable={false} />
        <div className="ranking-card-meta">
          <span
            className="ranking-card-dot"
            style={{ backgroundColor: dotColor }}
            aria-hidden="true"
          />
          <div className="ranking-card-label">{label}</div>
        </div>
      </article>
    )
  }

  const renderColumn = ({
    title,
    imageIds,
    dragValue,
    targetRank,
    columnKey,
    className,
    cardsClassName,
  }: {
    title: string
    imageIds: string[]
    dragValue: number
    targetRank: number | null
    columnKey: string
    className: string
    cardsClassName: string
  }) => {
    const columnClassName = ['ranking-column', className, dragOverRank === dragValue && 'is-drag-over']
      .filter(Boolean)
      .join(' ')
    return (
      <section
        key={columnKey}
        className={columnClassName}
        onDragOver={(event) => {
          if (isResizingSplit) return
          event.preventDefault()
          setDragOverRank(dragValue)
        }}
        onDragLeave={() => {
          if (isResizingSplit) return
          setDragOverRank(null)
        }}
        onDrop={(event) => dropOnRank(event, targetRank)}
      >
        <header className="ranking-column-header">{title}</header>
        <div className={`ranking-column-cards ${cardsClassName}`}>{imageIds.map(renderCard)}</div>
      </section>
    )
  }

  return (
    <div className="ranking-root">
      <header className="ranking-header">
        <div className="ranking-nav-group">
          <button
            type="button"
            className="ranking-button"
            onClick={goPrev}
            disabled={!canGoPrev}
          >
            Prev
          </button>
          <button
            type="button"
            className="ranking-button ranking-button-primary"
            onClick={goNext}
            disabled={!canGoNext}
          >
            Next
          </button>
        </div>
        <div className="ranking-meta">
          <strong>
            {currentIndex + 1} / {dataset.instances.length}
          </strong>
          <span className="ranking-instance-id">instance: {currentInstance.instance_id}</span>
          <span className="ranking-save-status">{saveStateLabel(currentSession)}</span>
        </div>
        <a className="ranking-button" href={exportHref} target="_blank" rel="noreferrer">
          Export
        </a>
      </header>

      <div className="ranking-guard" role="status">
        {isBoardComplete(currentSession.board)
          ? 'All images ranked. Next is enabled.'
          : 'Assign every image to a rank before continuing.'}
      </div>

      <div className={workspaceClassName} ref={workspaceRef} style={workspaceStyle}>
        {renderColumn({
          title: 'Unranked',
          imageIds: currentSession.board.unranked,
          dragValue: -1,
          targetRank: null,
          columnKey: 'unranked',
          className: 'ranking-column-unranked',
          cardsClassName: 'ranking-column-cards-unranked',
        })}
        <div
          className={splitterClassName}
          onPointerDown={onSplitterPointerDown}
          role={splitterEnabled ? 'separator' : undefined}
          aria-hidden={!splitterEnabled}
          aria-orientation={splitterEnabled ? 'horizontal' : undefined}
        >
          <span className="ranking-splitter-grip" />
        </div>
        <section className="ranking-ranks-panel">
          <header className="ranking-ranks-header">Ranks</header>
          <div className="ranking-ranks-board">
            {currentSession.board.rankColumns.map((column, rankIdx) => (
              renderColumn({
                title: `${rankIdx + 1}`,
                imageIds: column,
                dragValue: rankIdx,
                targetRank: rankIdx,
                columnKey: `rank-${rankIdx}`,
                className: 'ranking-column-rank',
                cardsClassName: 'ranking-column-cards-rank',
              })
            ))}
          </div>
        </section>
      </div>

      <footer className="ranking-footer">
        <span>{ordered.length} images</span>
        <span>Hotkeys: 1-9 rank, arrows move, q/e instance, Enter fullscreen, Esc close</span>
      </footer>

      {fullscreenImageId && fullscreenImage ? (
        <div className="ranking-fullscreen" role="dialog" aria-modal="true">
          <header className="ranking-fullscreen-header">
            <div className="ranking-fullscreen-meta">
              <strong>
                {fullscreenPosition} / {currentImageOrder.length}
              </strong>
              <span>{cardLabel(fullscreenImage.sourcePath)}</span>
            </div>
            <div className="ranking-fullscreen-hint">
              Hotkeys: 1-9 rank, a/d image, Esc close
            </div>
            <button
              type="button"
              className="ranking-button"
              onClick={closeFullscreen}
            >
              Close
            </button>
          </header>
          <div
            className={`ranking-fullscreen-stage ${fullscreenTransform.zoom > MIN_FULLSCREEN_ZOOM ? 'is-zoomed' : ''}`}
            onWheel={handleFullscreenWheel}
            onPointerDown={handleFullscreenPointerDown}
            onPointerMove={handleFullscreenPointerMove}
            onPointerUp={handleFullscreenPointerEnd}
            onPointerCancel={handleFullscreenPointerEnd}
            onDoubleClick={resetFullscreenTransform}
          >
            <img
              src={fullscreenImage.url}
              alt={fullscreenImage.sourcePath}
              className="ranking-fullscreen-image"
              draggable={false}
              style={{
                transform: `translate3d(${fullscreenTransform.offsetX}px, ${fullscreenTransform.offsetY}px, 0) scale(${fullscreenTransform.zoom})`,
              }}
            />
          </div>
        </div>
      ) : null}
    </div>
  )
}
