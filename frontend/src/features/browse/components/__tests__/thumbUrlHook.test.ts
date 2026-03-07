import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'
import { scheduleObjectUrlRevoke } from '../../../../shared/hooks/useBlobUrl'

describe('thumb URL lifecycle', () => {
  beforeEach(() => {
    vi.useFakeTimers()
  })

  afterEach(() => {
    vi.useRealTimers()
    vi.restoreAllMocks()
  })

  it('revokes the URL after the scheduled lifecycle window', () => {
    const finalize = vi.fn()
    const revokeSpy = vi.spyOn(URL, 'revokeObjectURL').mockImplementation(() => {})

    scheduleObjectUrlRevoke('blob:thumb-1', finalize)
    expect(revokeSpy).not.toHaveBeenCalled()

    vi.runAllTimers()

    expect(finalize).toHaveBeenCalledTimes(1)
    expect(revokeSpy).toHaveBeenCalledWith('blob:thumb-1')
  })

  it('cancels revocation when the pending lifecycle is cleared early', () => {
    const finalize = vi.fn()
    const revokeSpy = vi.spyOn(URL, 'revokeObjectURL').mockImplementation(() => {})

    const pending = scheduleObjectUrlRevoke('blob:thumb-2', finalize)
    pending.cancel()
    vi.runAllTimers()

    expect(finalize).toHaveBeenCalledTimes(1)
    expect(revokeSpy).not.toHaveBeenCalled()
  })
})
