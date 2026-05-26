import { describe, expect, it } from 'vitest'
import { createLatestFrameScheduler } from '../frameScheduler'

describe('latest frame scheduler', () => {
  it('coalesces repeated schedules into one frame and runs the latest callback', () => {
    const frames: Array<(time: number) => void> = []
    const calls: string[] = []
    const scheduler = createLatestFrameScheduler({
      requestFrame(callback) {
        frames.push(callback)
        return frames.length
      },
      cancelFrame() {},
    })

    scheduler.schedule(() => calls.push('first'))
    scheduler.schedule(() => calls.push('second'))

    expect(frames).toHaveLength(1)
    expect(calls).toEqual([])
    frames[0](16)
    expect(calls).toEqual(['second'])
    expect(scheduler.hasPending()).toBe(false)
  })

  it('cancels pending frame work', () => {
    const frames: Array<(time: number) => void> = []
    const canceled: number[] = []
    const calls: string[] = []
    const scheduler = createLatestFrameScheduler({
      requestFrame(callback) {
        frames.push(callback)
        return 7
      },
      cancelFrame(frameId) {
        canceled.push(frameId)
      },
    })

    scheduler.schedule(() => calls.push('stale'))
    expect(scheduler.hasPending()).toBe(true)
    scheduler.cancel()
    frames[0](16)

    expect(canceled).toEqual([7])
    expect(calls).toEqual([])
    expect(scheduler.hasPending()).toBe(false)
  })

  it('runs immediately when animation frames are unavailable', () => {
    const calls: string[] = []
    const scheduler = createLatestFrameScheduler({
      requestFrame() {
        return null
      },
      cancelFrame() {},
    })

    scheduler.schedule(() => calls.push('fallback'))

    expect(calls).toEqual(['fallback'])
    expect(scheduler.hasPending()).toBe(false)
  })
})
