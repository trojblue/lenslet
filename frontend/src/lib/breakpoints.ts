export const LAYOUT_BREAKPOINTS = {
  phoneMax: 480,
  mobileMax: 767,
  narrowMax: 900,
  tabletMax: 1024,
  mediumMax: 1180,
} as const

export const LAYOUT_MEDIA_QUERIES = {
  phone: `(max-width: ${LAYOUT_BREAKPOINTS.phoneMax}px)`,
  mobile: `(max-width: ${LAYOUT_BREAKPOINTS.mobileMax}px)`,
  narrow: `(max-width: ${LAYOUT_BREAKPOINTS.narrowMax}px)`,
} as const

const SIDEBAR_LEFT_MIN = 200
const SIDEBAR_RIGHT_MIN = 240
const SIDEBAR_MAX_TABLET = 320
const SIDEBAR_MAX_MEDIUM = 360
const SIDEBAR_MAX_DESKTOP = 420

function clamp(value: number, min: number, max: number): number {
  return Math.min(Math.max(value, min), max)
}

function getSidebarMaxWidth(viewportWidth: number): number {
  if (viewportWidth <= LAYOUT_BREAKPOINTS.tabletMax) return SIDEBAR_MAX_TABLET
  if (viewportWidth <= LAYOUT_BREAKPOINTS.mediumMax) return SIDEBAR_MAX_MEDIUM
  return SIDEBAR_MAX_DESKTOP
}

function getMinCenterWidth(viewportWidth: number): number {
  if (viewportWidth <= LAYOUT_BREAKPOINTS.tabletMax) return 360
  if (viewportWidth <= LAYOUT_BREAKPOINTS.mediumMax) return 420
  return 520
}

export interface SidebarConstraintInput {
  viewportWidth: number
  leftOpen: boolean
  rightOpen: boolean
  leftWidth: number
  rightWidth: number
}

export interface SidebarConstraintResult {
  leftWidth: number
  rightWidth: number
}

export function constrainSidebarWidths({
  viewportWidth,
  leftOpen,
  rightOpen,
  leftWidth,
  rightWidth,
}: SidebarConstraintInput): SidebarConstraintResult {
  const maxSidebar = getSidebarMaxWidth(viewportWidth)
  let left = leftOpen ? clamp(leftWidth, SIDEBAR_LEFT_MIN, maxSidebar) : 0
  let right = rightOpen ? clamp(rightWidth, SIDEBAR_RIGHT_MIN, maxSidebar) : 0

  const maxCombined = Math.max(0, viewportWidth - getMinCenterWidth(viewportWidth))
  if (left + right > maxCombined) {
    let overflow = left + right - maxCombined

    if (right > 0) {
      const shrinkableRight = Math.max(0, right - SIDEBAR_RIGHT_MIN)
      const shrinkRight = Math.min(shrinkableRight, overflow)
      right -= shrinkRight
      overflow -= shrinkRight
    }

    if (overflow > 0 && left > 0) {
      const shrinkableLeft = Math.max(0, left - SIDEBAR_LEFT_MIN)
      const shrinkLeft = Math.min(shrinkableLeft, overflow)
      left -= shrinkLeft
      overflow -= shrinkLeft
    }

    if (overflow > 0 && right > 0) {
      right = Math.max(0, maxCombined - left)
    }

    if (left + right > maxCombined) {
      left = Math.max(0, maxCombined - right)
    }
  }

  return {
    leftWidth: Number(left.toFixed(2)),
    rightWidth: Number(right.toFixed(2)),
  }
}
