import {
  useCallback,
  useEffect,
  useMemo,
  useRef,
  useState,
  type CSSProperties,
  type ReactNode,
  type PointerEvent as ReactPointerEvent,
  type WheelEvent as ReactWheelEvent,
} from 'react'
import {
  DndContext,
  DragOverlay,
  PointerSensor,
  closestCenter,
  pointerWithin,
  useDroppable,
  useSensor,
  useSensors,
  type DragEndEvent,
  type DragOverEvent,
  type DragStartEvent,
  type Modifier,
} from '@dnd-kit/core'
import {
  SortableContext,
  rectSortingStrategy,
  useSortable,
  verticalListSortingStrategy,
} from '@dnd-kit/sortable'
import { CSS } from '@dnd-kit/utilities'
import { ChevronLeft, ChevronRight, Download } from 'lucide-react'
import { BASE } from '../../api/base'
import { rankingApi } from './api'
import './ranking.css'
import {
  finalRanksFromBoard,
  isBoardComplete,
  moveImageToRank,
  moveImageToRankWithAutoAdvance,
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

function FullscreenIcon() {
  return (
    <svg
      width="13"
      height="13"
      viewBox="0 0 24 24"
      fill="none"
      stroke="currentColor"
      strokeWidth="2"
      strokeLinecap="round"
      strokeLinejoin="round"
      aria-hidden="true"
    >
      <path d="M8 3H3v5" />
      <path d="M16 3h5v5" />
      <path d="M3 16v5h5" />
      <path d="M21 16v5h-5" />
    </svg>
  )
}

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

type RankingContainerId = 'unranked' | `rank-${number}`

type RankingCardContentProps = {
  image: ImageView
  label: string
  dotColor: string
  onOpenFullscreen?: () => void
}

type SortableRankingCardProps = RankingCardContentProps & {
  imageId: string
  containerId: RankingContainerId
  isSelected: boolean
  draggingDisabled: boolean
  onSelect: () => void
  registerCardRef: (imageId: string, element: HTMLElement | null) => void
}

type RankingDropColumnProps = {
  containerId: RankingContainerId
  title: string
  imageIds: string[]
  className: string
  cardsClassName: string
  cardsStyle?: CSSProperties
  isDragOver: boolean
  renderCard: (imageId: string, containerId: RankingContainerId) => ReactNode
}

const UNRANKED_CONTAINER_ID: RankingContainerId = 'unranked'

function rankContainerId(rankIndex: number): RankingContainerId {
  return `rank-${rankIndex}`
}

function parseContainerId(rawId: string, rankCount: number): RankingContainerId | null {
  if (rawId === UNRANKED_CONTAINER_ID) return UNRANKED_CONTAINER_ID
  if (!rawId.startsWith('rank-')) return null
  const rankIndex = Number(rawId.slice('rank-'.length))
  if (!Number.isInteger(rankIndex) || rankIndex < 0 || rankIndex >= rankCount) return null
  return rankContainerId(rankIndex)
}

function rankIndexForContainerId(containerId: RankingContainerId): number | null {
  if (containerId === UNRANKED_CONTAINER_ID) return null
  return Number(containerId.slice('rank-'.length))
}

function findContainerForImage(
  board: RankingBoardState,
  imageId: string,
): RankingContainerId | null {
  if (board.unranked.includes(imageId)) return UNRANKED_CONTAINER_ID
  for (let rankIndex = 0; rankIndex < board.rankColumns.length; rankIndex += 1) {
    if (board.rankColumns[rankIndex].includes(imageId)) {
      return rankContainerId(rankIndex)
    }
  }
  return null
}

function itemsForContainer(board: RankingBoardState, containerId: RankingContainerId): string[] {
  if (containerId === UNRANKED_CONTAINER_ID) {
    return board.unranked
  }
  const rankIndex = rankIndexForContainerId(containerId)
  if (rankIndex == null) return []
  return board.rankColumns[rankIndex] ?? []
}

function RankingCardContent({
  image,
  label,
  dotColor,
  onOpenFullscreen,
}: RankingCardContentProps) {
  return (
    <>
      {onOpenFullscreen ? (
        <button
          type="button"
          className="ranking-card-fullscreen"
          onPointerDown={(event) => {
            event.preventDefault()
            event.stopPropagation()
          }}
          onClick={(event) => {
            event.preventDefault()
            event.stopPropagation()
            onOpenFullscreen()
          }}
          aria-label={`Open ${label} fullscreen`}
        >
          <FullscreenIcon />
          <span className="sr-only">Fullscreen</span>
        </button>
      ) : null}
      <div className="ranking-card-image-shell">
        <img src={image.url} alt={image.sourcePath} loading="lazy" draggable={false} />
      </div>
      <div className="ranking-card-meta">
        <span
          className="ranking-card-dot"
          style={{ backgroundColor: dotColor }}
          aria-hidden="true"
        />
        <div className="ranking-card-label">{label}</div>
      </div>
    </>
  )
}

function SortableRankingCard({
  imageId,
  image,
  label,
  dotColor,
  containerId,
  isSelected,
  draggingDisabled,
  onSelect,
  onOpenFullscreen,
  registerCardRef,
}: SortableRankingCardProps) {
  const { attributes, listeners, setNodeRef, transform, isDragging } = useSortable({
    id: imageId,
    data: { containerId },
    disabled: draggingDisabled,
    transition: null,
    animateLayoutChanges: () => false,
  })
  const style: CSSProperties = {
    transform: CSS.Transform.toString(transform),
    transition: 'none',
  }
  const className = [
    'ranking-card',
    isSelected && 'is-selected',
    isDragging && 'is-dragging',
  ]
    .filter(Boolean)
    .join(' ')
  return (
    <article
      className={className}
      ref={(element) => {
        setNodeRef(element)
        registerCardRef(imageId, element)
      }}
      style={style}
      onClick={onSelect}
      {...attributes}
      {...listeners}
    >
      <RankingCardContent
        image={image}
        label={label}
        dotColor={dotColor}
        onOpenFullscreen={onOpenFullscreen}
      />
    </article>
  )
}

function RankingDropColumn({
  containerId,
  title,
  imageIds,
  className,
  cardsClassName,
  cardsStyle,
  isDragOver,
  renderCard,
}: RankingDropColumnProps) {
  const { setNodeRef } = useDroppable({ id: containerId })
  const strategy = containerId === UNRANKED_CONTAINER_ID
    ? rectSortingStrategy
    : verticalListSortingStrategy
  const columnClassName = ['ranking-column', className, isDragOver && 'is-drag-over']
    .filter(Boolean)
    .join(' ')
  return (
    <section className={columnClassName}>
      <header className="ranking-column-header ranking-unselectable">{title}</header>
      <div ref={setNodeRef} className={`ranking-column-cards ${cardsClassName}`} style={cardsStyle}>
        <SortableContext id={containerId} items={imageIds} strategy={strategy}>
          {imageIds.map((imageId) => renderCard(imageId, containerId))}
        </SortableContext>
      </div>
    </section>
  )
}

export default function RankingApp() {
  const [dataset, setDataset] = useState<RankingDatasetResponse | null>(null)
  const [sessions, setSessions] = useState<Record<string, InstanceSession>>({})
  const [currentIndex, setCurrentIndex] = useState(0)
  const [loading, setLoading] = useState(true)
  const [loadError, setLoadError] = useState<string | null>(null)
  const [activeDragImageId, setActiveDragImageId] = useState<string | null>(null)
  const [dragOverContainerId, setDragOverContainerId] = useState<RankingContainerId | null>(null)
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
  const dragPointerOffsetRef = useRef<{ x: number; y: number } | null>(null)
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
      options?: { autoAdvance?: boolean; targetInsertIndex?: number },
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
        : moveImageToRank(current.board, imageId, rankIndex, options?.targetInsertIndex)
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
    setDragOverContainerId(null)
    setActiveDragImageId(null)
    dragPointerOffsetRef.current = null
  }, [])

  const onSplitterPointerDown = useCallback((event: ReactPointerEvent<HTMLDivElement>) => {
    if (!splitterEnabled) return
    if ((event.pointerType ?? 'mouse') !== 'mouse') return
    if (event.button !== 0) return
    if (activeDragImageId) return

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
  }, [activeDragImageId, clearDragState, splitterEnabled])

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
      if (isResizingSplit || !currentSession) return
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
    [currentSession, isResizingSplit, selectCurrentImage],
  )

  const handleDragOver = useCallback(
    (event: DragOverEvent) => {
      if (!currentInstance) return
      const current = sessionsRef.current[currentInstance.instance_id]
      if (!current) return
      const overId = event.over ? String(event.over.id) : null
      setDragOverContainerId(resolveContainerId(current.board, overId))
    },
    [currentInstance, resolveContainerId],
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
    [clearDragState, currentInstance, moveCurrentImageToRank, resolveContainerId],
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

  const rankCount = Math.max(1, currentSession.board.rankColumns.length)
  const rankHotkeyHint = `1-${rankCount}`
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

  const renderCard = (imageId: string, containerId: RankingContainerId) => {
    const image = imageById.get(imageId)
    if (!image) return null
    const isSelected = currentSession.board.selectedImageId === imageId
    const label = cardLabel(image.sourcePath)
    const dotColor = dotColorByImageId[imageId] ?? DEFAULT_DOT_COLOR
    return (
      <SortableRankingCard
        key={imageId}
        imageId={imageId}
        image={image}
        label={label}
        dotColor={dotColor}
        containerId={containerId}
        isSelected={isSelected}
        draggingDisabled={isResizingSplit}
        onSelect={() => selectCurrentImage(imageId)}
        onOpenFullscreen={() => openFullscreenForImage(imageId)}
        registerCardRef={registerCardRef}
      />
    )
  }
  const dragOverlayImage = activeDragImageId ? imageById.get(activeDragImageId) ?? null : null
  const dragOverlayLabel = dragOverlayImage ? cardLabel(dragOverlayImage.sourcePath) : null
  const dragOverlayColor = activeDragImageId
    ? dotColorByImageId[activeDragImageId] ?? DEFAULT_DOT_COLOR
    : DEFAULT_DOT_COLOR

  return (
    <div className="ranking-root">
      <header className="ranking-header ranking-unselectable">
        <div className="ranking-header-meta">
          <h1 className="ranking-title">Image Ranking</h1>
          <strong className="ranking-progress-pill">
            {currentIndex + 1} / {dataset.instances.length}
          </strong>
          <span className="ranking-instance-id">instance: {currentInstance.instance_id}</span>
          <span className="ranking-save-status">{saveStateLabel(currentSession)}</span>
          <span className="ranking-hotkeys-inline">
            Hotkeys: {rankHotkeyHint} rank, arrows move, Enter fullscreen, Esc close
          </span>
        </div>
        <div className="ranking-header-actions">
          <a className="ranking-button ranking-export-button" href={exportHref} target="_blank" rel="noreferrer">
            <Download className="ranking-button-icon" aria-hidden="true" />
            Export
          </a>
          <div className="ranking-nav-group">
            <button
              type="button"
              className="ranking-button"
              onClick={goPrev}
              disabled={!canGoPrev}
            >
              <ChevronLeft className="ranking-button-icon" aria-hidden="true" />
              <span>{'< Prev (Q)'}</span>
            </button>
            <span
              className="ranking-next-tooltip"
              title={!canGoNext ? 'Rank all images before continuing.' : undefined}
            >
              <button
                type="button"
                className="ranking-button ranking-button-primary"
                onClick={goNext}
                disabled={!canGoNext}
              >
                <span>{'Next (E) >'}</span>
                <ChevronRight className="ranking-button-icon" aria-hidden="true" />
              </button>
            </span>
          </div>
        </div>
      </header>

      <DndContext
        sensors={sensors}
        collisionDetection={(args) => {
          const pointerCollisions = pointerWithin(args)
          return pointerCollisions.length > 0 ? pointerCollisions : closestCenter(args)
        }}
        onDragStart={handleDragStart}
        onDragOver={handleDragOver}
        onDragEnd={handleDragEnd}
        onDragCancel={clearDragState}
      >
        <div className={workspaceClassName} ref={workspaceRef} style={workspaceStyle}>
          <RankingDropColumn
            containerId={UNRANKED_CONTAINER_ID}
            title="Unranked"
            imageIds={currentSession.board.unranked}
            className="ranking-column-unranked"
            cardsClassName="ranking-column-cards-unranked"
            isDragOver={dragOverContainerId === UNRANKED_CONTAINER_ID}
            renderCard={renderCard}
          />
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
            <header className="ranking-ranks-header ranking-unselectable">Ranks</header>
            <div className="ranking-ranks-board">
              {currentSession.board.rankColumns.map((column, rankIdx) => (
                <RankingDropColumn
                  key={rankIdx}
                  containerId={rankContainerId(rankIdx)}
                  title={`${rankIdx + 1}`}
                  imageIds={column}
                  className="ranking-column-rank"
                  cardsClassName="ranking-column-cards-rank"
                  isDragOver={dragOverContainerId === rankContainerId(rankIdx)}
                  renderCard={renderCard}
                />
              ))}
            </div>
          </section>
        </div>
        <DragOverlay modifiers={dragOverlayModifiers} dropAnimation={null}>
          {dragOverlayImage && dragOverlayLabel ? (
            <article className="ranking-card ranking-card-overlay">
              <RankingCardContent
                image={dragOverlayImage}
                label={dragOverlayLabel}
                dotColor={dragOverlayColor}
              />
            </article>
          ) : null}
        </DragOverlay>
      </DndContext>

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
              Hotkeys: {rankHotkeyHint} rank, a/d image, Esc close
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
