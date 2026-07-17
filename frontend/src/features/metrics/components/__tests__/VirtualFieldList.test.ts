import { describe, expect, it } from 'vitest'

import { alignedFacetBatchKeys, virtualFieldKeyboardTarget } from '../VirtualFieldList'

describe('virtual field facet demand', () => {
  it('aligns mounted cards to stable 24-field request batches', () => {
    const keys = Array.from({ length: 300 }, (_, index) => `metric_${index}`)

    expect(alignedFacetBatchKeys(keys, [0, 1, 8])).toEqual(keys.slice(0, 24))
    expect(alignedFacetBatchKeys(keys, [22, 24, 25])).toEqual(keys.slice(0, 48))
    expect(alignedFacetBatchKeys(keys, [296, 299])).toEqual(keys.slice(288, 300))
  })

  it('maps keyboard navigation to bounded virtual field indices', () => {
    expect(virtualFieldKeyboardTarget('End', 0, 300, 4)).toBe(299)
    expect(virtualFieldKeyboardTarget('Home', 299, 300, 4)).toBe(0)
    expect(virtualFieldKeyboardTarget('PageDown', 20, 300, 4)).toBe(24)
    expect(virtualFieldKeyboardTarget('PageUp', 2, 300, 4)).toBe(0)
    expect(virtualFieldKeyboardTarget('ArrowDown', 299, 300, 4)).toBe(299)
    expect(virtualFieldKeyboardTarget('Tab', 0, 300, 4)).toBeNull()
  })
})
