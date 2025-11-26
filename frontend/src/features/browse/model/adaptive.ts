import type { Item } from '../../../lib/types'

export type AdaptiveRow = {
  index: number
  height: number // Total row height including caption/gap
  imageH: number // Just the image height
  items: { 
    item: Item
    displayW: number
    displayH: number
    originalIndex: number 
  }[]
}

export function computeAdaptiveRows({
  items,
  containerWidth,
  targetHeight,
  gap,
  captionH
}: {
  items: Item[]
  containerWidth: number
  targetHeight: number
  gap: number
  captionH: number
}): AdaptiveRow[] {
  if (containerWidth <= 0) return []

  const rows: AdaptiveRow[] = []
  let currentRowItems: { item: Item; aspect: number; originalIndex: number }[] = []
  let currentAspectSum = 0

  for (let i = 0; i < items.length; i++) {
    const item = items[i]
    
    // Fix: Handle missing dimensions (0x0) by defaulting to 4:3
    let aspect = 1.333 
    if (item.w > 0 && item.h > 0) {
        aspect = item.w / item.h
    }
    
    currentRowItems.push({ item, aspect, originalIndex: i })
    currentAspectSum += aspect
    
    // Width needed if we use targetHeight: sum(w) + (n-1)*gap
    // w = aspect * h
    const totalGap = (currentRowItems.length - 1) * gap
    const widthAtTarget = currentAspectSum * targetHeight + totalGap
    
    if (widthAtTarget >= containerWidth) {
        // We found a breakpoint. Calculate exact height to fit containerWidth.
        // containerWidth = h * sum(aspect) + totalGap
        // h = (containerWidth - totalGap) / sum(aspect)
        const h = (containerWidth - totalGap) / currentAspectSum
        
        // Only accept if it's not ridiculously small (e.g. < 50% of target)
        // If it is, we might have added one too many items.
        // But usually "justified" means we accept it. 
        // To avoid tiny rows, we could peek ahead, but simple greedy approach works well for typical aspect ratios.
        
        const rowItems = currentRowItems.map(it => ({
          item: it.item,
          displayW: it.aspect * h,
          displayH: h,
          originalIndex: it.originalIndex
        }))
        
        rows.push({
          index: rows.length,
          height: h + captionH + gap,
          imageH: h,
          items: rowItems
        })
        
        currentRowItems = []
        currentAspectSum = 0
    }
  }
  
  // Last row
  if (currentRowItems.length > 0) {
      // Left align, keep target height
      const h = targetHeight
      const rowItems = currentRowItems.map(it => ({
          item: it.item,
          displayW: it.aspect * h,
          displayH: h,
          originalIndex: it.originalIndex
      }))
      rows.push({
          index: rows.length,
          height: h + captionH + gap,
          imageH: h,
          items: rowItems
      })
  }
  
  return rows
}
