export type LayoutResult = { columns: number; cellW: number; mediaH: number; rowH: number }

type LayoutOptions = {
  containerW: number
  gap: number
  targetCell: number
  aspect: { w: number; h: number }
  captionH: number
}

export type Layout = (opts: LayoutOptions) => LayoutResult

export const flatLayout: Layout = ({ containerW, gap, targetCell, aspect, captionH }) => {
  const columns = Math.max(1, Math.floor((containerW + gap) / (targetCell + gap)))
  const cellW = (containerW - gap * (columns - 1)) / columns
  const mediaH = (cellW * aspect.h) / aspect.w
  const rowH = mediaH + captionH + gap
  return { columns, cellW, mediaH, rowH }
}

