import { afterEach, describe, expect, it, vi } from 'vitest'

import { scheduleCommittedText } from '../AttributesPanel'

describe('committed attribute text', () => {
  afterEach(() => {
    vi.useRealTimers()
  })

  it('coalesces ten rapid draft changes into one idle commit', () => {
    vi.useFakeTimers()
    const commit = vi.fn()
    let cancel = () => {}

    for (let index = 0; index < 10; index += 1) {
      cancel()
      cancel = scheduleCommittedText(commit, 250)
      vi.advanceTimersByTime(20)
    }

    expect(commit).not.toHaveBeenCalled()
    vi.advanceTimersByTime(250)
    expect(commit).toHaveBeenCalledTimes(1)
  })

  it('cancels an idle commit when the input unmounts', () => {
    vi.useFakeTimers()
    const commit = vi.fn()
    const cancel = scheduleCommittedText(commit, 250)

    cancel()
    vi.runAllTimers()

    expect(commit).not.toHaveBeenCalled()
  })
})
