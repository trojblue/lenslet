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
  toolbarCompact: `(max-width: ${LAYOUT_BREAKPOINTS.mediumMax}px)`,
} as const
