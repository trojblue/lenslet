export const LONG_PRESS_DELAY_MS = 500
export const LONG_PRESS_DELAY_MIN_MS = 450
export const LONG_PRESS_DELAY_MAX_MS = 600
export const LONG_PRESS_MOVE_TOLERANCE_PX = 8

export type LongPressCancelReason =
  | 'movement'
  | 'scroll'
  | 'pointerup'
  | 'pointercancel'
  | 'multitouch'
  | 'cleanup'

export interface LongPressPointerEventLike {
  pointerId: number
  pointerType?: string
  clientX: number
  clientY: number
  isPrimary?: boolean
}

interface LongPressControllerOptions {
  delayMs?: number
  moveTolerancePx?: number
  onLongPress: (event: LongPressPointerEventLike) => void
  onCancel?: (reason: LongPressCancelReason) => void
}

function clampLongPressDelay(delayMs: number): number {
  return Math.max(LONG_PRESS_DELAY_MIN_MS, Math.min(LONG_PRESS_DELAY_MAX_MS, delayMs))
}

/**
 * A tiny state machine that tracks a single long-press gesture and exposes
 * explicit cancellation reasons for deterministic behavior in tests/components.
 */
export class LongPressController {
  private readonly delayMs: number
  private readonly moveTolerancePx: number
  private readonly onLongPress: (event: LongPressPointerEventLike) => void
  private readonly onCancel?: (reason: LongPressCancelReason) => void

  private timerId: ReturnType<typeof setTimeout> | null = null
  private activePointerId: number | null = null
  private startX = 0
  private startY = 0
  private lastEvent: LongPressPointerEventLike | null = null
  private fired = false

  constructor(options: LongPressControllerOptions) {
    this.delayMs = clampLongPressDelay(options.delayMs ?? LONG_PRESS_DELAY_MS)
    this.moveTolerancePx = Math.max(0, options.moveTolerancePx ?? LONG_PRESS_MOVE_TOLERANCE_PX)
    this.onLongPress = options.onLongPress
    this.onCancel = options.onCancel
  }

  pointerDown(event: LongPressPointerEventLike): boolean {
    if ((event.pointerType ?? 'mouse') === 'mouse') return false
    if (event.isPrimary === false) {
      this.cancel('multitouch')
      return false
    }
    if (this.activePointerId != null && this.activePointerId !== event.pointerId) {
      this.cancel('multitouch')
      return false
    }

    this.activePointerId = event.pointerId
    this.startX = event.clientX
    this.startY = event.clientY
    this.lastEvent = event
    this.fired = false
    this.clearTimer()

    this.timerId = setTimeout(() => {
      if (this.activePointerId == null || this.fired || this.lastEvent == null) return
      this.fired = true
      this.clearTimer()
      this.onLongPress(this.lastEvent)
    }, this.delayMs)

    return true
  }

  pointerMove(event: LongPressPointerEventLike): void {
    if (!this.matchesPointer(event.pointerId) || this.fired) return
    this.lastEvent = event
    const dx = event.clientX - this.startX
    const dy = event.clientY - this.startY
    if (Math.hypot(dx, dy) > this.moveTolerancePx) {
      this.cancel('movement')
    }
  }

  pointerUp(pointerId?: number): void {
    if (pointerId != null && !this.matchesPointer(pointerId)) return
    if (!this.fired) {
      this.cancel('pointerup')
      return
    }
    this.reset()
  }

  pointerCancel(pointerId?: number): void {
    if (pointerId != null && !this.matchesPointer(pointerId)) return
    this.cancel('pointercancel')
  }

  cancelFromScroll(): void {
    this.cancel('scroll')
  }

  destroy(): void {
    this.cancel('cleanup')
  }

  private matchesPointer(pointerId: number): boolean {
    return this.activePointerId != null && this.activePointerId === pointerId
  }

  private clearTimer(): void {
    if (this.timerId == null) return
    clearTimeout(this.timerId)
    this.timerId = null
  }

  private reset(): void {
    this.clearTimer()
    this.activePointerId = null
    this.lastEvent = null
    this.fired = false
  }

  private cancel(reason: LongPressCancelReason): void {
    const shouldNotify = this.timerId != null && !this.fired && reason !== 'cleanup'
    this.reset()
    if (shouldNotify) {
      this.onCancel?.(reason)
    }
  }
}
