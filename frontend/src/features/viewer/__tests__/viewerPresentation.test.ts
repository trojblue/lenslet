import { describe, expect, it } from 'vitest'
import { getViewerImagePresentation, shouldRenderViewerImageResource } from '../Viewer'

describe('viewer image presentation', () => {
  it('keeps the previous resource visible as transitional while a new path loads', () => {
    expect(getViewerImagePresentation('/set/a.jpg', '/set/b.jpg', false)).toEqual({
      isCurrent: false,
      isTransitioning: true,
      opacity: 0.42,
    })
  })

  it('hides a current resource until it has decoded for the active path', () => {
    expect(getViewerImagePresentation('/set/b.jpg', '/set/b.jpg', false)).toEqual({
      isCurrent: true,
      isTransitioning: false,
      opacity: 0,
    })
  })

  it('shows the current resource after decode', () => {
    expect(getViewerImagePresentation('/set/b.jpg', '/set/b.jpg', true)).toEqual({
      isCurrent: true,
      isTransitioning: false,
      opacity: 1,
    })
  })

  it('hides stale transitional media after the active target fails or is unsupported', () => {
    expect(shouldRenderViewerImageResource('/set/a.jpg', false)).toBe(true)
    expect(shouldRenderViewerImageResource('/set/a.jpg', true)).toBe(false)
  })
})
