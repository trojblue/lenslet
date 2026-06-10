import { useCallback, useRef, type Dispatch, type SetStateAction } from 'react'
import { api } from '../../api/client'
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
}

type UseSimilaritySearchWorkflowResult = {
  clearSimilarity: () => void
  handleRevealOffView: () => void
  handleSimilaritySearch: (payload: EmbeddingSearchRequest) => Promise<void>
}

export function useSimilaritySearchWorkflow({
  similarityState,
  setSimilarityState,
  selectedPaths,
  setSelectedPaths,
  setQuery,
  setViewState,
  bumpRestoreGridToSelectionToken,
}: UseSimilaritySearchWorkflowParams): UseSimilaritySearchWorkflowResult {
  const similarityPrevSelectionRef = useRef<string[] | null>(null)

  const clearSimilarity = useCallback(() => {
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
    if (!similarityState && similarityPrevSelectionRef.current === null) {
      similarityPrevSelectionRef.current = selectedPaths
    }
    const res = await api.searchEmbeddings(payload)
    const queryPath = payload.query.kind === 'path' ? payload.query.path : null
    const queryVector = payload.query.kind === 'vector' ? payload.query.vector_b64 : null
    setSimilarityState({
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
  }, [
    bumpRestoreGridToSelectionToken,
    selectedPaths,
    setSelectedPaths,
    setSimilarityState,
    similarityState,
  ])

  return {
    clearSimilarity,
    handleRevealOffView,
    handleSimilaritySearch,
  }
}
