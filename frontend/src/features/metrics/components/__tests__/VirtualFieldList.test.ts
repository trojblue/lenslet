import { describe, expect, it } from 'vitest'

import {
  alignedFacetBatchKeys,
  initialFacetBatchKeys,
  resolveVirtualFieldIndices,
  resolveVisibleFacetBatch,
  virtualFieldViewportIndices,
  virtualFieldKeyboardTarget,
} from '../VirtualFieldList'

describe('virtual field facet demand', () => {
  it('aligns mounted cards to stable 24-field request batches', () => {
    const keys = Array.from({ length: 300 }, (_, index) => `metric_${index}`)

    expect(alignedFacetBatchKeys(keys, [0, 1, 8])).toEqual(keys.slice(0, 24))
    expect(alignedFacetBatchKeys(keys, [22, 24, 25])).toEqual(keys.slice(0, 48))
    expect(alignedFacetBatchKeys(keys, [296, 299])).toEqual(keys.slice(288, 300))
  })

  it('seeds the first aligned batch before virtual measurement', () => {
    const keys = Array.from({ length: 30 }, (_, index) => `field_${index}`)

    expect(initialFacetBatchKeys(keys)).toEqual(keys.slice(0, 24))
    expect(initialFacetBatchKeys([])).toEqual([])
  })

  it('retains a compatible measured batch and rejects it across a reset', () => {
    const keys = Array.from({ length: 30 }, (_, index) => `field_${index}`)
    const retained = keys.slice(24)

    expect(resolveVisibleFacetBatch(keys, retained, true)).toEqual(retained)
    expect(resolveVisibleFacetBatch(keys, retained, false)).toEqual(keys.slice(0, 24))
    expect(resolveVisibleFacetBatch(keys.slice(0, 20), retained, true)).toEqual(keys.slice(0, 20))
  })

  it('maps keyboard navigation to bounded virtual field indices', () => {
    expect(virtualFieldKeyboardTarget('End', 0, 300, 4)).toBe(299)
    expect(virtualFieldKeyboardTarget('Home', 299, 300, 4)).toBe(0)
    expect(virtualFieldKeyboardTarget('PageDown', 20, 300, 4)).toBe(24)
    expect(virtualFieldKeyboardTarget('PageUp', 2, 300, 4)).toBe(0)
    expect(virtualFieldKeyboardTarget('ArrowDown', 299, 300, 4)).toBe(299)
    expect(virtualFieldKeyboardTarget('Tab', 0, 300, 4)).toBeNull()
  })

  it('computes the overscanned target range synchronously from a scroll event', () => {
    expect(virtualFieldViewportIndices(24 * 396, 576, 30, 384)).toEqual(
      Array.from({ length: 10 }, (_, offset) => offset + 20),
    )
  })

  it('re-seeds numeric indices when field schema identity changes', () => {
    expect(resolveVirtualFieldIndices(
      'schema-a', 0, [24, 25], 'schema-b', 1, 30, 384,
    )).toEqual(
      [0, 1, 2, 3, 4, 5],
    )
  })

  it('does not resurrect indices when an earlier schema identity returns', () => {
    expect(resolveVirtualFieldIndices(
      'schema-a', 0, [24, 25], 'schema-a', 2, 30, 384,
    )).toEqual([0, 1, 2, 3, 4, 5])
  })
})
