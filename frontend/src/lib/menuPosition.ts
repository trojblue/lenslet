export const MENU_VIEWPORT_MARGIN_PX = 8
export const MENU_SIDE_OFFSET_PX = 6

export type MenuAlign = 'left' | 'right'

export interface ViewportSize {
  width: number
  height: number
}

export interface MenuSize {
  width: number
  height: number
}

export interface AnchorRectLike {
  left: number
  top: number
  right: number
  bottom: number
}

interface ClampMenuPositionInput {
  x: number
  y: number
  menuWidth: number
  menuHeight: number
  viewport: ViewportSize
  margin?: number
}

interface DropdownPanelPositionInput {
  anchorRect: AnchorRectLike
  menuSize: MenuSize
  viewport: ViewportSize
  align?: MenuAlign
  margin?: number
  sideOffset?: number
}

function clamp(value: number, min: number, max: number): number {
  if (max < min) return min
  return Math.min(max, Math.max(min, value))
}

export function clampMenuPosition({
  x,
  y,
  menuWidth,
  menuHeight,
  viewport,
  margin = MENU_VIEWPORT_MARGIN_PX,
}: ClampMenuPositionInput): { x: number; y: number } {
  const minX = margin
  const minY = margin
  const maxX = viewport.width - Math.max(0, menuWidth) - margin
  const maxY = viewport.height - Math.max(0, menuHeight) - margin
  return {
    x: clamp(x, minX, maxX),
    y: clamp(y, minY, maxY),
  }
}

export function getDropdownPanelPosition({
  anchorRect,
  menuSize,
  viewport,
  align = 'left',
  margin = MENU_VIEWPORT_MARGIN_PX,
  sideOffset = MENU_SIDE_OFFSET_PX,
}: DropdownPanelPositionInput): { x: number; y: number } {
  const desiredX = align === 'right'
    ? anchorRect.right - menuSize.width
    : anchorRect.left

  const belowY = anchorRect.bottom + sideOffset
  const aboveY = anchorRect.top - menuSize.height - sideOffset
  const canFitBelow = belowY + menuSize.height + margin <= viewport.height
  const canFitAbove = aboveY >= margin
  const desiredY = !canFitBelow && canFitAbove ? aboveY : belowY

  return clampMenuPosition({
    x: desiredX,
    y: desiredY,
    menuWidth: menuSize.width,
    menuHeight: menuSize.height,
    viewport,
    margin,
  })
}

export function getViewportSize(): ViewportSize {
  if (typeof window === 'undefined') {
    return { width: 1024, height: 768 }
  }
  return { width: window.innerWidth, height: window.innerHeight }
}
