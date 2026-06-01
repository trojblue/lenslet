import type { RankingBoardState } from './board'

export type RankingContainerId = 'unranked' | `rank-${number}`

export const UNRANKED_CONTAINER_ID: RankingContainerId = 'unranked'

export function rankContainerId(rankIndex: number): RankingContainerId {
  return `rank-${rankIndex}`
}

export function parseContainerId(rawId: string, rankCount: number): RankingContainerId | null {
  if (rawId === UNRANKED_CONTAINER_ID) return UNRANKED_CONTAINER_ID
  if (!rawId.startsWith('rank-')) return null
  const rankIndex = Number(rawId.slice('rank-'.length))
  if (!Number.isInteger(rankIndex) || rankIndex < 0 || rankIndex >= rankCount) return null
  return rankContainerId(rankIndex)
}

export function rankIndexForContainerId(containerId: RankingContainerId): number | null {
  if (containerId === UNRANKED_CONTAINER_ID) return null
  return Number(containerId.slice('rank-'.length))
}

export function findContainerForImage(
  board: RankingBoardState,
  imageId: string,
): RankingContainerId | null {
  if (board.unranked.includes(imageId)) return UNRANKED_CONTAINER_ID
  for (let rankIndex = 0; rankIndex < board.rankColumns.length; rankIndex += 1) {
    if (board.rankColumns[rankIndex].includes(imageId)) {
      return rankContainerId(rankIndex)
    }
  }
  return null
}

export function itemsForContainer(
  board: RankingBoardState,
  containerId: RankingContainerId,
): string[] {
  if (containerId === UNRANKED_CONTAINER_ID) {
    return board.unranked
  }
  const rankIndex = rankIndexForContainerId(containerId)
  if (rankIndex == null) return []
  return board.rankColumns[rankIndex] ?? []
}
