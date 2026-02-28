export type RankingBoardState = {
  unranked: string[]
  rankColumns: string[][]
  selectedImageId: string | null
}

function uniqueIds(values: string[]): string[] {
  const seen = new Set<string>()
  const output: string[] = []
  for (const value of values) {
    if (seen.has(value)) continue
    seen.add(value)
    output.push(value)
  }
  return output
}

function cloneRankColumns(rankColumns: string[][]): string[][] {
  return rankColumns.map((column) => [...column])
}

function compactRankColumns(rankColumns: string[][]): string[][] {
  const nonEmpty = rankColumns.filter((column) => column.length > 0)
  const compacted = nonEmpty.map((column) => [...column])
  while (compacted.length < rankColumns.length) {
    compacted.push([])
  }
  return compacted
}

function clampRankIndex(rankIndex: number, maxRanks: number): number {
  if (maxRanks <= 0) return 0
  if (rankIndex < 0) return 0
  if (rankIndex >= maxRanks) return maxRanks - 1
  return rankIndex
}

function clampInsertIndex(index: number | undefined, length: number): number {
  if (index == null || Number.isNaN(index)) return length
  if (index < 0) return 0
  if (index > length) return length
  return index
}

export function buildBoardState(
  imageIds: string[],
  maxRanks: number,
  savedFinalRanks: string[][] | null | undefined,
): RankingBoardState {
  const canonical = uniqueIds(imageIds)
  const allowed = new Set(canonical)
  const rankColumns: string[][] = Array.from({ length: Math.max(1, maxRanks) }, () => [])
  const assigned = new Set<string>()

  if (Array.isArray(savedFinalRanks)) {
    for (let rankIdx = 0; rankIdx < savedFinalRanks.length; rankIdx += 1) {
      if (rankIdx >= rankColumns.length) break
      const group = savedFinalRanks[rankIdx]
      if (!Array.isArray(group)) continue
      for (const rawId of group) {
        if (typeof rawId !== 'string') continue
        if (!allowed.has(rawId) || assigned.has(rawId)) continue
        rankColumns[rankIdx].push(rawId)
        assigned.add(rawId)
      }
    }
  }

  const unranked = canonical.filter((imageId) => !assigned.has(imageId))
  return {
    unranked,
    rankColumns,
    selectedImageId: canonical[0] ?? null,
  }
}

export function moveImageToRank(
  board: RankingBoardState,
  imageId: string,
  targetRankIndex: number | null,
  targetInsertIndex?: number,
): RankingBoardState {
  const hasImage = board.unranked.includes(imageId) ||
    board.rankColumns.some((column) => column.includes(imageId))
  if (!hasImage) return board

  const unranked = board.unranked.filter((id) => id !== imageId)
  const nextColumns = cloneRankColumns(board.rankColumns).map((column) =>
    column.filter((id) => id !== imageId),
  )
  if (targetRankIndex == null) {
    const insertIndex = clampInsertIndex(targetInsertIndex, unranked.length)
    unranked.splice(insertIndex, 0, imageId)
  } else {
    const column = nextColumns[clampRankIndex(targetRankIndex, nextColumns.length)]
    const insertIndex = clampInsertIndex(targetInsertIndex, column.length)
    column.splice(insertIndex, 0, imageId)
  }
  const rankColumns = compactRankColumns(nextColumns)
  return {
    unranked,
    rankColumns,
    selectedImageId: imageId,
  }
}

function nextUnrankedFromInitialOrder(
  imageId: string,
  unranked: string[],
  initialOrder: string[],
): string | null {
  if (unranked.length === 0) return null
  const unrankedSet = new Set(unranked)
  const canonicalOrder = uniqueIds(initialOrder)
  if (canonicalOrder.length === 0) {
    return unranked[0] ?? null
  }

  const currentIndex = canonicalOrder.indexOf(imageId)
  const startIndex = currentIndex >= 0 ? currentIndex + 1 : 0
  for (let idx = startIndex; idx < canonicalOrder.length; idx += 1) {
    const candidate = canonicalOrder[idx]
    if (unrankedSet.has(candidate)) {
      return candidate
    }
  }
  for (let idx = 0; idx < startIndex; idx += 1) {
    const candidate = canonicalOrder[idx]
    if (unrankedSet.has(candidate)) {
      return candidate
    }
  }
  return unranked[0] ?? null
}

export function moveImageToRankWithAutoAdvance(
  board: RankingBoardState,
  imageId: string,
  targetRankIndex: number | null,
  initialOrder: string[],
): RankingBoardState {
  const wasUnranked = board.unranked.includes(imageId)
  const nextBoard = moveImageToRank(board, imageId, targetRankIndex)
  if (nextBoard === board) return board
  if (!wasUnranked || targetRankIndex == null) return nextBoard

  const nextUnranked = nextUnrankedFromInitialOrder(
    imageId,
    nextBoard.unranked,
    initialOrder,
  )
  return {
    ...nextBoard,
    selectedImageId: nextUnranked ?? imageId,
  }
}

export function finalRanksFromBoard(board: RankingBoardState): string[][] {
  return board.rankColumns.filter((column) => column.length > 0).map((column) => [...column])
}

export function isBoardComplete(board: RankingBoardState): boolean {
  return board.unranked.length === 0
}

export function orderedImageIds(board: RankingBoardState): string[] {
  const ordered: string[] = [...board.unranked]
  for (const column of board.rankColumns) {
    ordered.push(...column)
  }
  return ordered
}

export function selectNeighborImage(
  board: RankingBoardState,
  direction: 'left' | 'right',
): string | null {
  const ordered = orderedImageIds(board)
  if (ordered.length === 0) return null
  if (!board.selectedImageId) return ordered[0]
  const currentIndex = ordered.indexOf(board.selectedImageId)
  if (currentIndex < 0) return ordered[0]
  if (direction === 'left') {
    const prevIndex = currentIndex - 1
    return ordered[prevIndex] ?? ordered[0]
  }
  const nextIndex = currentIndex + 1
  return ordered[nextIndex] ?? ordered[ordered.length - 1]
}
