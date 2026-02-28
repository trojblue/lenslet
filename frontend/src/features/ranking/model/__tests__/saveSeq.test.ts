import { describe, expect, it } from 'vitest'
import { isStaleSaveResponse, nextSaveSeq, sanitizeSaveSeq } from '../saveSeq'

describe('ranking save sequence contracts', () => {
  it('sanitizes unknown save sequence values', () => {
    expect(sanitizeSaveSeq(undefined)).toBe(0)
    expect(sanitizeSaveSeq(-1)).toBe(0)
    expect(sanitizeSaveSeq(4.9)).toBe(4)
  })

  it('increments save sequence monotonically', () => {
    expect(nextSaveSeq(0)).toBe(1)
    expect(nextSaveSeq(7)).toBe(8)
  })

  it('flags out-of-order responses as stale', () => {
    expect(isStaleSaveResponse(1, 2)).toBe(true)
    expect(isStaleSaveResponse(2, 2)).toBe(false)
    expect(isStaleSaveResponse(3, 2)).toBe(false)
  })
})

