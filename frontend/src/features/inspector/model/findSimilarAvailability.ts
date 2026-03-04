export type ResolveFindSimilarAvailabilityParams = {
  enabled: boolean
  embeddingsAvailable: boolean
  embeddingsLoading: boolean
  selectedCount: number
}

export type FindSimilarAvailability = {
  canFindSimilar: boolean
  disabledReason: string | null
}

export const FIND_SIMILAR_SELECT_SINGLE_REASON = 'Select a single image to search.'
export const FIND_SIMILAR_NO_EMBEDDINGS_REASON = 'No embeddings detected.'
export const FIND_SIMILAR_LOADING_EMBEDDINGS_REASON = 'Loading embeddings...'

export function resolveFindSimilarAvailability({
  enabled,
  embeddingsAvailable,
  embeddingsLoading,
  selectedCount,
}: ResolveFindSimilarAvailabilityParams): FindSimilarAvailability {
  if (!enabled) {
    return {
      canFindSimilar: false,
      disabledReason: null,
    }
  }
  if (!embeddingsAvailable) {
    return {
      canFindSimilar: false,
      disabledReason: embeddingsLoading
        ? FIND_SIMILAR_LOADING_EMBEDDINGS_REASON
        : FIND_SIMILAR_NO_EMBEDDINGS_REASON,
    }
  }
  if (selectedCount !== 1) {
    return {
      canFindSimilar: false,
      disabledReason: FIND_SIMILAR_SELECT_SINGLE_REASON,
    }
  }
  return {
    canFindSimilar: true,
    disabledReason: null,
  }
}
