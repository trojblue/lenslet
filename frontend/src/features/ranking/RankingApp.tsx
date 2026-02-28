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
import { isStaleSaveResponse, nextSaveSeq } from './model/saveSeq'
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

function nowIso(): string {
  return new Date().toISOString()
}

function cardLabel(sourcePath: string): string {
  const name = sourcePath.split('/').filter(Boolean).pop()
  return name || sourcePath
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
  const issuedSeqRef = useRef<Record<string, number>>({})
  useEffect(() => {
    sessionsRef.current = sessions
  }, [sessions])

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
        const initialSessions = buildInitialSessions(datasetPayload, exportPayload.results)
        const initialSeq: Record<string, number> = {}
        for (const [instanceId, session] of Object.entries(initialSessions)) {
          initialSeq[instanceId] = session.latestIssuedSeq
        }
        setDataset(datasetPayload)
        setSessions(initialSessions)
        issuedSeqRef.current = initialSeq
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
    const map = new Map<string, { url: string; sourcePath: string }>()
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

  const ensureStartedAt = useCallback((instanceId: string): string => {
    const existing = sessionsRef.current[instanceId]?.startedAt
    if (isValidIsoTimestamp(existing)) {
      return existing
    }
    const startedAt = nowIso()
    setSessions((prev) => {
      const session = prev[instanceId]
      if (!session || isValidIsoTimestamp(session.startedAt)) return prev
      return {
        ...prev,
        [instanceId]: {
          ...session,
          startedAt,
        },
      }
    })
    return startedAt
  }, [])

  const persistSnapshot = useCallback(
    (instance: RankingInstance, board: RankingBoardState, startedAtInput: string | null = null) => {
      const startedAt = isValidIsoTimestamp(startedAtInput)
        ? startedAtInput
        : ensureStartedAt(instance.instance_id)
      const issuedSeq = nextSaveSeq(issuedSeqRef.current[instance.instance_id] ?? 0)
      issuedSeqRef.current[instance.instance_id] = issuedSeq
      setSessions((prev) => {
        const session = prev[instance.instance_id]
        if (!session) return prev
        return {
          ...prev,
          [instance.instance_id]: {
            ...session,
            latestIssuedSeq: Math.max(session.latestIssuedSeq, issuedSeq),
            saveStatus: 'saving',
            saveError: null,
          },
        }
      })

      const payload: RankingSaveRequest = {
        instance_id: instance.instance_id,
        final_ranks: finalRanksFromBoard(board),
        started_at: startedAt,
        duration_ms: computeDurationMs(startedAt),
        completed: isBoardComplete(board),
        save_seq: issuedSeq,
      }

      const attemptSave = async (attempt: number): Promise<void> => {
        try {
          await rankingApi.save(payload)
          setSessions((prev) => {
            const session = prev[instance.instance_id]
            if (!session) return prev
            if (isStaleSaveResponse(issuedSeq, issuedSeqRef.current[instance.instance_id] ?? 0)) {
              return prev
            }
            return {
              ...prev,
              [instance.instance_id]: {
                ...session,
                latestAckSeq: Math.max(session.latestAckSeq, issuedSeq),
                saveStatus: 'saved',
                saveError: null,
              },
            }
          })
        } catch (error) {
          const message = error instanceof Error ? error.message : 'failed to save ranking'
          setSessions((prev) => {
            const session = prev[instance.instance_id]
            if (!session) return prev
            if (isStaleSaveResponse(issuedSeq, issuedSeqRef.current[instance.instance_id] ?? 0)) {
              return prev
            }
            return {
              ...prev,
              [instance.instance_id]: {
                ...session,
                saveStatus: 'error',
                saveError: message,
              },
            }
          })
          if (attempt > 0) return
          window.setTimeout(() => {
            if (isStaleSaveResponse(issuedSeq, issuedSeqRef.current[instance.instance_id] ?? 0)) {
              return
            }
            void attemptSave(1)
          }, 900)
        }
      }

      void attemptSave(0)
    },
    [ensureStartedAt],
  )

  const moveCurrentImageToRank = useCallback(
    (imageId: string, rankIndex: number | null) => {
      if (!currentInstance) return
      const current = sessionsRef.current[currentInstance.instance_id]
      if (!current) return
      const boardSnapshot = moveImageToRank(current.board, imageId, rankIndex)
      if (boardSnapshot === current.board) return
      setSessions((prev) => {
        const session = prev[currentInstance.instance_id]
        if (!session) return prev
        return {
          ...prev,
          [currentInstance.instance_id]: {
            ...session,
            board: boardSnapshot,
          },
        }
      })
      persistSnapshot(currentInstance, boardSnapshot, current.startedAt)
    },
    [currentInstance, persistSnapshot],
  )

  const selectCurrentImage = useCallback(
    (imageId: string) => {
      if (!currentInstance) return
      setSessions((prev) => {
        const session = prev[currentInstance.instance_id]
        if (!session) return prev
        return {
          ...prev,
          [currentInstance.instance_id]: {
            ...session,
            board: {
              ...session.board,
              selectedImageId: imageId,
            },
          },
        }
      })
    },
    [currentInstance],
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

  const dropOnRank = useCallback(
    (event: DragEvent<HTMLElement>, rankIndex: number | null) => {
      event.preventDefault()
      const imageId = event.dataTransfer.getData('text/plain') || draggingImageId
      setDragOverRank(null)
      setDraggingImageId(null)
      if (!imageId) return
      moveCurrentImageToRank(imageId, rankIndex)
    },
    [draggingImageId, moveCurrentImageToRank],
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
  const saveStateLabel = (
    currentSession.saveStatus === 'saving' ? 'Saving...'
      : currentSession.saveStatus === 'saved' ? 'Saved'
        : currentSession.saveStatus === 'error' ? `Save failed: ${currentSession.saveError ?? 'unknown error'}`
          : 'Idle'
  )

  const exportHref = `${BASE}/rank/export?completed_only=true`

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
          <span className="ranking-save-status">{saveStateLabel}</span>
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
        <section
          className={`ranking-column ${dragOverRank === -1 ? 'is-drag-over' : ''}`}
          onDragOver={(event) => {
            event.preventDefault()
            setDragOverRank(-1)
          }}
          onDragLeave={() => setDragOverRank(null)}
          onDrop={(event) => dropOnRank(event, null)}
        >
          <header className="ranking-column-header">Unranked</header>
          <div className="ranking-column-cards">
            {currentSession.board.unranked.map((imageId) => {
              const image = imageById.get(imageId)
              if (!image) return null
              const isSelected = currentSession.board.selectedImageId === imageId
              return (
                <article
                  key={imageId}
                  className={`ranking-card ${isSelected ? 'is-selected' : ''}`}
                  draggable
                  onDragStart={(event) => {
                    event.dataTransfer.setData('text/plain', imageId)
                    event.dataTransfer.effectAllowed = 'move'
                    setDraggingImageId(imageId)
                  }}
                  onDragEnd={() => {
                    setDraggingImageId(null)
                    setDragOverRank(null)
                  }}
                  onClick={() => selectCurrentImage(imageId)}
                >
                  <img src={image.url} alt={image.sourcePath} loading="lazy" draggable={false} />
                  <div className="ranking-card-label">{cardLabel(image.sourcePath)}</div>
                </article>
              )
            })}
          </div>
        </section>

        {currentSession.board.rankColumns.map((column, rankIdx) => (
          <section
            key={`rank-${rankIdx}`}
            className={`ranking-column ${dragOverRank === rankIdx ? 'is-drag-over' : ''}`}
            onDragOver={(event) => {
              event.preventDefault()
              setDragOverRank(rankIdx)
            }}
            onDragLeave={() => setDragOverRank(null)}
            onDrop={(event) => dropOnRank(event, rankIdx)}
          >
            <header className="ranking-column-header">Rank {rankIdx + 1}</header>
            <div className="ranking-column-cards">
              {column.map((imageId) => {
                const image = imageById.get(imageId)
                if (!image) return null
                const isSelected = currentSession.board.selectedImageId === imageId
                return (
                  <article
                    key={imageId}
                    className={`ranking-card ${isSelected ? 'is-selected' : ''}`}
                    draggable
                    onDragStart={(event) => {
                      event.dataTransfer.setData('text/plain', imageId)
                      event.dataTransfer.effectAllowed = 'move'
                      setDraggingImageId(imageId)
                    }}
                    onDragEnd={() => {
                      setDraggingImageId(null)
                      setDragOverRank(null)
                    }}
                    onClick={() => selectCurrentImage(imageId)}
                  >
                    <img src={image.url} alt={image.sourcePath} loading="lazy" draggable={false} />
                    <div className="ranking-card-label">{cardLabel(image.sourcePath)}</div>
                  </article>
                )
              })}
            </div>
          </section>
        ))}
      </div>

      <footer className="ranking-footer">
        <span>{ordered.length} images</span>
        <span>Hotkeys: 1-9 rank selected, arrows move selection, Enter next, Backspace prev</span>
      </footer>
    </div>
  )
}
