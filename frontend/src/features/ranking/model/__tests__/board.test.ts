import { describe, expect, it } from 'vitest'
import {
  buildBoardState,
  finalRanksFromBoard,
  isBoardComplete,
  moveImageToRank,
  orderedImageIds,
  selectNeighborImage,
} from '../board'

describe('ranking board state contracts', () => {
  it('hydrates saved rank groups and preserves unranked originals', () => {
    const board = buildBoardState(
      ['a', 'b', 'c', 'd'],
      4,
      [
        ['c'],
        ['b', 'd'],
      ],
    )

    expect(board.rankColumns[0]).toEqual(['c'])
    expect(board.rankColumns[1]).toEqual(['b', 'd'])
    expect(board.unranked).toEqual(['a'])
    expect(board.selectedImageId).toBe('a')
  })

  it('moves cards between unranked and ranked columns', () => {
    const initial = buildBoardState(['a', 'b', 'c'], 3, null)
    const ranked = moveImageToRank(initial, 'b', 0)
    const movedBack = moveImageToRank(ranked, 'b', null)

    expect(ranked.rankColumns[0]).toEqual(['b'])
    expect(ranked.unranked).toEqual(['a', 'c'])
    expect(movedBack.rankColumns[0]).toEqual([])
    expect(movedBack.unranked).toEqual(['a', 'c', 'b'])
    expect(movedBack.selectedImageId).toBe('b')
  })

  it('serializes final ranks and completion state', () => {
    const board = buildBoardState(['a', 'b'], 2, null)
    const first = moveImageToRank(board, 'a', 0)
    const second = moveImageToRank(first, 'b', 1)

    expect(isBoardComplete(first)).toBe(false)
    expect(isBoardComplete(second)).toBe(true)
    expect(finalRanksFromBoard(second)).toEqual([['a'], ['b']])
  })

  it('compacts sparse rank moves to preserve contiguous ordering', () => {
    const board = buildBoardState(['a', 'b', 'c'], 3, null)
    const sparseMove = moveImageToRank(board, 'a', 2)

    expect(sparseMove.rankColumns).toEqual([['a'], [], []])
    expect(finalRanksFromBoard(sparseMove)).toEqual([['a']])
  })

  it('moves keyboard selection in display order', () => {
    const board = buildBoardState(['a', 'b', 'c'], 3, null)
    const ranked = moveImageToRank(board, 'b', 0)
    const withSelection = { ...ranked, selectedImageId: 'a' }

    expect(orderedImageIds(withSelection)).toEqual(['a', 'c', 'b'])
    expect(selectNeighborImage(withSelection, 'right')).toBe('c')
    expect(selectNeighborImage(withSelection, 'left')).toBe('a')
  })

  it('ignores moves for unknown image ids', () => {
    const board = buildBoardState(['a', 'b'], 2, null)
    const next = moveImageToRank(board, 'z', 0)
    expect(next).toBe(board)
  })
})
