import { describe, expect, it } from 'vitest'
import { constrainSidebarWidths } from '../breakpoints'

describe('constrainSidebarWidths', () => {
  it('caps panel widths at tablet limits', () => {
    const constrained = constrainSidebarWidths({
      viewportWidth: 1024,
      leftOpen: true,
      rightOpen: true,
      leftWidth: 420,
      rightWidth: 500,
    })

    expect(constrained.leftWidth).toBe(320)
    expect(constrained.rightWidth).toBe(320)
  })

  it('shrinks right panel before left when center space is constrained', () => {
    const constrained = constrainSidebarWidths({
      viewportWidth: 930,
      leftOpen: true,
      rightOpen: true,
      leftWidth: 320,
      rightWidth: 320,
    })

    expect(constrained.leftWidth).toBe(320)
    expect(constrained.rightWidth).toBe(250)
  })

  it('returns zero width for closed sidebars', () => {
    const constrained = constrainSidebarWidths({
      viewportWidth: 1180,
      leftOpen: false,
      rightOpen: false,
      leftWidth: 280,
      rightWidth: 300,
    })

    expect(constrained).toEqual({ leftWidth: 0, rightWidth: 0 })
  })

  it('allows wider sidebars on very wide viewports', () => {
    const constrained = constrainSidebarWidths({
      viewportWidth: 3840,
      leftOpen: true,
      rightOpen: true,
      leftWidth: 900,
      rightWidth: 900,
    })

    expect(constrained.leftWidth).toBe(760)
    expect(constrained.rightWidth).toBe(900)
  })

  it('lets the right inspector reach at least 560px at 1440px while preserving center space', () => {
    const constrained = constrainSidebarWidths({
      viewportWidth: 1440,
      leftOpen: true,
      rightOpen: true,
      leftWidth: 240,
      rightWidth: 900,
    })

    expect(constrained.rightWidth).toBeGreaterThanOrEqual(560)
    const centerWidth = 1440 - constrained.leftWidth - constrained.rightWidth
    expect(centerWidth).toBeGreaterThanOrEqual(520)
  })
})
