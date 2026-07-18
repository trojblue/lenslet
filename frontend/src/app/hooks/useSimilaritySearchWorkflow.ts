import { useCallback, useLayoutEffect, useRef, type Dispatch, type SetStateAction } from 'react'
import { api } from '../../api/client'
import { sanitizePath } from '../../lib/paths'
import type { EmbeddingSearchRequest, ViewState } from '../../lib/types'
import type { SimilarityState } from './useAppDataScope'

type UseSimilaritySearchWorkflowParams = {
  similarityState: SimilarityState | null
  setSimilarityState: Dispatch<SetStateAction<SimilarityState | null>>
  selectedPaths: string[]
  setSelectedPaths: Dispatch<SetStateAction<string[]>>
  setQuery: (query: string) => void
  setViewState: Dispatch<SetStateAction<ViewState>>
  bumpRestoreGridToSelectionToken: () => void
  scopePath: string
  sessionResetToken: number
}

type UseSimilaritySearchWorkflowResult = {
  cancelPendingSimilaritySearch: () => void
  clearSimilarity: () => void
  handleRevealOffView: () => void
  handleSimilaritySearch: (payload: EmbeddingSearchRequest) => Promise<boolean>
}

export function similarityOwnerKey(scopePath: string, sessionResetToken: number): string {
  return `${sanitizePath(scopePath)}\u0000${sessionResetToken}`
}

export function isCurrentSimilarityRequest(
  requestOwnerKey: string,
  requestId: number,
  activeOwnerKey: string,
  latestRequestId: number,
): boolean {
  return requestOwnerKey === activeOwnerKey && requestId === latestRequestId
}

export function useSimilaritySearchWorkflow({
  similarityState,
  setSimilarityState,
  selectedPaths,
  setSelectedPaths,
  setQuery,
  setViewState,
  bumpRestoreGridToSelectionToken,
  scopePath,
  sessionResetToken,
}: UseSimilaritySearchWorkflowParams): UseSimilaritySearchWorkflowResult {
  const similarityPrevSelectionRef = useRef<string[] | null>(null)
  const activeOwnerKey = similarityOwnerKey(scopePath, sessionResetToken)
  const latestOwnerKeyRef = useRef(activeOwnerKey)
  const latestRequestIdRef = useRef(0)
  useLayoutEffect(() => {
    if (latestOwnerKeyRef.current === activeOwnerKey) return
    latestOwnerKeyRef.current = activeOwnerKey
    latestRequestIdRef.current += 1
    similarityPrevSelectionRef.current = null
  }, [activeOwnerKey])

  const cancelPendingSimilaritySearch = useCallback(() => {
    latestRequestIdRef.current += 1
  }, [])

  const clearSimilarity = useCallback(() => {
    latestRequestIdRef.current += 1
    setSimilarityState(null)
    const prevSelection = similarityPrevSelectionRef.current
    similarityPrevSelectionRef.current = null
    if (prevSelection && prevSelection.length) {
      setSelectedPaths(prevSelection)
      bumpRestoreGridToSelectionToken()
    } else {
      setSelectedPaths([])
    }
  }, [bumpRestoreGridToSelectionToken, setSelectedPaths, setSimilarityState])

  const handleRevealOffView = useCallback(() => {
    if (similarityState) {
      clearSimilarity()
    }
    setQuery('')
    setViewState((prev) => ({ ...prev, filters: { and: [] } }))
  }, [clearSimilarity, setQuery, setViewState, similarityState])

  const handleSimilaritySearch = useCallback(async (payload: EmbeddingSearchRequest) => {
    const selectionBeforeRequest = !similarityState && similarityPrevSelectionRef.current === null
      ? [...selectedPaths]
      : null
    const requestId = latestRequestIdRef.current + 1
    latestRequestIdRef.current = requestId
    const requestOwnerKey = activeOwnerKey
    const res = await api.searchEmbeddings(payload)
    if (!isCurrentSimilarityRequest(
      requestOwnerKey,
      requestId,
      latestOwnerKeyRef.current,
      latestRequestIdRef.current,
    )) return false
    if (selectionBeforeRequest !== null && similarityPrevSelectionRef.current === null) {
      similarityPrevSelectionRef.current = selectionBeforeRequest
    }
    const queryPath = payload.query.kind === 'path' ? payload.query.path : null
    const queryVector = payload.query.kind === 'vector' ? payload.query.vector_b64 : null
    setSimilarityState({
      scopePath: sanitizePath(scopePath),
      sessionResetToken,
      embedding: res.embedding,
      queryPath,
      queryVector,
      topK: payload.top_k ?? 50,
      minScore: payload.min_score ?? null,
      items: res.items,
      createdAt: Date.now(),
    })
    if (res.items.length) {
      const preferred = queryPath && res.items.some((item) => item.path === queryPath)
        ? queryPath
        : res.items[0].path
      setSelectedPaths([preferred])
      bumpRestoreGridToSelectionToken()
    } else {
      setSelectedPaths([])
    }
    return true
  }, [
    bumpRestoreGridToSelectionToken,
    activeOwnerKey,
    selectedPaths,
    scopePath,
    sessionResetToken,
    setSelectedPaths,
    setSimilarityState,
    similarityState,
  ])

  return {
    cancelPendingSimilaritySearch,
    clearSimilarity,
    handleRevealOffView,
    handleSimilaritySearch,
  }
}
