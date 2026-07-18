import { afterEach, describe, expect, it, vi } from 'vitest'
import {
  createBoundedRetryScheduler,
  createFieldSchemaRefreshScheduler,
} from '../useAppSyncEvents'

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

describe('persistence repair retry scheduling', () => {
  it('caps retries and resets after a successful repair', () => {
    vi.useFakeTimers()
    const retry = vi.fn()
    const scheduler = createBoundedRetryScheduler(retry, [10, 20])

    scheduler.schedule()
    scheduler.schedule()
    vi.advanceTimersByTime(10)
    expect(retry).toHaveBeenCalledTimes(1)
    scheduler.schedule()
    vi.advanceTimersByTime(20)
    expect(retry).toHaveBeenCalledTimes(2)
    scheduler.schedule()
    vi.runAllTimers()
    expect(retry).toHaveBeenCalledTimes(2)

    scheduler.reset()
    scheduler.schedule()
    vi.advanceTimersByTime(10)
    expect(retry).toHaveBeenCalledTimes(3)
  })
})
