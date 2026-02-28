import {
  useState,
  useEffect,
  useMemo,
  useRef,
  useCallback,
  createContext,
  type PointerEvent as ReactPointerEvent,
} from 'react'
import {
  DndContext,
  closestCenter,
  pointerWithin,
  PointerSensor,
  KeyboardSensor,
  useSensor,
  useSensors,
  type DragEndEvent,
  type DragStartEvent,
  DragOverlay,
} from '@dnd-kit/core'
import { arrayMove, sortableKeyboardCoordinates } from '@dnd-kit/sortable'
import { BASE } from '../../api/base'
import { rankingApi } from './api'
import {
  buildBoardState,
  moveImageToRank,
  moveImageToRankWithAutoAdvance,
  finalRanksFromBoard,
  isBoardComplete,
  type RankingBoardState,
} from './model/board'
import type {
  RankingDatasetResponse,
  RankingInstance,
  RankingSaveRequest,
  RankingExportEntry,
} from './types'
import { Header } from './components/Header'
import { RankColumn } from './components/RankColumn'
import { ImageCard } from './components/ImageCard'
import { Lightbox } from './components/Lightbox'

export const RankingContext = createContext<{
  getImageUrl: (id: string) => string
  onEnlarge: (id: string) => void
}>({
  getImageUrl: () => '',
  onEnlarge: () => {},
})

const UNASSIGNED_DEFAULT_HEIGHT = 200
const UNASSIGNED_MIN_HEIGHT = 120

function getAlphaLabel(index: number): string {
  let value = index
  let label = ''
  do {
    label = String.fromCharCode(65 + (value % 26)) + label
    value = Math.floor(value / 26) - 1
  } while (value >= 0)
  return label
}

function emptyBoard(): RankingBoardState {
  return { unranked: [], rankColumns: [], selectedImageId: null }
}

function initBoardForInstance(
  instance: RankingInstance,
  saved?: RankingExportEntry,
): RankingBoardState {
  const ids = instance.images.map((img) => img.image_id)
  return buildBoardState(ids, instance.max_ranks, saved?.final_ranks ?? null)
}

export default function RankingApp() {
  const [dataset, setDataset] = useState<RankingDatasetResponse | null>(null)
  const [currentIndex, setCurrentIndex] = useState(0)
  const [board, setBoard] = useState<RankingBoardState>(emptyBoard)
  const [activeId, setActiveId] = useState<string | null>(null)
  const [startedAt, setStartedAt] = useState(Date.now())
  const [completedInstances, setCompletedInstances] = useState<Set<string>>(
    new Set(),
  )
  const [resultsCache, setResultsCache] = useState<
    Record<string, RankingExportEntry>
  >({})
  const [viewingImage, setViewingImage] = useState<string | null>(null)
  const [unassignedHeight, setUnassignedHeight] = useState(
    UNASSIGNED_DEFAULT_HEIGHT,
  )
  const [loading, setLoading] = useState(true)
  const [loadError, setLoadError] = useState<string | null>(null)
  const resizeRef = useRef<{ startY: number; startH: number } | null>(null)

  const sensors = useSensors(
    useSensor(PointerSensor, { activationConstraint: { distance: 5 } }),
    useSensor(KeyboardSensor, {
      coordinateGetter: sortableKeyboardCoordinates,
    }),
  )

  const currentInstance = dataset?.instances[currentIndex] ?? null
  const numRanks = currentInstance?.max_ranks ?? 0

  const imageById = useMemo(() => {
    const m = new Map<string, { url: string; sourcePath: string }>()
    if (!currentInstance) return m
    for (const img of currentInstance.images) {
      m.set(img.image_id, { url: img.url, sourcePath: img.source_path })
    }
    return m
  }, [currentInstance])

  const imageLabels = useMemo(() => {
    if (!currentInstance) return {} as Record<string, string>
    return Object.fromEntries(
      currentInstance.images.map((img, i) => [img.image_id, getAlphaLabel(i)]),
    )
  }, [currentInstance])

  const currentImageOrder = useMemo(
    () => currentInstance?.images.map((img) => img.image_id) ?? [],
    [currentInstance],
  )

  const getImageUrl = useCallback(
    (id: string) => imageById.get(id)?.url ?? '',
    [imageById],
  )

  // --- Data fetching ---

  useEffect(() => {
    let active = true
    Promise.all([
      rankingApi.getDataset(),
      rankingApi.getProgress(),
      rankingApi.exportLatest(false),
    ])
      .then(([ds, progress, exported]) => {
        if (!active) return
        const cache: Record<string, RankingExportEntry> = {}
        for (const entry of exported.results) {
          cache[entry.instance_id] = entry
        }
        setDataset(ds)
        setCompletedInstances(new Set(progress.completed_instance_ids))
        setResultsCache(cache)

        const startIdx = Math.min(
          Math.max(0, progress.resume_instance_index),
          ds.instances.length - 1,
        )
        setCurrentIndex(startIdx)

        const inst = ds.instances[startIdx]
        if (inst) {
          setBoard(initBoardForInstance(inst, cache[inst.instance_id]))
        }
        setLoading(false)
      })
      .catch((err) => {
        if (!active) return
        setLoadError(err instanceof Error ? err.message : 'Failed to load')
        setLoading(false)
      })
    return () => {
      active = false
    }
  }, [])

  // Preload next instance images
  useEffect(() => {
    if (!dataset) return
    const next = dataset.instances[currentIndex + 1]
    if (!next) return
    for (const img of next.images) {
      const preload = new Image()
      preload.src = img.url
    }
  }, [dataset, currentIndex])

  // --- Persistence ---

  const saveBoard = useCallback(
    (boardToSave: RankingBoardState) => {
      if (!currentInstance) return
      const payload: RankingSaveRequest = {
        instance_id: currentInstance.instance_id,
        final_ranks: finalRanksFromBoard(boardToSave),
        started_at: new Date(startedAt).toISOString(),
        duration_ms: Date.now() - startedAt,
        completed: isBoardComplete(boardToSave),
      }
      rankingApi
        .save(payload)
        .then(() => {
          if (payload.completed) {
            setCompletedInstances((prev) =>
              new Set(prev).add(currentInstance.instance_id),
            )
          }
          setResultsCache((prev) => ({
            ...prev,
            [currentInstance.instance_id]: payload as unknown as RankingExportEntry,
          }))
        })
        .catch((err) => console.error('Save failed:', err))
    },
    [currentInstance, startedAt],
  )

  // --- DnD container helpers ---

  const findContainer = useCallback(
    (id: string): string | undefined => {
      if (board.unranked.includes(id)) return 'unassigned'
      for (let i = 0; i < board.rankColumns.length; i++) {
        if (board.rankColumns[i].includes(id)) return (i + 1).toString()
      }
      return undefined
    },
    [board],
  )

  const handleDragStart = (event: DragStartEvent) => {
    setActiveId(event.active.id as string)
  }

  const handleDragEnd = (event: DragEndEvent) => {
    const { active, over } = event
    setActiveId(null)
    if (!over) return

    const draggedId = active.id as string
    const overId = over.id as string
    const from = findContainer(draggedId)
    const to = findContainer(overId) || overId
    if (!from || !to) return

    if (from !== to) {
      const rankIndex = to === 'unassigned' ? null : parseInt(to) - 1
      const newBoard = moveImageToRank(board, draggedId, rankIndex)
      if (newBoard !== board) {
        setBoard(newBoard)
        setTimeout(() => saveBoard(newBoard), 0)
      }
    } else {
      if (overId === draggedId) return
      const items =
        to === 'unassigned'
          ? board.unranked
          : board.rankColumns[parseInt(to) - 1]
      if (!items) return
      const oldIdx = items.indexOf(draggedId)
      const newIdx = items.indexOf(overId)
      if (oldIdx < 0 || newIdx < 0 || oldIdx === newIdx) return
      const reordered = arrayMove(items, oldIdx, newIdx)

      let newBoard: RankingBoardState
      if (to === 'unassigned') {
        newBoard = { ...board, unranked: reordered }
      } else {
        const colIdx = parseInt(to) - 1
        newBoard = {
          ...board,
          rankColumns: board.rankColumns.map((col, i) =>
            i === colIdx ? reordered : col,
          ),
        }
      }
      setBoard(newBoard)
      setTimeout(() => saveBoard(newBoard), 0)
    }
  }

  // --- Rank assignment (keyboard + lightbox) ---

  const moveToRank = useCallback(
    (imageId: string, rank1Based: number) => {
      const rankIndex = rank1Based - 1
      const newBoard = moveImageToRank(board, imageId, rankIndex)
      if (newBoard !== board) {
        setBoard(newBoard)
        saveBoard(newBoard)
      }
    },
    [board, saveBoard],
  )

  // --- Navigation ---

  const canProceed = isBoardComplete(board)

  const handlePrev = useCallback(() => {
    if (currentIndex <= 0 || !dataset) return
    const newIdx = currentIndex - 1
    setCurrentIndex(newIdx)
    const inst = dataset.instances[newIdx]
    if (inst) {
      setBoard(initBoardForInstance(inst, resultsCache[inst.instance_id]))
      setStartedAt(Date.now())
    }
  }, [currentIndex, dataset, resultsCache])

  const handleNext = useCallback(() => {
    if (!canProceed || !dataset || currentIndex >= dataset.instances.length - 1)
      return
    saveBoard(board)
    const newIdx = currentIndex + 1
    setCurrentIndex(newIdx)
    const inst = dataset.instances[newIdx]
    if (inst) {
      setBoard(initBoardForInstance(inst, resultsCache[inst.instance_id]))
      setStartedAt(Date.now())
    }
  }, [board, canProceed, currentIndex, dataset, resultsCache, saveBoard])

  // --- Unassigned resize ---

  useEffect(() => {
    const onMove = (e: PointerEvent) => {
      if (!resizeRef.current) return
      const { startY, startH } = resizeRef.current
      const delta = e.clientY - startY
      const maxH = Math.max(
        UNASSIGNED_DEFAULT_HEIGHT,
        window.innerHeight - 280,
      )
      setUnassignedHeight(
        Math.min(maxH, Math.max(UNASSIGNED_MIN_HEIGHT, startH + delta)),
      )
    }
    const onUp = () => {
      if (!resizeRef.current) return
      resizeRef.current = null
      document.body.style.cursor = ''
      document.body.style.userSelect = ''
    }
    window.addEventListener('pointermove', onMove)
    window.addEventListener('pointerup', onUp)
    window.addEventListener('pointercancel', onUp)
    return () => {
      window.removeEventListener('pointermove', onMove)
      window.removeEventListener('pointerup', onUp)
      window.removeEventListener('pointercancel', onUp)
    }
  }, [])

  const handleResizeStart = (e: ReactPointerEvent<HTMLButtonElement>) => {
    e.preventDefault()
    resizeRef.current = { startY: e.clientY, startH: unassignedHeight }
    e.currentTarget.setPointerCapture(e.pointerId)
    document.body.style.cursor = 'row-resize'
    document.body.style.userSelect = 'none'
  }

  // --- Keyboard ---

  useEffect(() => {
    const handleKeyDown = (e: KeyboardEvent) => {
      if (document.getElementById('lightbox-container')) return
      const tag = (e.target as HTMLElement)?.tagName?.toLowerCase()
      if (tag === 'input' || tag === 'textarea' || tag === 'select') return

      if (e.key === 'Enter') {
        const el = document.activeElement
        if (el && el.hasAttribute('data-image-id')) {
          setViewingImage(el.getAttribute('data-image-id'))
        }
        return
      }

      if (e.key.toLowerCase() === 'q') {
        handlePrev()
        return
      }
      if (e.key.toLowerCase() === 'e') {
        handleNext()
        return
      }

      const numKey = parseInt(e.key)
      if (!isNaN(numKey) && numKey >= 1 && numKey <= numRanks) {
        const el = document.activeElement
        if (el && el.hasAttribute('data-image-id')) {
          const imageId = el.getAttribute('data-image-id') as string
          const rankIndex = numKey - 1
          const newBoard = moveImageToRankWithAutoAdvance(
            board,
            imageId,
            rankIndex,
            currentImageOrder,
          )
          if (newBoard !== board) {
            setBoard(newBoard)
            saveBoard(newBoard)
            setTimeout(() => {
              if (newBoard.selectedImageId) {
                const escaped =
                  window.CSS?.escape?.(newBoard.selectedImageId) ??
                  newBoard.selectedImageId
                const next = document.querySelector(
                  `[data-image-id="${escaped}"]`,
                ) as HTMLElement | null
                next?.focus()
              }
            }, 50)
          }
        }
      }
    }
    window.addEventListener('keydown', handleKeyDown)
    return () => window.removeEventListener('keydown', handleKeyDown)
  }, [
    board,
    numRanks,
    currentImageOrder,
    handlePrev,
    handleNext,
    saveBoard,
  ])

  // --- Export ---

  const handleExport = () =>
    window.open(`${BASE}/rank/export?completed_only=true`, '_blank')

  // --- Render ---

  if (loading) {
    return (
      <div className="flex h-screen items-center justify-center text-zinc-500">
        Loading ranking session...
      </div>
    )
  }

  if (loadError || !currentInstance || !dataset) {
    return (
      <div className="flex h-screen items-center justify-center flex-col gap-3">
        <p className="text-zinc-600 font-medium">
          Failed to load ranking mode
        </p>
        <pre className="text-sm text-zinc-400 bg-zinc-100 px-4 py-2 rounded-lg max-w-lg">
          {loadError ?? 'Missing dataset'}
        </pre>
      </div>
    )
  }

  return (
    <RankingContext.Provider value={{ getImageUrl, onEnlarge: setViewingImage }}>
      <div className="flex flex-col h-screen bg-[#FAFAFA] text-zinc-900 font-sans">
        <Header
          currentIndex={currentIndex}
          totalInstances={dataset.instances.length}
          onPrev={handlePrev}
          onNext={handleNext}
          onExport={handleExport}
          canProceed={canProceed}
          isFirst={currentIndex === 0}
          isLast={currentIndex === dataset.instances.length - 1}
        />

        <main className="flex-1 overflow-auto p-4 sm:p-6 lg:p-8">
          <DndContext
            sensors={sensors}
            collisionDetection={(args) => {
              const p = pointerWithin(args)
              return p.length > 0 ? p : closestCenter(args)
            }}
            onDragStart={handleDragStart}
            onDragEnd={handleDragEnd}
          >
            <div className="flex flex-col gap-6 h-full max-w-screen-2xl mx-auto">
              {/* Unassigned area */}
              <div className="bg-white p-5 rounded-2xl shadow-sm border border-zinc-200/60 flex-shrink-0">
                <div className="mb-4 flex items-center justify-between gap-3">
                  <div className="flex items-center gap-2">
                    <div className="w-2 h-2 rounded-full bg-zinc-300" />
                    <h2 className="text-xs font-semibold text-zinc-500 uppercase tracking-widest">
                      Unassigned
                    </h2>
                  </div>
                  <p className="text-xs font-mono text-zinc-500">
                    Press 1-{numRanks} or drag
                  </p>
                </div>
                <div style={{ height: `${unassignedHeight}px` }}>
                  <RankColumn
                    id="unassigned"
                    items={board.unranked}
                    imageLabels={imageLabels}
                    className="h-full min-h-0 overflow-y-auto p-1 flex gap-4 flex-wrap content-start"
                  />
                </div>
                <div className="mt-2 flex justify-center">
                  <button
                    type="button"
                    onPointerDown={handleResizeStart}
                    className="h-2 w-28 rounded-full bg-zinc-200/80 transition-all duration-200 hover:bg-zinc-300 cursor-row-resize"
                    aria-label="Resize unassigned section"
                    title="Drag to resize"
                  />
                </div>
              </div>

              {/* Rank columns */}
              <div className="flex gap-4 flex-1 overflow-x-auto pb-4">
                {Array.from({ length: numRanks }).map((_, i) => {
                  const rankId = (i + 1).toString()
                  return (
                    <div
                      key={rankId}
                      className="flex-1 min-w-[200px] flex flex-col bg-zinc-50/80 rounded-2xl p-4 border border-zinc-200/60 shadow-sm"
                    >
                      <div className="text-center mb-4 flex flex-col items-center gap-2">
                        <span className="inline-flex items-center justify-center w-8 h-8 rounded-full bg-white border border-zinc-200 text-zinc-700 font-mono text-sm font-medium shadow-sm">
                          {rankId}
                        </span>
                        <div className="h-px w-12 bg-zinc-200/60" />
                      </div>
                      <RankColumn
                        id={rankId}
                        items={board.rankColumns[i] || []}
                        imageLabels={imageLabels}
                        className="flex-1 flex flex-col items-center gap-3 min-h-[200px]"
                      />
                    </div>
                  )
                })}
              </div>
            </div>

            <DragOverlay>
              {activeId ? (
                <ImageCard
                  id={activeId}
                  isOverlay
                  badgeLabel={imageLabels[activeId]}
                />
              ) : null}
            </DragOverlay>
          </DndContext>
        </main>

        {viewingImage && currentInstance && (
          <Lightbox
            imageId={viewingImage}
            imageIds={currentImageOrder}
            onClose={() => setViewingImage(null)}
            onRank={moveToRank}
            numRanks={numRanks}
          />
        )}
      </div>
    </RankingContext.Provider>
  )
}
