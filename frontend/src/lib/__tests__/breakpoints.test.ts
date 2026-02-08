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
})
