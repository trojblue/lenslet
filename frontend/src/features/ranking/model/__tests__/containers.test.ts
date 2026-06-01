import { describe, expect, it } from 'vitest'
import { buildBoardState } from '../board'
import {
  findContainerForImage,
  itemsForContainer,
  parseContainerId,
  rankContainerId,
  rankIndexForContainerId,
  UNRANKED_CONTAINER_ID,
} from '../containers'

describe('ranking drag container helpers', () => {
  it('parses only valid ranking container ids', () => {
    expect(parseContainerId(UNRANKED_CONTAINER_ID, 3)).toBe(UNRANKED_CONTAINER_ID)
    expect(parseContainerId('rank-0', 3)).toBe(rankContainerId(0))
    expect(parseContainerId('rank-2', 3)).toBe(rankContainerId(2))
    expect(parseContainerId('rank-3', 3)).toBeNull()
    expect(parseContainerId('rank--1', 3)).toBeNull()
    expect(parseContainerId('image-a', 3)).toBeNull()
  })

  it('maps image ids and container ids back to board items', () => {
    const board = buildBoardState(
      ['a', 'b', 'c', 'd'],
      3,
      [['b'], ['d']],
    )

    expect(findContainerForImage(board, 'a')).toBe(UNRANKED_CONTAINER_ID)
    expect(findContainerForImage(board, 'b')).toBe(rankContainerId(0))
    expect(findContainerForImage(board, 'd')).toBe(rankContainerId(1))
    expect(findContainerForImage(board, 'z')).toBeNull()
    expect(itemsForContainer(board, UNRANKED_CONTAINER_ID)).toEqual(['a', 'c'])
    expect(itemsForContainer(board, rankContainerId(1))).toEqual(['d'])
    expect(rankIndexForContainerId(UNRANKED_CONTAINER_ID)).toBeNull()
    expect(rankIndexForContainerId(rankContainerId(2))).toBe(2)
  })
})
