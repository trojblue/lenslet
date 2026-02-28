import { useCallback, useEffect, useMemo, useRef, useState, type DragEvent } from 'react'
import { BASE } from '../../api/base'
import { rankingApi } from './api'
import './ranking.css'
import {
  finalRanksFromBoard,
  isBoardComplete,
  moveImageToRank,
  orderedImageIds,
  selectNeighborImage,
  type RankingBoardState,
} from './model/board'
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

export default function RankingApp() {
  const [dataset, setDataset] = useState<RankingDatasetResponse | null>(null)
  const [sessions, setSessions] = useState<Record<string, InstanceSession>>({})
  const [currentIndex, setCurrentIndex] = useState(0)
  const [loading, setLoading] = useState(true)
  const [loadError, setLoadError] = useState<string | null>(null)
  const [draggingImageId, setDraggingImageId] = useState<string | null>(null)
  const [dragOverRank, setDragOverRank] = useState<number | null>(null)

  const sessionsRef = useRef<Record<string, InstanceSession>>(sessions)
  const saveRequestRef = useRef<Record<string, number>>({})
  useEffect(() => {
    sessionsRef.current = sessions
  }, [sessions])

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

  useEffect(() => {
    if (typeof Image === 'undefined' || !dataset) return
    const nextInstance = dataset.instances[currentIndex + 1]
    if (!nextInstance) return
    for (const image of nextInstance.images) {
      const preload = new Image()
      preload.src = image.url
    }
  }, [dataset, currentIndex])

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
    (imageId: string, rankIndex: number | null) => {
      if (!currentInstance) return
      const current = sessionsRef.current[currentInstance.instance_id]
      if (!current) return
      const boardSnapshot = moveImageToRank(current.board, imageId, rankIndex)
      if (boardSnapshot === current.board) return
      updateSession(currentInstance.instance_id, (session) => ({
        ...session,
        board: boardSnapshot,
      }))
      persistSnapshot(currentInstance, boardSnapshot, current.startedAt)
    },
    [currentInstance, persistSnapshot, updateSession],
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
      const target = event.target as HTMLElement | null
      const tag = target?.tagName?.toLowerCase() ?? ''
      const isEditable = Boolean(
        target?.isContentEditable ||
        tag === 'input' ||
        tag === 'textarea' ||
        tag === 'select',
      )
      if (isEditable) return

      if (event.key >= '1' && event.key <= '9') {
        const rankIndex = Number(event.key) - 1
        const selected = currentSession.board.selectedImageId
        if (selected && rankIndex < currentInstance.max_ranks) {
          event.preventDefault()
          moveCurrentImageToRank(selected, rankIndex)
        }
        return
      }

      if (event.key === 'ArrowLeft' || event.key === 'ArrowRight') {
        event.preventDefault()
        const direction = event.key === 'ArrowLeft' ? 'left' : 'right'
        const nextSelected = selectNeighborImage(currentSession.board, direction)
        if (nextSelected) {
          selectCurrentImage(nextSelected)
        }
        return
      }

      if (event.key === 'Enter') {
        if (canGoNext) {
          event.preventDefault()
          goNext()
        }
        return
      }

      if (event.key === 'Backspace') {
        if (canGoPrev) {
          event.preventDefault()
          goPrev()
        }
      }
    }

    window.addEventListener('keydown', onKeyDown)
    return () => window.removeEventListener('keydown', onKeyDown)
  }, [canGoNext, canGoPrev, currentInstance, currentSession, goNext, goPrev, moveCurrentImageToRank, selectCurrentImage])

  const clearDragState = useCallback(() => {
    setDragOverRank(null)
    setDraggingImageId(null)
  }, [])

  const startDrag = useCallback((event: DragEvent<HTMLElement>, imageId: string) => {
    event.dataTransfer.setData('text/plain', imageId)
    event.dataTransfer.effectAllowed = 'move'
    setDraggingImageId(imageId)
  }, [])

  const dropOnRank = useCallback(
    (event: DragEvent<HTMLElement>, rankIndex: number | null) => {
      event.preventDefault()
      const imageId = event.dataTransfer.getData('text/plain') || draggingImageId
      clearDragState()
      if (!imageId) return
      moveCurrentImageToRank(imageId, rankIndex)
    },
    [clearDragState, draggingImageId, moveCurrentImageToRank],
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

  const renderCard = (imageId: string) => {
    const image = imageById.get(imageId)
    if (!image) return null
    const isSelected = currentSession.board.selectedImageId === imageId
    return (
      <article
        key={imageId}
        className={`ranking-card ${isSelected ? 'is-selected' : ''}`}
        draggable
        onDragStart={(event) => startDrag(event, imageId)}
        onDragEnd={clearDragState}
        onClick={() => selectCurrentImage(imageId)}
      >
        <img src={image.url} alt={image.sourcePath} loading="lazy" draggable={false} />
        <div className="ranking-card-label">{cardLabel(image.sourcePath)}</div>
      </article>
    )
  }

  const renderColumn = (
    title: string,
    imageIds: string[],
    dragValue: number,
    targetRank: number | null,
    key: string,
  ) => (
    <section
      key={key}
      className={`ranking-column ${dragOverRank === dragValue ? 'is-drag-over' : ''}`}
      onDragOver={(event) => {
        event.preventDefault()
        setDragOverRank(dragValue)
      }}
      onDragLeave={() => setDragOverRank(null)}
      onDrop={(event) => dropOnRank(event, targetRank)}
    >
      <header className="ranking-column-header">{title}</header>
      <div className="ranking-column-cards">{imageIds.map(renderCard)}</div>
    </section>
  )

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

      <div className="ranking-board">
        {renderColumn('Unranked', currentSession.board.unranked, -1, null, 'unranked')}
        {currentSession.board.rankColumns.map((column, rankIdx) => (
          renderColumn(
            `Rank ${rankIdx + 1}`,
            column,
            rankIdx,
            rankIdx,
            `rank-${rankIdx}`,
          )
        ))}
      </div>

      <footer className="ranking-footer">
        <span>{ordered.length} images</span>
        <span>Hotkeys: 1-9 rank selected, arrows move selection, Enter next, Backspace prev</span>
      </footer>
    </div>
  )
}
