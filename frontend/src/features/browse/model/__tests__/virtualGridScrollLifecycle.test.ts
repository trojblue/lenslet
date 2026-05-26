import { describe, expect, it, vi } from 'vitest'
import {
  cancelPendingScrollAnimationFrame,
  clearScrollIdleTimeout,
} from '../virtualGridScrollLifecycle'

describe('virtual grid scroll lifecycle', () => {
  it('clears the scroll idle timeout and returns an idle sentinel', () => {
    const clearTimeoutFn = vi.fn()

    const nextTimeoutId = clearScrollIdleTimeout(23, clearTimeoutFn)

    expect(nextTimeoutId).toBeNull()
    expect(clearTimeoutFn).toHaveBeenCalledWith(23)
  })

  it('does not clear an idle scroll timeout sentinel', () => {
    const clearTimeoutFn = vi.fn()

    const nextTimeoutId = clearScrollIdleTimeout(null, clearTimeoutFn)

    expect(nextTimeoutId).toBeNull()
    expect(clearTimeoutFn).not.toHaveBeenCalled()
  })

  it('cancels and clears a pending scroll animation frame', () => {
    const cancelFrame = vi.fn()
    const frameRef = { current: 17 }

    cancelPendingScrollAnimationFrame(frameRef, cancelFrame)

    expect(cancelFrame).toHaveBeenCalledWith(17)
    expect(frameRef.current).toBeNull()
  })

  it('leaves idle scroll animation state untouched', () => {
    const cancelFrame = vi.fn()
    const frameRef = { current: null }

    cancelPendingScrollAnimationFrame(frameRef, cancelFrame)

    expect(cancelFrame).not.toHaveBeenCalled()
    expect(frameRef.current).toBeNull()
  })

  it('clears the pending frame even when cancellation fails', () => {
    const cancelFrame = vi.fn(() => {
      throw new Error('cancel failed')
    })
    const frameRef = { current: 31 }

    expect(() => cancelPendingScrollAnimationFrame(frameRef, cancelFrame)).toThrow('cancel failed')
    expect(frameRef.current).toBeNull()
  })
})
