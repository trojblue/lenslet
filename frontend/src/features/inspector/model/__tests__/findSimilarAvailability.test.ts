import { describe, expect, it } from 'vitest'
import {
  FIND_SIMILAR_LOADING_EMBEDDINGS_REASON,
  FIND_SIMILAR_NO_EMBEDDINGS_REASON,
  FIND_SIMILAR_SELECT_SINGLE_REASON,
  resolveFindSimilarAvailability,
} from '../findSimilarAvailability'

describe('resolveFindSimilarAvailability', () => {
  it('returns disabled with no reason when the action is unavailable', () => {
    expect(resolveFindSimilarAvailability({
      enabled: false,
      embeddingsAvailable: true,
      embeddingsLoading: false,
      selectedCount: 1,
    })).toEqual({
      canFindSimilar: false,
      disabledReason: null,
    })
  })

  it('returns loading and no-embeddings reasons before enabling', () => {
    expect(resolveFindSimilarAvailability({
      enabled: true,
      embeddingsAvailable: false,
      embeddingsLoading: true,
      selectedCount: 1,
    })).toEqual({
      canFindSimilar: false,
      disabledReason: FIND_SIMILAR_LOADING_EMBEDDINGS_REASON,
    })

    expect(resolveFindSimilarAvailability({
      enabled: true,
      embeddingsAvailable: false,
      embeddingsLoading: false,
      selectedCount: 1,
    })).toEqual({
      canFindSimilar: false,
      disabledReason: FIND_SIMILAR_NO_EMBEDDINGS_REASON,
    })
  })

  it('requires a single selected item once embeddings are ready', () => {
    expect(resolveFindSimilarAvailability({
      enabled: true,
      embeddingsAvailable: true,
      embeddingsLoading: false,
      selectedCount: 2,
    })).toEqual({
      canFindSimilar: false,
      disabledReason: FIND_SIMILAR_SELECT_SINGLE_REASON,
    })

    expect(resolveFindSimilarAvailability({
      enabled: true,
      embeddingsAvailable: true,
      embeddingsLoading: false,
      selectedCount: 1,
    })).toEqual({
      canFindSimilar: true,
      disabledReason: null,
    })
  })
})
