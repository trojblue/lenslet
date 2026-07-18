import { describe, expect, it } from 'vitest'
import { lazySurfaceMessage } from '../lazySurface'

describe('lazy surface copy', () => {
  it('suppresses pending copy before the delay', () => {
    expect(lazySurfaceMessage('Loading inspector...', true, false)).toBe('\u00a0')
  })

  it('shows pending copy after the delay and errors immediately', () => {
    expect(lazySurfaceMessage('Loading compare...', true, true)).toBe('Loading compare...')
    expect(lazySurfaceMessage('Compare could not load.', false, false)).toBe('Compare could not load.')
  })
})
