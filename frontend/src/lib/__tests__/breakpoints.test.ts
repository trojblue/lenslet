import { describe, expect, it } from 'vitest'
import { LAYOUT_BREAKPOINTS, LAYOUT_MEDIA_QUERIES } from '../breakpoints'

describe('layout breakpoint constants', () => {
  it('keeps shared media query breakpoints stable for component-local compact UI', () => {
    expect(LAYOUT_BREAKPOINTS.phoneMax).toBe(480)
    expect(LAYOUT_BREAKPOINTS.narrowMax).toBe(900)
    expect(LAYOUT_BREAKPOINTS.mediumMax).toBe(1180)
    expect(LAYOUT_MEDIA_QUERIES.phone).toBe('(max-width: 480px)')
    expect(LAYOUT_MEDIA_QUERIES.narrow).toBe('(max-width: 900px)')
    expect(LAYOUT_MEDIA_QUERIES.toolbarCompact).toBe('(max-width: 1180px)')
  })
})
