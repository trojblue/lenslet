import { describe, expect, it } from 'vitest'
import { delayedVisibilityWaitMs } from '../useDelayedVisibility'

describe('delayed visibility timing', () => {
  it('keeps copy hidden until the full delay has elapsed', () => {
    expect(delayedVisibilityWaitMs(800, 1_000, 1_350)).toBe(450)
  })

  it('shows copy immediately when an earlier phase already crossed the delay', () => {
    expect(delayedVisibilityWaitMs(800, 1_000, 1_900)).toBe(0)
  })

  it('does not lengthen the delay when the clock moves backwards', () => {
    expect(delayedVisibilityWaitMs(800, 1_000, 900)).toBe(800)
  })
})
