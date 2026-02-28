import { describe, expect, it } from 'vitest'
import {
  buildBoardState,
  finalRanksFromBoard,
  isBoardComplete,
  moveImageToRank,
  moveImageToRankWithAutoAdvance,
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

  it('supports insertion index when moving between containers', () => {
    const board = buildBoardState(['a', 'b', 'c', 'd'], 4, [['c'], ['d']])
    const moved = moveImageToRank(board, 'b', 0, 0)
    const unrankedMoved = moveImageToRank(moved, 'c', null, 1)

    expect(moved.rankColumns[0]).toEqual(['b', 'c'])
    expect(unrankedMoved.unranked).toEqual(['a', 'c'])
  })

  it('reorders inside the same rank column using target insertion index', () => {
    const board = buildBoardState(['a', 'b', 'c', 'd'], 4, [['a', 'b', 'c']])
    const movedToTail = moveImageToRank(board, 'a', 0, 2)
    const movedToHead = moveImageToRank(movedToTail, 'c', 0, 0)

    expect(movedToTail.rankColumns[0]).toEqual(['b', 'c', 'a'])
    expect(movedToHead.rankColumns[0]).toEqual(['c', 'b', 'a'])
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

  it('auto-advances to the next unranked image in initial order', () => {
    const board = buildBoardState(
      ['a', 'b', 'c', 'd'],
      3,
      [['b']],
    )
    const withSelection = {
      ...board,
      selectedImageId: 'c',
    }

    const next = moveImageToRankWithAutoAdvance(
      withSelection,
      'c',
      0,
      ['a', 'b', 'c', 'd'],
    )

    expect(next.rankColumns[0]).toEqual(['b', 'c'])
    expect(next.unranked).toEqual(['a', 'd'])
    expect(next.selectedImageId).toBe('d')
  })

  it('wraps auto-advance when unranked items remain earlier in initial order', () => {
    const board = buildBoardState(['a', 'b', 'c'], 3, null)
    const withSelection = {
      ...board,
      selectedImageId: 'c',
    }

    const next = moveImageToRankWithAutoAdvance(
      withSelection,
      'c',
      1,
      ['a', 'b', 'c'],
    )

    expect(next.unranked).toEqual(['a', 'b'])
    expect(next.selectedImageId).toBe('a')
  })

  it('keeps selection on rerank and unrank operations', () => {
    const board = buildBoardState(['a', 'b', 'c'], 3, [['b']])
    const reranked = moveImageToRankWithAutoAdvance(
      board,
      'b',
      2,
      ['a', 'b', 'c'],
    )
    const unranked = moveImageToRankWithAutoAdvance(
      reranked,
      'b',
      null,
      ['a', 'b', 'c'],
    )

    expect(reranked.selectedImageId).toBe('b')
    expect(unranked.selectedImageId).toBe('b')
    expect(unranked.unranked).toEqual(['a', 'c', 'b'])
  })

  it('falls back to remaining unranked order for hydrated edge cases', () => {
    const hydrated = buildBoardState(
      ['a', 'b', 'c', 'd'],
      3,
      [['a'], ['c']],
    )

    const next = moveImageToRankWithAutoAdvance(
      hydrated,
      'b',
      0,
      ['a', 'b', 'c'],
    )

    expect(next.unranked).toEqual(['d'])
    expect(next.selectedImageId).toBe('d')
  })
})
