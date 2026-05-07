import { describe, expect, it } from 'vitest'
import {
  didViewerPanMove,
  shouldSuppressViewerClickAfterInteraction,
} from '../useZoomPan'

describe('useZoomPan interaction guards', () => {
  it('only treats a pan as a drag once it passes the click suppression threshold', () => {
    expect(didViewerPanMove({ x: 10, y: 10 }, { x: 12, y: 12 })).toBe(false)
    expect(didViewerPanMove({ x: 10, y: 10 }, { x: 13, y: 10 })).toBe(true)
  })

  it('suppresses the next click after a drag or pinch interaction', () => {
    expect(
      shouldSuppressViewerClickAfterInteraction({ panMoved: false, pinchActive: false }),
    ).toBe(false)
    expect(
      shouldSuppressViewerClickAfterInteraction({ panMoved: true, pinchActive: false }),
    ).toBe(true)
    expect(
      shouldSuppressViewerClickAfterInteraction({ panMoved: false, pinchActive: true }),
    ).toBe(true)
  })
})
