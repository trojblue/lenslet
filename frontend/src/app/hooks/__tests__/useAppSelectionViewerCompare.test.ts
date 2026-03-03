import { describe, expect, it } from 'vitest'
import {
  resolveOverlayPopstateResult,
  shouldCloseCompareForSelectionChange,
} from '../useAppSelectionViewerCompare'

describe('useAppSelectionViewerCompare guards', () => {
  it('auto-closes compare only when compare is open and selection drops below compare support', () => {
    expect(shouldCloseCompareForSelectionChange(false, false)).toBe(false)
    expect(shouldCloseCompareForSelectionChange(false, true)).toBe(false)
    expect(shouldCloseCompareForSelectionChange(true, true)).toBe(false)
    expect(shouldCloseCompareForSelectionChange(true, false)).toBe(true)
  })

  it('resolves popstate overlays by clearing active viewer/compare overlays only', () => {
    expect(resolveOverlayPopstateResult(null, false)).toEqual({
      resetViewer: false,
      resetCompare: false,
    })
    expect(resolveOverlayPopstateResult('/images/a.png', false)).toEqual({
      resetViewer: true,
      resetCompare: false,
    })
    expect(resolveOverlayPopstateResult(null, true)).toEqual({
      resetViewer: false,
      resetCompare: true,
    })
    expect(resolveOverlayPopstateResult('/images/a.png', true)).toEqual({
      resetViewer: true,
      resetCompare: true,
    })
  })
})
