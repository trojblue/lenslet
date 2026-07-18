import { describe, expect, it, vi } from 'vitest'
import {
  applyAccumulatedGridWheelDelta,
  bindGridResizeGestures,
  isGridResizeWheel,
} from '../useGridResizeGestures'

class FakeGestureTarget {
  private readonly listeners = new Map<string, Set<EventListener>>()

  addEventListener(type: string, listener: EventListenerOrEventListenerObject): void {
    if (typeof listener !== 'function') return
    const listeners = this.listeners.get(type) ?? new Set<EventListener>()
    listeners.add(listener)
    this.listeners.set(type, listeners)
  }

  removeEventListener(type: string, listener: EventListenerOrEventListenerObject): void {
    if (typeof listener !== 'function') return
    this.listeners.get(type)?.delete(listener)
  }

  dispatch(type: string, event: unknown): void {
    for (const listener of this.listeners.get(type) ?? []) listener(event as Event)
  }

  listenerCount(type: string): number {
    return this.listeners.get(type)?.size ?? 0
  }
}

describe('grid resize wheel policy', () => {
  it('targets Control and Meta modifiers only', () => {
    expect(isGridResizeWheel({ ctrlKey: true, metaKey: false })).toBe(true)
    expect(isGridResizeWheel({ ctrlKey: false, metaKey: true })).toBe(true)
    expect(isGridResizeWheel({ ctrlKey: false, metaKey: false })).toBe(false)
  })

  it('accumulates sub-step deltas and applies direction, step, and bounds', () => {
    expect(applyAccumulatedGridWheelDelta(220, 60)).toEqual({
      gridItemSize: 220,
      remainingDelta: 60,
    })
    expect(applyAccumulatedGridWheelDelta(220, 120)).toEqual({
      gridItemSize: 230,
      remainingDelta: 20,
    })
    expect(applyAccumulatedGridWheelDelta(220, -100)).toEqual({
      gridItemSize: 210,
      remainingDelta: 0,
    })
    expect(applyAccumulatedGridWheelDelta(490, 300)).toEqual({
      gridItemSize: 500,
      remainingDelta: 0,
    })
    expect(applyAccumulatedGridWheelDelta(90, -300)).toEqual({
      gridItemSize: 80,
      remainingDelta: 0,
    })
  })

  it('coalesces one target wheel burst per frame and leaves other targets alone', () => {
    const gallery = new FakeGestureTarget()
    const other = new FakeGestureTarget()
    let gridItemSize = 220
    let frame: FrameRequestCallback | null = null
    const requestFrame = vi.fn((callback: FrameRequestCallback) => {
      frame = callback
      return 7
    })
    const onGridItemSizeChange = vi.fn((nextSize: number) => {
      gridItemSize = nextSize
    })
    const cleanup = bindGridResizeGestures({
      target: gallery as unknown as HTMLElement,
      getGridItemSize: () => gridItemSize,
      onGridItemSizeChange,
      requestFrame,
      cancelFrame: vi.fn(),
    })
    const preventDefault = vi.fn()
    const wheelEvent = { ctrlKey: true, metaKey: false, deltaY: -60, preventDefault }

    other.dispatch('wheel', wheelEvent)
    gallery.dispatch('wheel', wheelEvent)
    gallery.dispatch('wheel', wheelEvent)

    expect(preventDefault).toHaveBeenCalledTimes(2)
    expect(requestFrame).toHaveBeenCalledTimes(1)
    expect(onGridItemSizeChange).not.toHaveBeenCalled()
    expect(frame).not.toBeNull()
    ;(frame as unknown as FrameRequestCallback)(0)
    expect(onGridItemSizeChange).toHaveBeenCalledOnce()
    expect(gridItemSize).toBe(230)

    cleanup()
    expect(gallery.listenerCount('wheel')).toBe(0)
    expect(gallery.listenerCount('touchstart')).toBe(0)
    expect(gallery.listenerCount('touchmove')).toBe(0)
  })

  it('does not consume ordinary wheel input and cancels a pending frame on cleanup', () => {
    const gallery = new FakeGestureTarget()
    const cancelFrame = vi.fn()
    const requestFrame = vi.fn((_callback: FrameRequestCallback) => 11)
    const cleanup = bindGridResizeGestures({
      target: gallery as unknown as HTMLElement,
      getGridItemSize: () => 220,
      onGridItemSizeChange: vi.fn(),
      requestFrame,
      cancelFrame,
    })
    const ordinaryPreventDefault = vi.fn()
    gallery.dispatch('wheel', {
      ctrlKey: false,
      metaKey: false,
      deltaY: 100,
      preventDefault: ordinaryPreventDefault,
    })
    expect(ordinaryPreventDefault).not.toHaveBeenCalled()
    expect(requestFrame).not.toHaveBeenCalled()

    gallery.dispatch('wheel', {
      ctrlKey: false,
      metaKey: true,
      deltaY: -100,
      preventDefault: vi.fn(),
    })
    cleanup()
    expect(cancelFrame).toHaveBeenCalledWith(11)
  })
})
