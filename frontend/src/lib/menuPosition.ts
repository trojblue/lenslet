export const MENU_VIEWPORT_MARGIN_PX = 8
export const MENU_SIDE_OFFSET_PX = 6

export type MenuAlign = 'left' | 'right'

export interface ViewportSize {
  width: number
  height: number
}

export interface ViewportBounds extends ViewportSize {
  left: number
  top: number
  right: number
  bottom: number
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
  viewport: ViewportSize | ViewportBounds
  margin?: number
}

interface DropdownPanelPositionInput {
  anchorRect: AnchorRectLike
  menuSize: MenuSize
  viewport: ViewportSize | ViewportBounds
  align?: MenuAlign
  margin?: number
  sideOffset?: number
}

function clamp(value: number, min: number, max: number): number {
  if (max < min) return min
  return Math.min(max, Math.max(min, value))
}

function finiteOr(value: number | undefined, fallback: number): number {
  return typeof value === 'number' && Number.isFinite(value) ? value : fallback
}

export function toViewportBounds(viewport: ViewportSize | ViewportBounds): ViewportBounds {
  const left = 'left' in viewport ? finiteOr(viewport.left, 0) : 0
  const top = 'top' in viewport ? finiteOr(viewport.top, 0) : 0
  const width = Math.max(0, finiteOr(viewport.width, 0))
  const height = Math.max(0, finiteOr(viewport.height, 0))
  return {
    left,
    top,
    width,
    height,
    right: 'right' in viewport ? finiteOr(viewport.right, left + width) : left + width,
    bottom: 'bottom' in viewport ? finiteOr(viewport.bottom, top + height) : top + height,
  }
}

export function clampMenuPosition({
  x,
  y,
  menuWidth,
  menuHeight,
  viewport,
  margin = MENU_VIEWPORT_MARGIN_PX,
}: ClampMenuPositionInput): { x: number; y: number } {
  const bounds = toViewportBounds(viewport)
  const minX = bounds.left + margin
  const minY = bounds.top + margin
  const maxX = bounds.right - Math.max(0, menuWidth) - margin
  const maxY = bounds.bottom - Math.max(0, menuHeight) - margin
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
  const bounds = toViewportBounds(viewport)
  const desiredX = align === 'right'
    ? anchorRect.right - menuSize.width
    : anchorRect.left

  const belowY = anchorRect.bottom + sideOffset
  const aboveY = anchorRect.top - menuSize.height - sideOffset
  const canFitBelow = belowY + menuSize.height + margin <= bounds.bottom
  const canFitAbove = aboveY >= bounds.top + margin
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

export function getVisibleViewportBounds(): ViewportBounds {
  if (typeof window === 'undefined') {
    return { left: 0, top: 0, width: 1024, height: 768, right: 1024, bottom: 768 }
  }

  const visualViewport = window.visualViewport
  if (visualViewport) {
    const width = Math.max(0, finiteOr(visualViewport.width, window.innerWidth))
    const height = Math.max(0, finiteOr(visualViewport.height, window.innerHeight))
    const left = finiteOr(visualViewport.offsetLeft, 0)
    const top = finiteOr(visualViewport.offsetTop, 0)
    return {
      left,
      top,
      width,
      height,
      right: left + width,
      bottom: top + height,
    }
  }

  const width = Math.max(0, finiteOr(window.innerWidth, 1024))
  const height = Math.max(0, finiteOr(window.innerHeight, 768))
  return { left: 0, top: 0, width, height, right: width, bottom: height }
}

export function subscribeVisibleViewportChanges(onChange: () => void): () => void {
  if (typeof window === 'undefined') return () => {}

  window.addEventListener('resize', onChange)
  window.addEventListener('scroll', onChange, true)
  const visualViewport = window.visualViewport
  visualViewport?.addEventListener('resize', onChange)
  visualViewport?.addEventListener('scroll', onChange)

  return () => {
    window.removeEventListener('resize', onChange)
    window.removeEventListener('scroll', onChange, true)
    visualViewport?.removeEventListener('resize', onChange)
    visualViewport?.removeEventListener('scroll', onChange)
  }
}

export function getViewportSize(): ViewportSize {
  if (typeof window === 'undefined') {
    return { width: 1024, height: 768 }
  }
  return { width: window.innerWidth, height: window.innerHeight }
}
