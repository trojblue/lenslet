import type { BrowseItemPayload } from '../../../lib/types'

export type AdaptiveRow = {
  index: number
  height: number // Total row height including caption/gap
  imageH: number // Just the image height
  items: {
    item: BrowseItemPayload
    displayW: number
    displayH: number
    fit?: 'contain'
    originalIndex: number
  }[]
}

type RowItem = { item: BrowseItemPayload; aspect: number; originalIndex: number }

const DEFAULT_ASPECT = 1.333
const MIN_ROW_HEIGHT_FACTOR = 0.65
const MAX_ROW_HEIGHT_FACTOR = 1.35
const TALL_OUTLIER_ASPECT = 0.25

export function computeAdaptiveRows({
  items,
  containerWidth,
  targetHeight,
  gap,
  captionH,
}: {
  items: BrowseItemPayload[]
  containerWidth: number
  targetHeight: number
  gap: number
  captionH: number
}): AdaptiveRow[] {
  if (containerWidth <= 0) return []

  const rows: AdaptiveRow[] = []
  const minImageHeight = Math.max(1, targetHeight * MIN_ROW_HEIGHT_FACTOR)
  const maxImageHeight = Math.max(minImageHeight, targetHeight * MAX_ROW_HEIGHT_FACTOR)
  let currentRowItems: RowItem[] = []

  const buildRow = (rowItems: RowItem[], height: number): AdaptiveRow => ({
    index: rows.length,
    height: height + captionH + gap,
    imageH: height,
    items: rowItems.map((rowItem) => ({
      item: rowItem.item,
      displayW: rowItem.aspect * height,
      displayH: height,
      originalIndex: rowItem.originalIndex,
    })),
  })

  const pushScaledRow = (rowItems: RowItem[], height: number) => {
    rows.push(buildRow(rowItems, height))
  }

  const pushContainedRow = (rowItem: RowItem) => {
    const height = Math.min(maxImageHeight, Math.max(minImageHeight, targetHeight))
    rows.push({
      index: rows.length,
      height: height + captionH + gap,
      imageH: height,
      items: [{
        item: rowItem.item,
        displayW: containerWidth,
        displayH: height,
        fit: 'contain',
        originalIndex: rowItem.originalIndex,
      }],
    })
  }

  const getAspectSum = (rowItems: RowItem[]) => (
    rowItems.reduce((sum, rowItem) => sum + rowItem.aspect, 0)
  )

  const getTotalGap = (rowItems: RowItem[]) => Math.max(0, rowItems.length - 1) * gap

  const getWidthAtHeight = (rowItems: RowItem[], height: number) => (
    getAspectSum(rowItems) * height + getTotalGap(rowItems)
  )

  const getJustifiedHeight = (rowItems: RowItem[]) => {
    const availableWidth = Math.max(1, containerWidth - getTotalGap(rowItems))
    return availableWidth / getAspectSum(rowItems)
  }

  const getTrailingHeight = (rowItems: RowItem[]) => {
    if (getWidthAtHeight(rowItems, targetHeight) <= containerWidth) {
      return targetHeight
    }
    return getJustifiedHeight(rowItems)
  }

  const shouldContainSingleItem = (rowItem: RowItem) => (
    rowItem.aspect <= TALL_OUTLIER_ASPECT || rowItem.aspect * minImageHeight > containerWidth
  )

  const pushTrailingRows = (rowItems: RowItem[]) => {
    let pending: RowItem[] = []
    for (const rowItem of rowItems) {
      const candidate = [...pending, rowItem]
      if (getWidthAtHeight(candidate, targetHeight) <= containerWidth) {
        pending = candidate
        continue
      }

      if (pending.length > 0) {
        pushScaledRow(pending, getTrailingHeight(pending))
        pending = [rowItem]
        continue
      }

      const fitHeight = getJustifiedHeight(candidate)
      if (fitHeight >= minImageHeight) {
        pushScaledRow(candidate, fitHeight)
      } else {
        pushContainedRow(rowItem)
      }
      pending = []
    }

    if (pending.length > 0) {
      pushScaledRow(pending, getTrailingHeight(pending))
    }
  }

  for (let i = 0; i < items.length; i++) {
    const item = items[i]

    const aspect = item.width > 0 && item.height > 0 ? item.width / item.height : DEFAULT_ASPECT
    const rowItem = { item, aspect, originalIndex: i }

    if (shouldContainSingleItem(rowItem)) {
      pushTrailingRows(currentRowItems)
      currentRowItems = []
      pushContainedRow(rowItem)
      continue
    }

    if (currentRowItems.length === 0) {
      currentRowItems = [rowItem]
      continue
    }

    const candidate = [...currentRowItems, rowItem]
    const candidateHeight = getJustifiedHeight(candidate)
    if (candidateHeight > targetHeight) {
      currentRowItems = candidate
      continue
    }

    const currentHeight = getJustifiedHeight(currentRowItems)
    const candidateValid = candidateHeight >= minImageHeight
    const currentValid = currentHeight <= maxImageHeight
    const candidateError = Math.abs(candidateHeight - targetHeight)
    const currentError = Math.abs(currentHeight - targetHeight)

    if (candidateValid && (!currentValid || candidateError <= currentError)) {
      pushScaledRow(candidate, candidateHeight)
      currentRowItems = []
    } else if (currentValid) {
      pushScaledRow(currentRowItems, currentHeight)
      currentRowItems = [rowItem]
    } else if (candidateValid) {
      pushScaledRow(candidate, candidateHeight)
      currentRowItems = []
    } else {
      pushScaledRow(currentRowItems, Math.min(maxImageHeight, currentHeight))
      currentRowItems = [rowItem]
    }
  }

  if (currentRowItems.length > 0) {
    pushTrailingRows(currentRowItems)
  }

  return rows
}
