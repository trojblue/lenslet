export type LayoutMode = 'phone' | 'narrow' | 'tablet' | 'desktop'
export type OverlayMode = 'none' | 'viewer' | 'compare'
export type SidebarSuppressionReason =
  | 'viewport-too-narrow'
  | 'inspector-too-narrow'
  | 'overlay-active'
  | 'short-height'
  | 'insufficient-center-space'

export interface ResponsiveLayoutInput {
  viewportWidth: number
  viewportHeight: number
  userLeftOpen: boolean
  userRightOpen: boolean
  leftPreferredWidth: number
  rightPreferredWidth: number
  overlay: OverlayMode
  mobileSearchOpen: boolean
  mobileDrawerOpen: boolean
}

export interface ResponsiveLayoutModel {
  mode: LayoutMode
  shortHeight: boolean
  centerMinWidth: number

  effectiveLeftOpen: boolean
  effectiveRightOpen: boolean
  leftRailVisible: boolean
  leftWidth: number
  rightWidth: number
  leftSuppressionReason?: SidebarSuppressionReason
  rightSuppressionReason?: SidebarSuppressionReason

  gridInsets: { left: number; right: number }
  overlayInsets: { left: number; right: number }

  inspector: {
    persistentAllowed: boolean
    minUsableWidth: number
    suppressionReason?: SidebarSuppressionReason
  }

  shellReserves: {
    toolbarHeightPx: number
    mobileDrawerHeightPx: number
  }
}

export interface SidebarDragConstraintInput {
  viewportWidth: number
  activeSide: 'left' | 'right'
  userLeftOpen: boolean
  userRightOpen: boolean
  leftPreferredWidth: number
  rightPreferredWidth: number
}

export interface SidebarDragConstraint {
  minWidth: number
  maxWidth: number
  disabled: boolean
  suppressionReason?: SidebarSuppressionReason
}

export const RESPONSIVE_LAYOUT_CONSTANTS = {
  phoneMaxWidth: 480,
  narrowMaxWidth: 900,
  tabletMaxWidth: 1180,
  shortHeightMax: 559,
  leftContentMinWidth: 200,
  leftRailWidth: 48,
  rightInspectorMinUsableWidth: 280,
  baseToolbarHeight: 48,
  mobileSearchRowHeight: 48,
  mobileDrawerHeight: 217,
  centerMinWidthByMode: {
    phone: 320,
    narrow: 360,
    tablet: 420,
    desktop: 520,
  } satisfies Record<LayoutMode, number>,
} as const

function clamp(value: number, min: number, max: number): number {
  return Math.min(Math.max(value, min), max)
}

function positiveFiniteOr(value: number, fallback: number): number {
  return Number.isFinite(value) && value > 0 ? value : fallback
}

export function resolveLayoutMode(viewportWidth: number): LayoutMode {
  if (viewportWidth <= RESPONSIVE_LAYOUT_CONSTANTS.phoneMaxWidth) return 'phone'
  if (viewportWidth <= RESPONSIVE_LAYOUT_CONSTANTS.narrowMaxWidth) return 'narrow'
  if (viewportWidth <= RESPONSIVE_LAYOUT_CONSTANTS.tabletMaxWidth) return 'tablet'
  return 'desktop'
}

function centerMinWidthForMode(mode: LayoutMode): number {
  return RESPONSIVE_LAYOUT_CONSTANTS.centerMinWidthByMode[mode]
}

function leftMaxWidth(viewportWidth: number, mode: LayoutMode): number {
  if (mode === 'phone') return RESPONSIVE_LAYOUT_CONSTANTS.leftContentMinWidth
  if (mode === 'narrow') return 320
  if (mode === 'tablet') return 360
  return clamp(Math.round(viewportWidth * 0.22), 420, 760)
}

function rightMaxWidth(viewportWidth: number, mode: LayoutMode): number {
  if (mode === 'phone') return RESPONSIVE_LAYOUT_CONSTANTS.rightInspectorMinUsableWidth
  if (mode === 'narrow') return 320
  if (mode === 'tablet') return 440
  return clamp(Math.round(viewportWidth * 0.6), 560, 1400)
}

function viewportSuppressionReason(mode: LayoutMode): SidebarSuppressionReason {
  return mode === 'phone' ? 'viewport-too-narrow' : 'insufficient-center-space'
}

function roundWidth(value: number): number {
  return Number(value.toFixed(2))
}

export function buildResponsiveLayoutModel(input: ResponsiveLayoutInput): ResponsiveLayoutModel {
  const viewportWidth = Math.max(0, input.viewportWidth)
  const viewportHeight = Math.max(0, input.viewportHeight)
  const mode = resolveLayoutMode(viewportWidth)
  const shortHeight = viewportHeight < RESPONSIVE_LAYOUT_CONSTANTS.shortHeightMax + 1
  const centerMinWidth = centerMinWidthForMode(mode)
  const overlayActive = input.overlay !== 'none'
  const leftPreferredWidth = positiveFiniteOr(
    input.leftPreferredWidth,
    RESPONSIVE_LAYOUT_CONSTANTS.leftContentMinWidth,
  )
  const rightPreferredWidth = positiveFiniteOr(
    input.rightPreferredWidth,
    RESPONSIVE_LAYOUT_CONSTANTS.rightInspectorMinUsableWidth,
  )

  const mobileShell = mode === 'phone' || mode === 'narrow'
  const shellReserves = {
    toolbarHeightPx: RESPONSIVE_LAYOUT_CONSTANTS.baseToolbarHeight +
      (mobileShell && input.mobileSearchOpen ? RESPONSIVE_LAYOUT_CONSTANTS.mobileSearchRowHeight : 0),
    mobileDrawerHeightPx: mobileShell && !overlayActive && input.mobileDrawerOpen
      ? RESPONSIVE_LAYOUT_CONSTANTS.mobileDrawerHeight
      : 0,
  }

  if (shortHeight) {
    const suppressionReason: SidebarSuppressionReason = 'short-height'
    return {
      mode,
      shortHeight,
      centerMinWidth,
      effectiveLeftOpen: false,
      effectiveRightOpen: false,
      leftRailVisible: false,
      leftWidth: 0,
      rightWidth: 0,
      leftSuppressionReason: input.userLeftOpen ? suppressionReason : undefined,
      rightSuppressionReason: input.userRightOpen ? suppressionReason : undefined,
      gridInsets: { left: 0, right: 0 },
      overlayInsets: { left: 0, right: 0 },
      inspector: {
        persistentAllowed: false,
        minUsableWidth: RESPONSIVE_LAYOUT_CONSTANTS.rightInspectorMinUsableWidth,
        suppressionReason,
      },
      shellReserves,
    }
  }

  const availableForPanels = Math.max(0, viewportWidth - centerMinWidth)
  let remaining = availableForPanels
  let effectiveRightOpen = false
  let rightWidth = 0
  let rightSuppressionReason: SidebarSuppressionReason | undefined

  if (input.userRightOpen) {
    const rightMin = RESPONSIVE_LAYOUT_CONSTANTS.rightInspectorMinUsableWidth
    if (remaining >= rightMin) {
      const reserveLeftMin = input.userLeftOpen && remaining - rightMin >= RESPONSIVE_LAYOUT_CONSTANTS.leftContentMinWidth
        ? RESPONSIVE_LAYOUT_CONSTANTS.leftContentMinWidth
        : 0
      const maxRight = Math.min(rightMaxWidth(viewportWidth, mode), remaining - reserveLeftMin)
      rightWidth = roundWidth(clamp(rightPreferredWidth, rightMin, maxRight))
      effectiveRightOpen = true
      remaining -= rightWidth
    } else {
      rightSuppressionReason = mode === 'phone'
        ? 'viewport-too-narrow'
        : 'inspector-too-narrow'
    }
  }

  let effectiveLeftOpen = false
  let leftContentWidth = 0
  let leftSuppressionReason: SidebarSuppressionReason | undefined

  if (input.userLeftOpen) {
    const leftMin = RESPONSIVE_LAYOUT_CONSTANTS.leftContentMinWidth
    if (remaining >= leftMin) {
      leftContentWidth = roundWidth(clamp(leftPreferredWidth, leftMin, Math.min(leftMaxWidth(viewportWidth, mode), remaining)))
      effectiveLeftOpen = true
      remaining -= leftContentWidth
    } else {
      leftSuppressionReason = viewportWidth < centerMinWidth + leftMin
        ? viewportSuppressionReason(mode)
        : 'insufficient-center-space'
    }
  }

  const inspectorCanPersist = availableForPanels >= RESPONSIVE_LAYOUT_CONSTANTS.rightInspectorMinUsableWidth
  const inspectorSuppressionReason = inspectorCanPersist
    ? undefined
    : (mode === 'phone' ? 'viewport-too-narrow' : 'inspector-too-narrow')
  const leftRailVisible = effectiveLeftOpen ||
    ((mode === 'tablet' || mode === 'desktop') && remaining >= RESPONSIVE_LAYOUT_CONSTANTS.leftRailWidth)
  const leftWidth = effectiveLeftOpen
    ? leftContentWidth
    : (leftRailVisible ? RESPONSIVE_LAYOUT_CONSTANTS.leftRailWidth : 0)

  return {
    mode,
    shortHeight,
    centerMinWidth,
    effectiveLeftOpen,
    effectiveRightOpen,
    leftRailVisible,
    leftWidth,
    rightWidth,
    leftSuppressionReason,
    rightSuppressionReason,
    gridInsets: { left: leftWidth, right: rightWidth },
    overlayInsets: overlayActive ? { left: leftWidth, right: rightWidth } : { left: 0, right: 0 },
    inspector: {
      persistentAllowed: inspectorCanPersist,
      minUsableWidth: RESPONSIVE_LAYOUT_CONSTANTS.rightInspectorMinUsableWidth,
      suppressionReason: inspectorSuppressionReason,
    },
    shellReserves,
  }
}

export function resolveSidebarDragConstraint(input: SidebarDragConstraintInput): SidebarDragConstraint {
  const viewportWidth = Math.max(0, input.viewportWidth)
  const mode = resolveLayoutMode(viewportWidth)
  const centerMinWidth = centerMinWidthForMode(mode)
  const availableForPanels = Math.max(0, viewportWidth - centerMinWidth)
  const leftMin = RESPONSIVE_LAYOUT_CONSTANTS.leftContentMinWidth
  const rightMin = RESPONSIVE_LAYOUT_CONSTANTS.rightInspectorMinUsableWidth

  if (input.activeSide === 'left') {
    const rightReserve = input.userRightOpen && availableForPanels - leftMin >= rightMin
      ? clamp(
        positiveFiniteOr(input.rightPreferredWidth, rightMin),
        rightMin,
        Math.min(rightMaxWidth(viewportWidth, mode), availableForPanels - leftMin),
      )
      : 0
    const maxWidth = roundWidth(Math.min(leftMaxWidth(viewportWidth, mode), availableForPanels - rightReserve))
    return {
      minWidth: leftMin,
      maxWidth,
      disabled: maxWidth < leftMin,
      suppressionReason: maxWidth < leftMin ? viewportSuppressionReason(mode) : undefined,
    }
  }

  const leftReserve = input.userLeftOpen && availableForPanels - rightMin >= leftMin
    ? leftMin
    : 0
  const maxWidth = roundWidth(Math.min(rightMaxWidth(viewportWidth, mode), availableForPanels - leftReserve))
  return {
    minWidth: rightMin,
    maxWidth,
    disabled: maxWidth < rightMin,
    suppressionReason: maxWidth < rightMin
      ? (mode === 'phone' ? 'viewport-too-narrow' : 'inspector-too-narrow')
      : undefined,
  }
}

export function clampSidebarDragWidth(
  width: number,
  constraint: SidebarDragConstraint,
): number {
  if (constraint.disabled) return 0
  return roundWidth(clamp(width, constraint.minWidth, constraint.maxWidth))
}
