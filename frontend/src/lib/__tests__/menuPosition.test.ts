import { describe, expect, it } from 'vitest'
import { clampMenuPosition, getDropdownPanelPosition } from '../menuPosition'

const viewport = { width: 390, height: 844 }

describe('menu positioning', () => {
  it('clamps context menu position to viewport bounds', () => {
    const pos = clampMenuPosition({
      x: -20,
      y: 900,
      menuWidth: 220,
      menuHeight: 240,
      viewport,
    })

    expect(pos.x).toBe(8)
    expect(pos.y).toBe(596)
  })

  it('keeps an already valid position unchanged', () => {
    const pos = clampMenuPosition({
      x: 24,
      y: 36,
      menuWidth: 160,
      menuHeight: 120,
      viewport,
    })

    expect(pos).toEqual({ x: 24, y: 36 })
  })

  it('places dropdown above trigger when below would overflow', () => {
    const pos = getDropdownPanelPosition({
      anchorRect: { left: 40, right: 120, top: 820, bottom: 840 },
      menuSize: { width: 180, height: 180 },
      viewport,
      align: 'left',
    })

    expect(pos.y).toBeLessThan(820)
  })

  it('clamps right-aligned dropdown near viewport edge', () => {
    const pos = getDropdownPanelPosition({
      anchorRect: { left: 4, right: 42, top: 40, bottom: 70 },
      menuSize: { width: 240, height: 180 },
      viewport,
      align: 'right',
    })

    expect(pos.x).toBe(8)
    expect(pos.y).toBeGreaterThanOrEqual(8)
  })
})
