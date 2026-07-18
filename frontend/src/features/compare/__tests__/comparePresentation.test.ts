import { describe, expect, it } from 'vitest'
import {
  comparePairCanCommit,
  compareResource,
  retainCurrentDecodedResourceIdentities,
  selectDecodedCompareResource,
} from '../comparePresentation'

describe('compare pair presentation', () => {
  it('prefers a decoded full resource and otherwise uses a decoded thumbnail', () => {
    const full = compareResource('/a.jpg', 'blob:full-a', 'full')
    const thumb = compareResource('/a.jpg', 'blob:thumb-a', 'thumbnail')
    expect(selectDecodedCompareResource(full, thumb, new Set([thumb!.identity]))).toBe(thumb)
    expect(selectDecodedCompareResource(full, thumb, new Set([thumb!.identity, full!.identity]))).toBe(full)
  })

  it('does not expose undecoded candidate resources', () => {
    const full = compareResource('/a.jpg', 'blob:full-a', 'full')
    expect(selectDecodedCompareResource(full, null, new Set())).toBeNull()
  })

  it('commits a pair only when both sides are decoded or terminal', () => {
    const a = compareResource('/a.jpg', 'blob:a', 'full')
    expect(comparePairCanCommit(a, null, false, false)).toBe(false)
    expect(comparePairCanCommit(a, null, false, true)).toBe(true)
  })

  it('retains decoded readiness for an unchanged side while dropping stale resources', () => {
    const unchanged = compareResource('/same.jpg', 'blob:same', 'full')
    const stale = compareResource('/old.jpg', 'blob:old', 'full')
    const next = compareResource('/next.jpg', 'blob:next', 'full')
    const retained = retainCurrentDecodedResourceIdentities(
      [unchanged, next],
      new Set([unchanged!.identity, stale!.identity]),
    )
    expect([...retained]).toEqual([unchanged!.identity])
  })
})
