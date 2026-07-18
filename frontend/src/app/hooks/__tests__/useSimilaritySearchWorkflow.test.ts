import { describe, expect, it } from 'vitest'
import {
  isCurrentSimilarityRequest,
  similarityOwnerKey,
} from '../useSimilaritySearchWorkflow'

describe('similarity search ownership', () => {
  it('normalizes scope and changes identity across session resets', () => {
    expect(similarityOwnerKey('/scope-a/', 2)).toBe(similarityOwnerKey('/scope-a', 2))
    expect(similarityOwnerKey('/scope-a', 3)).not.toBe(similarityOwnerKey('/scope-a', 2))
  })

  it('accepts only the latest request from the active owner', () => {
    const owner = similarityOwnerKey('/scope-a', 2)

    expect(isCurrentSimilarityRequest(owner, 4, owner, 4)).toBe(true)
    expect(isCurrentSimilarityRequest(owner, 3, owner, 4)).toBe(false)
    expect(isCurrentSimilarityRequest(
      owner,
      4,
      similarityOwnerKey('/scope-b', 2),
      4,
    )).toBe(false)
  })
})
