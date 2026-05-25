import { describe, expect, it } from 'vitest'
import {
  RESPONSIVE_LAYOUT_CONSTANTS,
  buildResponsiveLayoutModel,
  resolveLayoutMode,
  resolveSidebarDragConstraint,
} from '../responsiveLayoutPolicy'

function model(overrides: Partial<Parameters<typeof buildResponsiveLayoutModel>[0]> = {}) {
  return buildResponsiveLayoutModel({
    viewportWidth: 1440,
    viewportHeight: 900,
    userLeftOpen: true,
    userRightOpen: true,
    leftPreferredWidth: 240,
    rightPreferredWidth: 300,
    overlay: 'none',
    mobileSearchOpen: false,
    mobileDrawerOpen: true,
    ...overrides,
  })
}

describe('responsiveLayoutPolicy', () => {
  it('classifies the four layout modes at their boundaries', () => {
    expect(resolveLayoutMode(320)).toBe('phone')
    expect(resolveLayoutMode(480)).toBe('phone')
    expect(resolveLayoutMode(481)).toBe('narrow')
    expect(resolveLayoutMode(900)).toBe('narrow')
    expect(resolveLayoutMode(901)).toBe('tablet')
    expect(resolveLayoutMode(1180)).toBe('tablet')
    expect(resolveLayoutMode(1181)).toBe('desktop')
  })

  it('keeps ordinary desktop preferences effective without mutating them', () => {
    const layout = model()

    expect(layout.mode).toBe('desktop')
    expect(layout.effectiveLeftOpen).toBe(true)
    expect(layout.effectiveRightOpen).toBe(true)
    expect(layout.leftWidth).toBe(240)
    expect(layout.rightWidth).toBe(300)
    expect(layout.gridInsets).toEqual({ left: 240, right: 300 })
    expect(layout.overlayInsets).toEqual({ left: 0, right: 0 })
  })

  it('suppresses impossible phone sidebars instead of shrinking them below usable minima', () => {
    const layout = model({ viewportWidth: 320, viewportHeight: 700 })

    expect(layout.mode).toBe('phone')
    expect(layout.centerMinWidth).toBe(RESPONSIVE_LAYOUT_CONSTANTS.centerMinWidthByMode.phone)
    expect(layout.effectiveLeftOpen).toBe(false)
    expect(layout.effectiveRightOpen).toBe(false)
    expect(layout.leftWidth).toBe(0)
    expect(layout.rightWidth).toBe(0)
    expect(layout.leftSuppressionReason).toBe('viewport-too-narrow')
    expect(layout.rightSuppressionReason).toBe('viewport-too-narrow')
  })

  it('prioritizes the inspector when both preferred sidebars cannot fit at narrow width', () => {
    const layout = model({
      viewportWidth: 760,
      leftPreferredWidth: 320,
      rightPreferredWidth: 300,
    })

    expect(layout.mode).toBe('narrow')
    expect(layout.effectiveRightOpen).toBe(true)
    expect(layout.rightWidth).toBe(300)
    expect(layout.effectiveLeftOpen).toBe(false)
    expect(layout.leftSuppressionReason).toBe('insufficient-center-space')
    expect(760 - layout.gridInsets.left - layout.gridInsets.right).toBeGreaterThanOrEqual(layout.centerMinWidth)
  })

  it('keeps both sidebars usable at 900px by clamping oversized preferred widths', () => {
    const layout = model({
      viewportWidth: 900,
      leftPreferredWidth: 760,
      rightPreferredWidth: 900,
    })

    expect(layout.mode).toBe('narrow')
    expect(layout.effectiveLeftOpen).toBe(true)
    expect(layout.effectiveRightOpen).toBe(true)
    expect(layout.leftWidth).toBeGreaterThanOrEqual(RESPONSIVE_LAYOUT_CONSTANTS.leftContentMinWidth)
    expect(layout.rightWidth).toBeGreaterThanOrEqual(RESPONSIVE_LAYOUT_CONSTANTS.rightInspectorMinUsableWidth)
    expect(layout.leftWidth + layout.rightWidth + layout.centerMinWidth).toBeLessThanOrEqual(900)
    expect(layout.leftWidth).toBeLessThan(760)
    expect(layout.rightWidth).toBeLessThan(900)
  })

  it('clamps absurd persisted right widths at 1024px without suppressing a usable inspector', () => {
    const layout = model({
      viewportWidth: 1024,
      leftPreferredWidth: 240,
      rightPreferredWidth: 900,
    })

    expect(layout.mode).toBe('tablet')
    expect(layout.effectiveRightOpen).toBe(true)
    expect(layout.rightWidth).toBe(404)
    expect(layout.effectiveLeftOpen).toBe(true)
    expect(layout.leftWidth).toBe(200)
    expect(layout.leftWidth + layout.rightWidth + layout.centerMinWidth).toBe(1024)
  })

  it('restores effective sidebars when resizing back up with the same user preferences', () => {
    const narrow = model({ viewportWidth: 320, viewportHeight: 700 })
    const desktop = model({ viewportWidth: 1440, viewportHeight: 900 })

    expect(narrow.effectiveLeftOpen).toBe(false)
    expect(narrow.effectiveRightOpen).toBe(false)
    expect(desktop.effectiveLeftOpen).toBe(true)
    expect(desktop.effectiveRightOpen).toBe(true)
  })

  it('suppresses sidebars during short-height states', () => {
    const short = model({ viewportWidth: 1024, viewportHeight: 430 })

    expect(short.shortHeight).toBe(true)
    expect(short.leftSuppressionReason).toBe('short-height')
    expect(short.rightSuppressionReason).toBe('short-height')
    expect(short.overlayInsets).toEqual({ left: 0, right: 0 })
  })

  it('preserves normal visible sidebars and uses them as viewer overlay insets', () => {
    const normal = model({ overlay: 'none', viewportWidth: 1440 })
    const viewer = model({ overlay: 'viewer', viewportWidth: 1440 })

    expect(viewer.effectiveLeftOpen).toBe(normal.effectiveLeftOpen)
    expect(viewer.effectiveRightOpen).toBe(normal.effectiveRightOpen)
    expect(viewer.leftWidth).toBe(normal.leftWidth)
    expect(viewer.rightWidth).toBe(normal.rightWidth)
    expect(viewer.leftSuppressionReason).toBeUndefined()
    expect(viewer.rightSuppressionReason).toBeUndefined()
    expect(viewer.gridInsets).toEqual(normal.gridInsets)
    expect(viewer.overlayInsets).toEqual({
      left: normal.leftWidth,
      right: normal.rightWidth,
    })
  })

  it('preserves normal visible sidebars and uses them as compare overlay insets at borderline width', () => {
    const normal = model({
      overlay: 'none',
      viewportWidth: 900,
      leftPreferredWidth: 760,
      rightPreferredWidth: 900,
    })
    const compare = model({
      overlay: 'compare',
      viewportWidth: 900,
      leftPreferredWidth: 760,
      rightPreferredWidth: 900,
    })

    expect(normal.effectiveLeftOpen).toBe(true)
    expect(normal.effectiveRightOpen).toBe(true)
    expect(compare.effectiveLeftOpen).toBe(true)
    expect(compare.effectiveRightOpen).toBe(true)
    expect(compare.leftWidth).toBe(normal.leftWidth)
    expect(compare.rightWidth).toBe(normal.rightWidth)
    expect(compare.overlayInsets).toEqual({
      left: normal.leftWidth,
      right: normal.rightWidth,
    })
  })

  it('does not force overlay sidebars onto layouts where normal policy suppresses them', () => {
    const phone = model({ viewportWidth: 390, viewportHeight: 700, overlay: 'viewer' })
    const short = model({ viewportWidth: 1024, viewportHeight: 430, overlay: 'viewer' })

    expect(phone.mode).toBe('phone')
    expect(phone.effectiveLeftOpen).toBe(false)
    expect(phone.effectiveRightOpen).toBe(false)
    expect(phone.overlayInsets).toEqual({ left: 0, right: 0 })
    expect(phone.shellReserves.mobileDrawerHeightPx).toBe(0)
    expect(short.shortHeight).toBe(true)
    expect(short.leftSuppressionReason).toBe('short-height')
    expect(short.rightSuppressionReason).toBe('short-height')
    expect(short.overlayInsets).toEqual({ left: 0, right: 0 })
  })

  it('declares shell reserves from policy constants', () => {
    expect(model({ viewportWidth: 390, mobileSearchOpen: false }).shellReserves).toEqual({
      toolbarHeightPx: 48,
      mobileDrawerHeightPx: 217,
    })
    expect(model({ viewportWidth: 390, mobileSearchOpen: true }).shellReserves).toEqual({
      toolbarHeightPx: 96,
      mobileDrawerHeightPx: 217,
    })
    expect(model({ viewportWidth: 390, mobileDrawerOpen: false }).shellReserves).toEqual({
      toolbarHeightPx: 48,
      mobileDrawerHeightPx: 0,
    })
    expect(model({ viewportWidth: 1440, mobileSearchOpen: true }).shellReserves).toEqual({
      toolbarHeightPx: 48,
      mobileDrawerHeightPx: 0,
    })
  })

  it('uses the same policy for drag constraints', () => {
    expect(resolveSidebarDragConstraint({
      viewportWidth: 1440,
      activeSide: 'right',
      userLeftOpen: true,
      userRightOpen: true,
      leftPreferredWidth: 240,
      rightPreferredWidth: 900,
    })).toEqual({
      minWidth: 280,
      maxWidth: 720,
      disabled: false,
      suppressionReason: undefined,
    })

    expect(resolveSidebarDragConstraint({
      viewportWidth: 320,
      activeSide: 'left',
      userLeftOpen: true,
      userRightOpen: false,
      leftPreferredWidth: 760,
      rightPreferredWidth: 300,
    })).toEqual({
      minWidth: 200,
      maxWidth: 0,
      disabled: true,
      suppressionReason: 'viewport-too-narrow',
    })
  })
})
