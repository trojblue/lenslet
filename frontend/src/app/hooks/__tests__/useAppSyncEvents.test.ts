import { afterEach, describe, expect, it, vi } from 'vitest'
import { createFieldSchemaRefreshScheduler } from '../useAppSyncEvents'

afterEach(() => {
  vi.useRealTimers()
})

describe('field schema refresh scheduling', () => {
  it('coalesces a continuous metric-event burst into one trailing refresh', () => {
    vi.useFakeTimers()
    const refresh = vi.fn()
    const scheduler = createFieldSchemaRefreshScheduler(refresh, 250)

    for (let index = 0; index < 100; index += 1) {
      scheduler.schedule()
      vi.advanceTimersByTime(10)
    }
    expect(refresh).not.toHaveBeenCalled()

    vi.advanceTimersByTime(239)
    expect(refresh).not.toHaveBeenCalled()
    vi.advanceTimersByTime(1)
    expect(refresh).toHaveBeenCalledTimes(1)
  })

  it('cancels a pending refresh on cleanup', () => {
    vi.useFakeTimers()
    const refresh = vi.fn()
    const scheduler = createFieldSchemaRefreshScheduler(refresh, 250)

    scheduler.schedule()
    scheduler.cancel()
    vi.runAllTimers()

    expect(refresh).not.toHaveBeenCalled()
  })
})
