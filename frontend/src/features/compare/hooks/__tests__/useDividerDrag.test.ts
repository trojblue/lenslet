import { describe, expect, it, vi } from 'vitest'
import {
  clampCompareSplitPct,
  createDividerDragSession,
  splitPctFromClientX,
} from '../useDividerDrag'

type Listener = EventListener

class FakeEventTarget {
  captured: number[] = []
  released: number[] = []
  private listeners = new Map<string, Set<Listener>>()

  addEventListener(type: string, listener: Listener): void {
    const listeners = this.listeners.get(type) ?? new Set<Listener>()
    listeners.add(listener)
    this.listeners.set(type, listeners)
  }

  removeEventListener(type: string, listener: Listener): void {
    this.listeners.get(type)?.delete(listener)
  }

  setPointerCapture(pointerId: number): void {
    this.captured.push(pointerId)
  }

  releasePointerCapture(pointerId: number): void {
    this.released.push(pointerId)
  }

  dispatch(type: string, event: PointerEvent): void {
    for (const listener of Array.from(this.listeners.get(type) ?? [])) {
      listener(event)
    }
  }

  listenerCount(type: string): number {
    return this.listeners.get(type)?.size ?? 0
  }
}

function pointerEvent(pointerId: number, clientX = 0): PointerEvent {
  return {
    pointerId,
    clientX,
    preventDefault: vi.fn(),
  } as unknown as PointerEvent
}

describe('compare divider drag helpers', () => {
  it('clamps split percentages to the compare divider range', () => {
    expect(clampCompareSplitPct(-20)).toBe(5)
    expect(clampCompareSplitPct(50)).toBe(50)
    expect(clampCompareSplitPct(120)).toBe(95)
  })

  it('computes split percentage from the current stage bounds', () => {
    expect(splitPctFromClientX(75, { left: 25, width: 100 })).toBe(50)
    expect(splitPctFromClientX(-50, { left: 0, width: 100 })).toBe(5)
    expect(splitPctFromClientX(250, { left: 0, width: 100 })).toBe(95)
    expect(splitPctFromClientX(50, { left: 0, width: 0 })).toBeNull()
  })

  it('recomputes stage bounds on every move instead of reusing a stale rect', () => {
    const listenerTarget = new FakeEventTarget()
    const target = new FakeEventTarget()
    const values: number[] = []
    const rects = [
      { left: 0, width: 100 },
      { left: 0, width: 200 },
    ]

    createDividerDragSession({
      pointerId: 7,
      target: target as unknown as HTMLElement,
      listenerTarget: listenerTarget as unknown as Window,
      getStageRect: () => rects.shift() ?? { left: 0, width: 200 },
      setSplitPct: (value) => values.push(value),
    })

    listenerTarget.dispatch('pointermove', pointerEvent(7, 90))
    listenerTarget.dispatch('pointermove', pointerEvent(7, 90))

    expect(values).toEqual([90, 45])
  })

  it('removes global listeners and releases capture on pointer end', () => {
    const listenerTarget = new FakeEventTarget()
    const target = new FakeEventTarget()
    const values: number[] = []
    const session = createDividerDragSession({
      pointerId: 3,
      target: target as unknown as HTMLElement,
      listenerTarget: listenerTarget as unknown as Window,
      getStageRect: () => ({ left: 0, width: 100 }),
      setSplitPct: (value) => values.push(value),
    })

    listenerTarget.dispatch('pointermove', pointerEvent(3, 70))
    listenerTarget.dispatch('pointerup', pointerEvent(3, 70))
    listenerTarget.dispatch('pointermove', pointerEvent(3, 30))

    expect(values).toEqual([70])
    expect(target.captured).toEqual([3])
    expect(target.released).toEqual([3])
    expect(session.isActive()).toBe(false)
    expect(listenerTarget.listenerCount('pointermove')).toBe(0)
    expect(listenerTarget.listenerCount('pointerup')).toBe(0)
    expect(listenerTarget.listenerCount('pointercancel')).toBe(0)
    expect(target.listenerCount('lostpointercapture')).toBe(0)
  })

  it('cleans up when pointer capture is lost', () => {
    const listenerTarget = new FakeEventTarget()
    const target = new FakeEventTarget()
    const values: number[] = []
    const session = createDividerDragSession({
      pointerId: 11,
      target: target as unknown as HTMLElement,
      listenerTarget: listenerTarget as unknown as Window,
      getStageRect: () => ({ left: 0, width: 100 }),
      setSplitPct: (value) => values.push(value),
    })

    target.dispatch('lostpointercapture', pointerEvent(11, 0))
    listenerTarget.dispatch('pointermove', pointerEvent(11, 85))

    expect(values).toEqual([])
    expect(session.isActive()).toBe(false)
    expect(listenerTarget.listenerCount('pointermove')).toBe(0)
    expect(target.listenerCount('lostpointercapture')).toBe(0)
  })
})
