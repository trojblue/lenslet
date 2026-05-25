import { afterEach, describe, expect, it, vi } from 'vitest'
import {
  clampMenuPosition,
  getDropdownPanelPosition,
  getVisibleViewportBounds,
  subscribeVisibleViewportChanges,
  toViewportBounds,
} from '../menuPosition'

const viewport = { width: 390, height: 844 }

describe('menu positioning', () => {
  afterEach(() => {
    vi.unstubAllGlobals()
  })

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

  it('clamps against visual viewport offsets', () => {
    const pos = clampMenuPosition({
      x: 0,
      y: 10,
      menuWidth: 120,
      menuHeight: 80,
      viewport: { left: 40, top: 120, width: 300, height: 240, right: 340, bottom: 360 },
    })

    expect(pos).toEqual({ x: 48, y: 128 })
  })

  it('pins oversized surfaces to the visible margin', () => {
    const pos = clampMenuPosition({
      x: 200,
      y: 200,
      menuWidth: 500,
      menuHeight: 900,
      viewport,
    })

    expect(pos).toEqual({ x: 8, y: 8 })
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

  it('normalizes size-only viewport inputs to origin bounds', () => {
    expect(toViewportBounds({ width: 320, height: 480 })).toEqual({
      left: 0,
      top: 0,
      width: 320,
      height: 480,
      right: 320,
      bottom: 480,
    })
  })

  it('reads visual viewport bounds when available', () => {
    vi.stubGlobal('window', {
      innerWidth: 1024,
      innerHeight: 768,
      visualViewport: {
        width: 280,
        height: 420,
        offsetLeft: 24,
        offsetTop: 36,
      },
    })

    expect(getVisibleViewportBounds()).toEqual({
      left: 24,
      top: 36,
      width: 280,
      height: 420,
      right: 304,
      bottom: 456,
    })
  })

  it('subscribes to window and visual viewport changes', () => {
    const windowAdd = vi.fn()
    const windowRemove = vi.fn()
    const visualAdd = vi.fn()
    const visualRemove = vi.fn()
    const onChange = vi.fn()
    vi.stubGlobal('window', {
      addEventListener: windowAdd,
      removeEventListener: windowRemove,
      visualViewport: {
        addEventListener: visualAdd,
        removeEventListener: visualRemove,
      },
    })

    const unsubscribe = subscribeVisibleViewportChanges(onChange)
    unsubscribe()

    expect(windowAdd).toHaveBeenCalledWith('resize', onChange)
    expect(windowAdd).toHaveBeenCalledWith('scroll', onChange, true)
    expect(visualAdd).toHaveBeenCalledWith('resize', onChange)
    expect(visualAdd).toHaveBeenCalledWith('scroll', onChange)
    expect(windowRemove).toHaveBeenCalledWith('resize', onChange)
    expect(windowRemove).toHaveBeenCalledWith('scroll', onChange, true)
    expect(visualRemove).toHaveBeenCalledWith('resize', onChange)
    expect(visualRemove).toHaveBeenCalledWith('scroll', onChange)
  })
})
