import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'
import { LONG_PRESS_DELAY_MS, LongPressController } from '../touch'

function ptr(
  pointerId: number,
  x: number,
  y: number,
  pointerType: 'touch' | 'pen' | 'mouse' = 'touch',
) {
  return { pointerId, clientX: x, clientY: y, pointerType, isPrimary: true as const }
}

describe('LongPressController', () => {
  beforeEach(() => {
    vi.useFakeTimers()
  })

  afterEach(() => {
    vi.useRealTimers()
    vi.restoreAllMocks()
  })

  it('fires onLongPress after the configured delay', () => {
    const onLongPress = vi.fn()
    const controller = new LongPressController({ onLongPress })

    const started = controller.pointerDown(ptr(1, 10, 10))
    expect(started).toBe(true)
    vi.advanceTimersByTime(LONG_PRESS_DELAY_MS - 1)
    expect(onLongPress).not.toHaveBeenCalled()

    vi.advanceTimersByTime(1)
    expect(onLongPress).toHaveBeenCalledTimes(1)
  })

  it('cancels when movement exceeds tolerance', () => {
    const onLongPress = vi.fn()
    const onCancel = vi.fn()
    const controller = new LongPressController({ onLongPress, onCancel })

    controller.pointerDown(ptr(1, 10, 10))
    controller.pointerMove(ptr(1, 25, 10))
    vi.advanceTimersByTime(LONG_PRESS_DELAY_MS + 1)

    expect(onLongPress).not.toHaveBeenCalled()
    expect(onCancel).toHaveBeenCalledWith('movement')
  })

  it('cancels on pointercancel', () => {
    const onLongPress = vi.fn()
    const onCancel = vi.fn()
    const controller = new LongPressController({ onLongPress, onCancel })

    controller.pointerDown(ptr(1, 10, 10))
    controller.pointerCancel(1)
    vi.advanceTimersByTime(LONG_PRESS_DELAY_MS + 1)

    expect(onLongPress).not.toHaveBeenCalled()
    expect(onCancel).toHaveBeenCalledWith('pointercancel')
  })

  it('does not fire when cancelled by scroll', () => {
    const onLongPress = vi.fn()
    const onCancel = vi.fn()
    const controller = new LongPressController({ onLongPress, onCancel })

    controller.pointerDown(ptr(1, 10, 10))
    controller.cancelFromScroll()
    vi.advanceTimersByTime(LONG_PRESS_DELAY_MS + 1)

    expect(onLongPress).not.toHaveBeenCalled()
    expect(onCancel).toHaveBeenCalledWith('scroll')
  })

  it('ignores mouse pointer presses', () => {
    const onLongPress = vi.fn()
    const controller = new LongPressController({ onLongPress })

    const started = controller.pointerDown(ptr(1, 10, 10, 'mouse'))
    vi.advanceTimersByTime(LONG_PRESS_DELAY_MS + 1)

    expect(started).toBe(false)
    expect(onLongPress).not.toHaveBeenCalled()
  })
})
