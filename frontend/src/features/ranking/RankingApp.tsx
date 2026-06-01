import {
  useCallback,
  useMemo,
  useRef,
  type CSSProperties,
  type ReactNode,
} from 'react'
import {
  DndContext,
  DragOverlay,
  closestCenter,
  pointerWithin,
  useDroppable,
} from '@dnd-kit/core'
import {
  SortableContext,
  rectSortingStrategy,
  useSortable,
  verticalListSortingStrategy,
} from '@dnd-kit/sortable'
import { CSS } from '@dnd-kit/utilities'
import { ChevronLeft, ChevronRight, Download } from 'lucide-react'
import { apiUrl } from '../../api/base'
import { cssVars } from '../../lib/cssVars'
import './ranking.css'
import {
  clampUnrankedThumbSizePx,
  UNRANKED_THUMB_SIZE_MAX_PX,
  UNRANKED_THUMB_SIZE_MIN_PX,
  UNRANKED_THUMB_SIZE_STEP_PX,
  useUnrankedPanelSizing,
} from './hooks/useUnrankedPanelSizing'
import { useRankingDrag } from './hooks/useRankingDrag'
import { useRankingFullscreen } from './hooks/useRankingFullscreen'
import { useRankingKeyboard } from './hooks/useRankingKeyboard'
import { useRankingSession } from './hooks/useRankingSession'
import {
  rankContainerId,
  UNRANKED_CONTAINER_ID,
  type RankingContainerId,
} from './model/containers'
import { RANKING_DOT_COLORS, buildDotColorByImageId } from './model/palette'

type ImageView = {
  url: string
  sourcePath: string
}

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

function cardLabel(sourcePath: string): string {
  const name = sourcePath.split('/').filter(Boolean).pop()
  return name || sourcePath
}

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
  showHeader?: boolean
  headerContent?: ReactNode
  renderCard: (imageId: string, containerId: RankingContainerId) => ReactNode
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
    containerId === UNRANKED_CONTAINER_ID ? 'is-unranked' : 'is-ranked',
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
  showHeader = true,
  headerContent,
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
      {showHeader ? (
        <header className="ranking-column-header ranking-unselectable">
          {headerContent ?? title}
        </header>
      ) : null}
      <div ref={setNodeRef} className={`ranking-column-cards ${cardsClassName}`} style={cardsStyle}>
        <SortableContext id={containerId} items={imageIds} strategy={strategy}>
          {imageIds.map((imageId) => renderCard(imageId, containerId))}
        </SortableContext>
      </div>
    </section>
  )
}

export default function RankingApp() {
  const {
    dataset,
    currentIndex,
    currentInstance,
    currentSession,
    currentImageOrder,
    sessionsRef,
    loading,
    loadError,
    canGoPrev,
    canGoNext,
    goPrev,
    goNext,
    moveCurrentImageToRank,
    selectCurrentImage,
  } = useRankingSession()
  const cardRefs = useRef<Record<string, HTMLElement | null>>({})
  const workspaceRef = useRef<HTMLDivElement | null>(null)

  const imageById = useMemo(() => {
    const map = new Map<string, ImageView>()
    if (!currentInstance) return map
    for (const image of currentInstance.images) {
      map.set(image.image_id, { url: image.url, sourcePath: image.source_path })
    }
    return map
  }, [currentInstance])
  const dotColorByImageId = useMemo(
    () => buildDotColorByImageId(currentImageOrder),
    [currentImageOrder],
  )

  const registerCardRef = useCallback((imageId: string, element: HTMLElement | null) => {
    cardRefs.current[imageId] = element
  }, [])

  const focusCard = useCallback((imageId: string | null) => {
    if (!imageId || typeof window === 'undefined') return
    window.requestAnimationFrame(() => {
      window.requestAnimationFrame(() => {
        cardRefs.current[imageId]?.focus()
      })
    })
  }, [])

  const {
    closeFullscreen,
    fullscreenImageId,
    fullscreenTransform,
    handleFullscreenPointerDown,
    handleFullscreenPointerEnd,
    handleFullscreenPointerMove,
    handleFullscreenWheel,
    isFullscreenZoomed,
    navigateFullscreenImage,
    openFullscreenForImage,
    resetFullscreenTransform,
  } = useRankingFullscreen({
    currentImageOrder,
    currentInstanceId: currentInstance?.instance_id ?? null,
    focusCard,
    selectCurrentImage,
  })
  const fullscreenImage = fullscreenImageId ? imageById.get(fullscreenImageId) ?? null : null

  const {
    activeDragImageId,
    clearDragState,
    dragOverlayModifiers,
    dragOverContainerId,
    handleDragEnd,
    handleDragOver,
    handleDragStart,
    sensors,
  } = useRankingDrag({
    currentInstance,
    currentSession,
    moveCurrentImageToRank,
    selectCurrentImage,
    sessionsRef,
  })

  const {
    isResizingSplit,
    onUnrankedResizeStart,
    setUnrankedThumbSizePx,
    unrankedHeightPx,
    unrankedThumbSizePx,
  } = useUnrankedPanelSizing({
    activeDragImageId,
    clearDragState,
    currentIndex,
    workspaceRef,
  })

  useRankingKeyboard({
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
  })

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
  const exportHref = apiUrl('/rank/export?completed_only=true')
  const fullscreenPosition = fullscreenImageId
    ? currentImageOrder.indexOf(fullscreenImageId) + 1
    : 0
  const workspaceClassName = [
    'ranking-workspace',
    isResizingSplit && 'is-resizing',
  ]
    .filter(Boolean)
    .join(' ')
  const unrankedTrayStyle: CSSProperties = {
    height: `${Math.max(0, Math.trunc(unrankedHeightPx))}px`,
  }
  const rootStyle = cssVars({
    '--ranking-card-size-unranked': `${clampUnrankedThumbSizePx(unrankedThumbSizePx)}px`,
  })

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
    <div className="ranking-root" style={rootStyle}>
      <header className="ranking-header ranking-unselectable">
        <div className="ranking-shell ranking-header-shell">
          <div className="ranking-header-leading">
            <h1 className="ranking-header-title">Image Ranking</h1>
            <strong className="ranking-progress-pill">
              {currentIndex + 1} / {dataset.instances.length}
            </strong>
          </div>

          <div className="ranking-header-trailing">
            <label className="ranking-thumb-size-control ranking-unselectable ranking-thumb-size-control-header">
              <span>Thumbs</span>
              <input
                type="range"
                min={UNRANKED_THUMB_SIZE_MIN_PX}
                max={UNRANKED_THUMB_SIZE_MAX_PX}
                step={UNRANKED_THUMB_SIZE_STEP_PX}
                value={unrankedThumbSizePx}
                onChange={(event) => {
                  setUnrankedThumbSizePx(
                    clampUnrankedThumbSizePx(Number(event.currentTarget.value)),
                  )
                }}
                aria-label="Unassigned thumbnail size"
              />
              <span className="ranking-thumb-size-value">{unrankedThumbSizePx}px</span>
            </label>
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
                <span>{'Prev (Q)'}</span>
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
                  <span>{'Next (E)'}</span>
                  <ChevronRight className="ranking-button-icon" aria-hidden="true" />
                </button>
              </span>
            </div>
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
        <main className="ranking-main">
          <div className="ranking-shell ranking-main-shell">
            <div className={workspaceClassName} ref={workspaceRef}>
              <section className="ranking-unranked-panel">
                <header className="ranking-unranked-head">
                  <h1 className="ranking-title">Unassigned</h1>
                  <p className="ranking-unranked-hint">
                    Press {rankHotkeyHint} to assign selected, Enter for fullscreen
                  </p>
                </header>
                <div className="ranking-unranked-tray" style={unrankedTrayStyle}>
                  <RankingDropColumn
                    containerId={UNRANKED_CONTAINER_ID}
                    title="Unassigned"
                    imageIds={currentSession.board.unranked}
                    className="ranking-column-unranked"
                    cardsClassName="ranking-column-cards-unranked"
                    isDragOver={dragOverContainerId === UNRANKED_CONTAINER_ID}
                    showHeader={false}
                    renderCard={renderCard}
                  />
                </div>
                <div className="ranking-unranked-resizer">
                  <button
                    type="button"
                    className="ranking-unranked-resize-handle"
                    onPointerDown={onUnrankedResizeStart}
                    aria-label="Resize unassigned panel"
                    title="Drag to resize unassigned panel"
                  />
                </div>
              </section>
              <section className="ranking-ranks-panel">
                <div className="ranking-ranks-board">
                  {currentSession.board.rankColumns.map((column, rankIdx) => (
                    <RankingDropColumn
                      key={rankIdx}
                      containerId={rankContainerId(rankIdx)}
                      title={`${rankIdx + 1}`}
                      headerContent={<span className="ranking-rank-index">{rankIdx + 1}</span>}
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
          </div>
        </main>
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
            className={`ranking-fullscreen-stage ${isFullscreenZoomed ? 'is-zoomed' : ''}`}
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
